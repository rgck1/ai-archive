# -*- coding: utf-8 -*-
"""近一周领涨组合 · 每日快照（合并进 v47-daily.service，每天 20:30 执行）。

设计要点（对齐用户约束）：
  - 不新建 timer / 独立任务：作为第 5 个 ExecStart 追加进现有 invest-workbench-v47-daily.service，
    timer 配置（每天 20:30、Persistent、AccuracySec）一个字不动，原 4 个脚本行为与频率完全保留。
  - 每天自动算一次：调用根 server.py 的 api_recs_momentum()（唯一算法真值源，import 复用，
    不复制动量算法），把结果落盘 data/recs_momentum_snapshot.json；前端 /api/recs_momentum
    改为读该快照，页面一次请求不再现场重算。
  - 计算结果纳入现有处理流程：产物是 data/ 下的快照 JSON，与 recs_top3_run.json 等同类，
    由 server.py 的 /api/recs_momentum 统一读取渲染。
  - 处理重复执行：
      1) flock 文件锁——并发/补跑重叠时直接退出，不重复算、不重复写；
      2) 内容哈希去重——结果没变（如周末净值未更新）就不重写快照正文，只刷新审计计数，
         避免无谓 IO 与文件 mtime 抖动；
      3) 同日多次触发（手动 start + timer）幂等——快照带 day 字段，审计记录每次触发。
  - 退出码恒为 0：数据源异常属可恢复事件，保留上一版快照并在审计里标 stale，
    不让 systemd 反复报警，也不让页面变空。

用法：
  python3 recs_momentum_daily.py            # 正常每日执行
  python3 recs_momentum_daily.py --force    # 忽略去重，强制重算重写（手动修复用）
"""
import datetime
import hashlib
import json
import os
import sys
import time

try:
    import fcntl   # Linux（服务器）真文件锁；Windows 本地测试无此模块，降级为无锁
except ImportError:
    fcntl = None

APP = os.environ.get("WB_APP", "/opt/invest-workbench")
DATA = os.path.join(APP, "data")
SNAP = os.path.join(DATA, "recs_momentum_snapshot.json")
LOCK = os.path.join(DATA, ".recs_momentum_daily.lock")
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
os.environ.setdefault("XQ_CACHE_DIR", DATA)


def _stamp():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)   # 目录缺失时自恢复
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)
    try:
        import pwd
        u = pwd.getpwnam("invest")
        os.chown(path, u.pw_uid, u.pw_gid)
    except Exception:
        pass


def _content_hash(payload):
    """对快照正文做稳定哈希（排除每次都变的时间戳字段），用于去重判断。"""
    keys = ["generated_at", "items", "ranking", "excluded", "as_of", "status",
            "period", "eligible_count", "positive_count", "shortfall", "blocked_reason",
            "tradable_excluded", "tradable_min"]
    core = {k: payload.get(k) for k in keys}
    raw = json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def main():
    force = "--force" in sys.argv
    t0 = time.time()
    started = _stamp()
    today = datetime.date.today().isoformat()

    # 1) flock 防并发重复执行（timer 补跑 + 手动 start 重叠时只跑一个）
    #    服务器端 fcntl 可用则上真锁；本地 Windows 无 fcntl 时降级为无锁（便于自测）
    lk = open(LOCK, "w") if fcntl else None
    if fcntl:
        try:
            fcntl.flock(lk.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("[recs-mom] 另一实例正在执行，本次跳过（flock）", flush=True)
            lk.close()
            return 0

    prev = _load(SNAP, {})
    audit = list(prev.get("run_audit") or []) if isinstance(prev, dict) else []
    audit = audit[-19:]  # 保留最近 20 次审计
    prev_hash = str((prev or {}).get("content_sha") or "") if isinstance(prev, dict) else ""

    result = {
        "ok": False, "action": "", "content_sha": "", "as_of": None,
        "status": "", "error": "", "elapsed_sec": 0,
    }
    try:
        import server as S
        # 必须现场重算：api_recs_momentum({}) 默认会优先「读回上一版快照」，
        # 用它做每日计算会形成自循环（chash 恒定 → 永远 dedup，快照正文再不更新）。
        # _calc_recs_momentum 是同一套算法真值源，只是跳过快照读取直接算。
        calc = S._calc_recs_momentum({})   # 默认参数：window=5 / top_n=3 / positive=1
        if not isinstance(calc, dict) or not calc.get("ok"):
            raise RuntimeError("api_recs_momentum 返回不可用")
        chash = _content_hash(calc)
        result["as_of"] = calc.get("as_of")
        result["status"] = calc.get("status")
        result["content_sha"] = chash

        if (not force) and prev_hash and chash == prev_hash and isinstance(prev, dict) and prev.get("payload"):
            # 内容未变（净值未推进）——不重写正文，仅刷新审计，保持 generated_at 为真正的计算日
            result["action"] = "dedup"
            snap = dict(prev)
            snap["last_checked_at"] = started
            snap["day"] = today
        else:
            # 内容有变化或强制：写新快照正文
            calc["_snapshot_computed_at"] = started   # 计算时间（每天一次），供页面展示
            calc["_snapshot_source"] = "daily_task"   # 标记来源=定时任务快照
            snap = {
                "schema": "recs_momentum_snapshot_v1",
                "day": today,
                "computed_at": started,
                "last_checked_at": started,
                "content_sha": chash,
                "payload": calc,
            }
            result["action"] = "written"
        snap["run_audit"] = audit + [{
            "at": started, "action": result["action"], "day": today,
            "as_of": result["as_of"], "status": result["status"],
            "content_sha": chash[:12],
        }]
        _write_json(SNAP, snap)
        result["ok"] = True
        print("[recs-mom] %s ok=True as_of=%s status=%s sha=%s" % (
            result["action"], result["as_of"], result["status"], chash[:12]), flush=True)
    except Exception as e:
        result["error"] = str(e)[:240]
        # 异常保留上一版快照，只在审计里记一笔；无上一版则写一个不可用占位，避免 API 空转
        if not isinstance(prev, dict) or not prev.get("payload"):
            snap = {
                "schema": "recs_momentum_snapshot_v1", "day": today,
                "computed_at": started, "last_checked_at": started,
                "content_sha": "", "error": result["error"],
                "payload": {"ok": True, "status": "unavailable", "items": [], "ranking": [],
                            "generated_at": started,
                            "blocked_reason": "每日动量快照生成失败：" + result["error"],
                            "_snapshot_computed_at": started, "_snapshot_source": "daily_task_error"},
                "run_audit": audit + [{"at": started, "action": "error", "day": today,
                                       "error": result["error"]}],
            }
            _write_json(SNAP, snap)
        print("[recs-mom] 生成失败（保留上一版）：%s" % result["error"], flush=True)
    finally:
        result["elapsed_sec"] = round(time.time() - t0, 2)
        if fcntl and lk:
            fcntl.flock(lk.fileno(), fcntl.LOCK_UN)
        if lk:
            lk.close()
    return 0   # 恒 0，可恢复异常不触发 systemd 报警


if __name__ == "__main__":
    sys.exit(main())
