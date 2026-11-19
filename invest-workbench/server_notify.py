# -*- coding: utf-8 -*-
"""服务器侧企微直推底座（关机也能推送 · 2026-11-19）。

背景：推荐/告警的计算与快照在服务器 7x24，但企微推送此前只在本机 push_bridge.py，
本机关机即停、不补发。实测服务器带 key POST qyapi.weixin.qq.com 返回 errcode:0，
故把「关机也要到」的 P0 级信号改为服务器侧直推。

设计铁律：
  - webhook 只存服务器本地私有文件 data/server_notify_webhook（chmod 600 / invest:invest），
    或环境变量 PUSH_WEBHOOK_URL；绝不入代码库、不回显、不同步 ai-archive。
  - 北京时间显式：所有展示时间 = UTC+8，避免云/本机时区错位。
  - 内容去重：按 (kind, 内容 SHA) 记 data/server_notify_state.json，同内容冷却期内不重推；
    状态文件带最近 N 条审计，失败不标记已成功。
  - 分段发送：企微 text 单条 <2048 字节，按 1900 字节切段，首段可选 @all。
  - 失败有限重试 + 时间戳冷却，错误码归一，不把 URL/响应体写日志。
  - 退出码恒 0：推送失败是可恢复事件，不 systemd 反复报警。

作为模块被复用：
    import server_notify as N
    N.send("标题\\n正文", kind="freshness", mention_all=False)
    N.freshness_report()   # 计算五路数据新鲜度 -> (text, alerts列表)

作为 CLI（定时任务调用）：
    python3 server_notify.py --test                 # 连通性测试
    python3 server_notify.py --daily                # 每日汇总：推荐+freshness异常
    python3 server_notify.py --freshness            # 仅新鲜度异常时推
    python3 server_notify.py --text "标题\\n正文" --kind xxx [--all]
"""
import datetime
import hashlib
import json
import os
import sys
import time
import urllib.request
import urllib.error

APP = os.environ.get("WB_APP", "/opt/invest-workbench")
DATA = os.path.join(APP, "data")
WEBHOOK_FILE = os.path.join(DATA, "server_notify_webhook")
STATE_FILE = os.path.join(DATA, "server_notify_state.json")
CHINA_TZ = datetime.timezone(datetime.timedelta(hours=8))
CN = 1900          # 每段字节上限（企微 text 限 2048，留编号余量）
COOLDOWN = 6 * 3600  # 同内容默认冷却 6 小时（P0 级可按 kind 覆盖）
MAX_AUDIT = 40

# 新鲜度阈值（落后交易日）：超过即判 stale；行业轮动按用户口径 2 日
_FRESH_RULES = {
    "sector_rotation": 2,
    "nav": 3,
    "consensus": 5,
    "holdings": 5,
    "pool_daily": 5,
}


