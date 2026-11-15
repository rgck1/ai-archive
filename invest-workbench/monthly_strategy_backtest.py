# -*- coding: utf-8 -*-
"""跟单推荐 Top3 · 每月自动回测（由 systemd timer 每月 1 日 04:30 触发）。

职责：
  1) 以 invest 身份跑 strategy_lab.py 全量回测：8 个现有配置方案 + 18 个公开策略，
     3 个页面标的池、1250 交易日窗口、真实成本与市场摩擦统一口径。
     strategy_lab.py 的 _summarize() 会对**每一个策略**做跨池综合自评分
     （池内夏普 50% + 总收益 30% + 回撤反向 20% 的排名百分位，再对可用池取平均），
     并把全量评分结果写进 strategy_lab.json 的 summary.ranking。
  2) 严格校验新结果（有效池 ≥ 2、每池有效策略 ≥ 15、generated_at 必须更新）。
     不合格就恢复上一版 strategy_lab.json —— 绝不拿网络失败产生的空数据覆盖真值。
  3) 写 data/recs_top3_run.json 运行审计（本次时间、耗时、Top3、是否 stale）。
     **Top3 的选取与渲染统一由 /api/recs_top3 现场从 strategy_lab.json 派生**，
     这样展示内容永远等于最新一次月度回测，不会出现「快照」与「回测」两份数据打架。

用法：
  python3 monthly_strategy_backtest.py                 # 完整月度跑（回测 + 校验 + 审计）
  python3 monthly_strategy_backtest.py --derive-only  # 不跑回测，只按现有回测结果刷新审计

退出码恒为 0：网络/数据源异常属于可恢复事件，保留上一版并标 stale，
不让 systemd timer 反复报警，也不让页面变空。
"""
import datetime
import json
import os
import shutil
import subprocess
import sys
import time

APP = os.environ.get("WB_APP", "/opt/invest-workbench")
DATA = os.path.join(APP, "data")
LAB_PY = os.path.join(APP, "strategy_lab.py")
LAB_JSON = os.path.join(DATA, "strategy_lab.json")
RUN_JSON = os.path.join(DATA, "recs_top3_run.json")
LAB_TIMEOUT = 2400          # 5 年窗口三池全策略，CPU 密集，给足 40 分钟
PYTHON = "/usr/bin/python3"


def _load(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)
    # 服务以 invest 运行，正常情况文件已属 invest；这里兜底处理 root 手工执行的情况
    try:
        import pwd
        u = pwd.getpwnam("invest")
        os.chown(path, u.pw_uid, u.pw_gid)
    except Exception:
        pass


def _stamp():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _validate(d, prev_generated_at):
    """新回测必须「真的跑成了」才允许替换旧真值。"""
    if not isinstance(d, dict) or not d.get("ok"):
        return False, "回测结果 ok=False"
    pools = [p for p in (d.get("pools") or []) if (p or {}).get("ok")]
    if len(pools) < 2:
        return False, "有效回测池不足 2 个（%d）" % len(pools)
    for p in pools:
        ok_cnt = sum(1 for r in (p.get("results") or []) if r.get("status") == "ok")
        if ok_cnt < 15:
            return False, "池 %s 有效策略仅 %d 个" % (p.get("key"), ok_cnt)
    ranking = ((d.get("summary") or {}).get("ranking") or [])
    if len(ranking) < 15:
        return False, "参与自评分的策略不足 15 个（%d）" % len(ranking)
    gen = str(d.get("generated_at") or "")
    if prev_generated_at and gen <= prev_generated_at:
        return False, "generated_at 未更新（%s）" % gen
    return True, ""


def _top3_brief(d):
    """审计日志里的简要 Top3：按综合分降序，取前三（与 /api/recs_top3 同规则）。"""
    ranking = [x for x in (((d.get("summary") or {}).get("ranking")) or [])
               if isinstance(x, dict)]
    ranking.sort(key=lambda x: -float(x.get("score") or 0))
    return [{"rank": i + 1, "key": x.get("key"), "name": x.get("name"),
             "score": x.get("score")}
            for i, x in enumerate(ranking[:3])]


def _write_run(obj):
    _write_json(RUN_JSON, obj)


def main():
    derive_only = "--derive-only" in sys.argv
    started = _stamp()
    t0 = time.time()
    prev = _load(LAB_JSON, {})
    prev_gen = str((prev or {}).get("generated_at") or "") if isinstance(prev, dict) else ""
    run = {
        "started_at": started, "finished_at": "", "ok": False,
        "mode": "derive-only" if derive_only else "full-backtest",
        "lab_generated_at": prev_gen, "top3": [], "elapsed_sec": 0,
        "stale": False, "error": "",
        "next_run": "每月 1 日 04:30（Asia/Shanghai）自动重跑",
    }

    if not derive_only:
        bak = ""
        if os.path.isfile(LAB_JSON):
            bak = LAB_JSON + ".bak_" + datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            try:
                shutil.copy2(LAB_JSON, bak)
            except Exception as e:
                print("[monthly] 备份失败，仍继续：%s" % str(e)[:120])
        env = os.environ.copy()
        env["XQ_CACHE_DIR"] = DATA
        print("[monthly] 开始全量回测：%s" % LAB_PY, flush=True)
        try:
            p = subprocess.run([PYTHON, LAB_PY], cwd=APP, env=env,
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace",
                               timeout=LAB_TIMEOUT)
            tail = (p.stdout or "").strip().splitlines()[-12:]
            print("[monthly] 回测退出码=%s" % p.returncode, flush=True)
            for ln in tail:
                print("  " + ln, flush=True)
            if p.returncode != 0:
                run["error"] = "strategy_lab.py 退出码 %s：%s" % (
                    p.returncode, (p.stderr or "")[-300:])
        except subprocess.TimeoutExpired:
            run["error"] = "全量回测超时（%d 秒）" % LAB_TIMEOUT
        except Exception as e:
            run["error"] = "全量回测异常：%s" % str(e)[:200]

        cur = _load(LAB_JSON, {})
        ok, why = _validate(cur, prev_gen)
        if run["error"]:
            ok, why = False, run["error"] + "；" + why
        if not ok:
            # 恢复上一版真值，绝不把坏数据留在 strategy_lab.json
            if bak and os.path.isfile(bak):
                try:
                    os.replace(bak, LAB_JSON)
                    print("[monthly] 已恢复上一版 strategy_lab.json", flush=True)
                except Exception as e:
                    print("[monthly] 恢复失败：%s" % str(e)[:120], flush=True)
            run.update({"ok": False, "stale": True, "error": ("校验不通过：" + why).strip(),
                        "finished_at": _stamp(),
                        "elapsed_sec": round(time.time() - t0, 1)})
            _write_run(run)
            print("[monthly] 本次回测未采纳，保留上一版：%s" % why, flush=True)
            return 0
        run["lab_generated_at"] = cur.get("generated_at")
        run["ohlc_source"] = cur.get("ohlc_source") or ""
        d = cur
    else:
        d = _load(LAB_JSON, {})
        if not isinstance(d, dict) or not d.get("ok"):
            run.update({"ok": False, "stale": True,
                        "error": "strategy_lab.json 不可用，无法派生 Top3",
                        "finished_at": _stamp()})
            _write_run(run)
            print("[monthly] strategy_lab.json 不可用", flush=True)
            return 0
        run["lab_generated_at"] = d.get("generated_at")
        run["ohlc_source"] = d.get("ohlc_source") or ""
        ok, why = _validate(d, "")      # derive-only 只校验内容完整性，不比时间戳
        if not ok:
            run.update({"ok": False, "stale": True, "error": "现有回测结果不完整：" + why,
                        "finished_at": _stamp()})
            _write_run(run)
            print("[monthly] 现有回测结果不完整：%s" % why, flush=True)
            return 0

    run["top3"] = _top3_brief(d)
    run.update({"ok": True, "stale": False, "error": "",
                "finished_at": _stamp(),
                "elapsed_sec": round(time.time() - t0, 1),
                "total_strategies": len(((d.get("summary") or {}).get("ranking")) or []) })
    _write_run(run)
    print("[monthly] 完成：lab=%s 参与评分=%s" % (
        run["lab_generated_at"], run.get("total_strategies")), flush=True)
    for x in run["top3"]:
        print("  TOP%d %s (%s) score=%s" % (
            x["rank"], x["name"], x["key"], x["score"]), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