def now_cn():
    """北京时间字符串（显式 UTC+8，不依赖服务器本地时区）。"""
    return datetime.datetime.now(CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _load(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def get_webhook():
    """环境变量优先，其次服务器私有文件。返回 '' 表示未配置（静默跳过，不报错）。"""
    url = (os.environ.get("PUSH_WEBHOOK_URL") or "").strip()
    if url:
        return url
    try:
        with open(WEBHOOK_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def chunks(text, limit=CN):
    parts, part, size = [], "", 0
    for ch in text:
        n = len(ch.encode("utf-8"))
        if size + n > limit:
            parts.append(part); part, size = "", 0
        part += ch; size += n
    if part:
        parts.append(part)
    return [("[%s/%s]\n" % (i + 1, len(parts)) if len(parts) > 1 else "") + v
            for i, v in enumerate(parts)]


def _post(webhook, payload):
    """统一出站 POST：禁重定向、错误码与限流归一。不写 URL/响应体进日志。"""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **kw):
            return None
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(webhook, data=body,
                                 headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(NoRedirect(),
                                         urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=15) as r:
            result = json.loads(r.read(65536))
        code = result.get("errcode")
        if code == 0:
            return "accepted", ""
        if code in (-1, 45009):
            return "retry", "繁忙或限流(%s)" % code
        return "failed", "拒绝(%s)" % code
    except urllib.error.HTTPError as exc:
        if exc.code == 429 or exc.code >= 500:
            return "retry", "HTTP %s" % exc.code
        return "failed", "HTTP %s" % exc.code
    except Exception:
        return "retry", "连接异常"


def _state():
    return _load(STATE_FILE, {"sent": {}, "audit": []})


def _dedup_ok(st, key, kind, cooldown):
    rec = (st.get("sent") or {}).get(key)
    if not rec:
        return True
    cd = cooldown.get(kind, COOLDOWN)
    return (time.time() - float(rec.get("at") or 0)) >= cd


def send(content, kind="misc", mention_all=False, dedup=True,
         cooldown=None, title=""):
    """发一条企微消息。返回 dict {ok, skipped, reason, parts}。

    dedup=True 时按 (kind, 内容SHA) 冷却去重；dedup=False 强制发（测试/紧急）。
    cooldown: {kind: 秒} 覆盖默认冷却。
    """
    cooldown = cooldown or {}
    hook = get_webhook()
    if not hook:
        return {"ok": False, "skipped": True, "reason": "no_webhook", "parts": 0}
    text = ((title + "\n") if title else "") + str(content)
    fp = hashlib.sha256((kind + "|" + text).encode("utf-8")).hexdigest()
    st = _state()
    st.setdefault("sent", {}); st.setdefault("audit", [])
    if dedup and not _dedup_ok(st, fp, kind, cooldown):
        return {"ok": False, "skipped": True, "reason": "dedup", "parts": 0}

    parts = chunks(text)
    outcome = ("accepted", "")
    for i, part in enumerate(parts):
        payload_text = {"content": part}
        if mention_all and i == 0:
            payload_text["mentioned_list"] = ["@all"]
        outcome = _post(hook, {"msgtype": "text", "text": payload_text})
        if outcome[0] != "accepted":
            break

    ok = outcome[0] == "accepted"
    st["audit"].insert(0, {
        "at": now_cn(), "kind": kind, "fp": fp[:12],
        "chars": len(text), "parts": len(parts),
        "state": outcome[0], "note": outcome[1],
    })
    st["audit"] = st["audit"][:MAX_AUDIT]
    if ok:
        st["sent"][fp] = {"at": time.time(), "kind": kind}
        # 只保留最近 200 个去重键，防止无限增长
        if len(st["sent"]) > 200:
            keep = sorted(st["sent"].items(),
                          key=lambda kv: kv[1].get("at") or 0, reverse=True)[:200]
            st["sent"] = dict(keep)
    _write(STATE_FILE, st)
    return {"ok": ok, "skipped": False, "reason": outcome[1], "parts": len(parts)}


# ---------------- 新鲜度探针（P0 · 纯只读） ----------------
def _last_date_from_list(d, key="date"):
    if isinstance(d, dict):
        for k in ("days", "items", "points", "series", "history"):
            v = d.get(k)
            if isinstance(v, list) and v:
                last = v[-1]
                if isinstance(last, dict) and last.get(key):
                    return str(last[key])[:10]
    return ""


def _freshness_rows():
    """返回 [{name, last, lag, threshold, stale, note}]，全部只读本地 JSON。"""
    def load(fn):
        return _load(os.path.join(DATA, fn), {})

    rows = []
    # 1) 行业轮动：date
    d = load("sector_rotation_latest.json")
    rows.append(("行业轮动", str(d.get("date") or "")[:10], d.get("built_at") or ""))
    # 2) 净值：scan nav_*.json 的最新 date 字段（取全池最大）
    latest_nav, nav_count = "", 0
    try:
        for fn in os.listdir(DATA):
            if not (fn.startswith("nav_") and fn.endswith(".json")):
                continue
            dd = load(fn)
            pts = dd.get("points") if isinstance(dd, dict) else None
            if isinstance(pts, list) and pts:
                nav_count += 1
                dt = str(pts[-1].get("date") or "")[:10]
                if dt and dt > latest_nav:
                    latest_nav = dt
    except OSError:
        pass
    rows.append(("组合净值", latest_nav, "%d只" % nav_count))
    # 3) 一致预期：time
    d = load("last_consensus.json")
    rows.append(("一致预期", str(d.get("time") or "")[:10], ""))
    # 4) 持仓：time
    d = load("holdings_snapshot.json")
    rows.append(("持仓快照", str(d.get("time") or "")[:10], ""))
    # 5) 业绩池：days 最后一条
    d = load("pool_daily.json")
    rows.append(("业绩曲线", _last_date_from_list(d), ""))

    # 计算落后交易日（粗略：跳过周末；不含节假日精确日历，够告警用）
    today = datetime.datetime.now(CHINA_TZ).date()
    out = []
    names = list(_FRESH_RULES.keys())
    for (name, last, note), key in zip(rows, names):
        lag = None
        if last:
            try:
                dt = datetime.date.fromisoformat(last)
                d0, cnt = dt, 0
                while d0 < today:
                    d0 += datetime.timedelta(days=1)
                    if d0.weekday() < 5:
                        cnt += 1
                lag = cnt
            except ValueError:
                lag = None
        th = _FRESH_RULES[key]
        stale = (lag is None) or (lag > th)
        out.append({"name": name, "key": key, "last": last, "lag": lag,
                    "threshold": th, "stale": stale, "note": note})
    return out


def freshness_report():
    rows = _freshness_rows()
    alerts = [r for r in rows if r["stale"]]
    lines = ["【数据新鲜度巡检】%s" % now_cn()]
    for r in rows:
        flag = "⚠️过期" if r["stale"] else "OK"
        lag = ("落后%s交易日" % r["lag"]) if r["lag"] is not None else "无法判定"
        lines.append("· %s：%s（%s，阈值%s）%s" % (
            r["name"], r["last"] or "无日期", lag, r["threshold"],
            ("  " + r["note"]) if r["note"] else ""))
    return "\n".join(lines), alerts


# ---------------- 每日汇总推送 ----------------
def _recs_summary():
    d = _load(os.path.join(DATA, "recs_momentum_snapshot.json"), {})
    p = d.get("payload") or {}
    items = p.get("items") or []
    if not items:
        return None
    lines = ["【今日推荐 · 近一周领涨组合】快照日 %s" % (d.get("day") or "—")]
    for x in items[:5]:
        code = str(x.get("code") or "")
        name = str(x.get("name") or code)
        pct = x.get("pct") or x.get("ret") or x.get("change_pct")
        pcts = ("%+.2f%%" % pct) if isinstance(pct, (int, float)) else ""
        lines.append("· %s %s %s" % (name, code, pcts))
    lines.append("（规则化动量筛选，非投资建议，请核对原文独立判断）")
    return "\n".join(lines)


def daily():
    """每日 20:30 v47-daily 调用：推荐快照 + 新鲜度异常，各按 kind 独立去重。"""
    results = {}
    recs = _recs_summary()
    if recs:
        results["recs"] = send(recs, kind="daily_recs", mention_all=False,
                               title="", cooldown={"daily_recs": 20 * 3600})
    text, alerts = freshness_report()
    if alerts:
        results["freshness"] = send(text, kind="freshness", mention_all=False,
                                    cooldown={"freshness": 20 * 3600})
    else:
        results["freshness"] = {"ok": True, "skipped": True, "reason": "all_fresh"}
    return results


def main():
    args = sys.argv[1:]
    if "--test" in args:
        print(json.dumps(send("[投资工作台] 服务器直推连通性测试 %s\n收到即表示关机也能推送。" % now_cn(),
                              kind="test", dedup=False), ensure_ascii=False))
        return 0
    if "--freshness" in args:
        text, alerts = freshness_report()
        print(text)
        if alerts:
            print(json.dumps(send(text, kind="freshness",
                                  cooldown={"freshness": 20 * 3600}), ensure_ascii=False))
        return 0
    if "--daily" in args:
        print(json.dumps(daily(), ensure_ascii=False))
        return 0
    if "--text" in args:
        i = args.index("--text")
        content = args[i + 1] if i + 1 < len(args) else ""
        kind = "misc"
        if "--kind" in args:
            k = args.index("--kind")
            kind = args[k + 1] if k + 1 < len(args) else "misc"
        print(json.dumps(send(content, kind=kind, mention_all=("--all" in args),
                              dedup=("--no-dedup" not in args)), ensure_ascii=False))
        return 0
    print("用法: --test | --daily | --freshness | --text '内容' [--kind X] [--all] [--no-dedup]")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        # 推送底座自身异常也不能让定时任务失败
        print("server_notify error: %s" % str(e)[:200])
        sys.exit(0)
