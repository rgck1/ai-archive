# -*- coding: utf-8 -*-
"""投资工作台 · 信息雷达企微推送桥接器（本机常驻，Python 3.9+ 标准库）。

职责（每轮）：
  1) 交易时段 09:00–15:30 每 60 秒拉一次线上 /api/radar/brief（令牌鉴权、只读）；
  2) P0 紧急（跌破止损 / 跟单清仓 / 跌破大趋势线）合并成一条，立即直发并 @all，
     绕过信息雷达的 5 分钟合并与 4 秒节流；
  3) P1 做T信号（新进入买/卖）、P1b 条件单触发（买点/目标达成）、P2 今日决策卡
     只向信息雷达 wecom_jobs 追加任务，由雷达自身发送线程统一发出，复用其重试 / 限流 / 状态页；
     条件单止损触发不在此推（已由 P0 紧急 stop 覆盖），避免同标的重复 @all；
  4) 非交易时段静默，直接睡到下一个交易日 09:00，不空转。

设计边界：
  - 绝不改动信息雷达的任何业务表，只向 wecom_jobs 追加待发送任务；
  - Webhook 只从 信息雷达/data/preferences.json 读，令牌只从同目录 config.json 读，
    两者不写日志、不回显；
  - 首次运行静默播种存量预警，不补发历史消息（--force 可跳过）；
  - 网络异常只记日志并退出本轮，不抛异常弹窗、不影响其它本机服务；
  - 本机时钟按北京时间使用（与 A 股一致）；法定节假日以 brief.trade_day 为准。

用法：
  python push_bridge.py --once --dry-run   # 跑一轮，只打印将发的消息
  python push_bridge.py --once             # 跑一轮并真正发送
  python push_bridge.py --test             # 发一条链路测试消息（不 @all）
  python push_bridge.py --loop             # 常驻（由 start_services.py 拉起）
  python push_bridge.py --once --dry-run --force --ignore-session
      # 周末/夜间用线上真实数据预览完整消息；仅打印，不发送、不入队、不写状态
"""
import os
import sys
import json
import time
import hashlib
import sqlite3
import datetime
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(HERE, "config.json")
LOG_PATH = os.path.join(HERE, "push_bridge.log")
STATE_PATH = os.path.join(HERE, "push_state.json")
RADAR_DIR = os.path.abspath(os.path.join(HERE, "..", "信息雷达"))
RADAR_PROGRAM = os.path.join(RADAR_DIR, "程序")
RADAR_PREFS = os.path.join(RADAR_DIR, "data", "preferences.json")
RADAR_DB = os.path.join(RADAR_DIR, "data", "radar.sqlite3")

# 默认参数：均可在 config.json 里用同名键覆盖
DEFAULT_BRIEF_URL = "https://wt.likeke.top/api/radar/brief"
DEFAULT_HOME_URL = "https://wt.likeke.top/"
POLL_SECONDS = 60
SESSION_START_HM = 9 * 60          # 09:00
SESSION_END_HM = 15 * 60 + 30      # 15:30
DECISION_PRE_HM = 9 * 60 + 25      # 09:25 盘前决策卡
DECISION_POST_HM = 15 * 60 + 10    # 15:10 结论变化补推
P0_COOLDOWN = 3600                 # 同标的同级别 1 小时冷却
P1_COOLDOWN = 3600
P0_MAX_ITEMS = 8
P1_MAX_ITEMS = 10
P2_MAX_ROWS = 4
URGENT_LEVELS = ("stop", "cleared", "trend")   # 用户拍板：三类全算 P0，全部 @all

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 复用信息雷达自己的发送实现，保证 URL 白名单 / 分块 / 错误码处理只有一份真值源
sys.path.insert(0, RADAR_PROGRAM)
try:
    from wecom import send, send_rich, chunks, validate_url  # noqa: E402
except Exception as _exc:  # pragma: no cover
    print("无法加载信息雷达 wecom.py：%s" % str(_exc)[:160])
    raise


def log(msg):
    line = "%s %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    # pythonw 下拉起时 stdout 可为 None，输出失败不能中断推送
    try:
        print(line)
    except Exception:
        pass


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_state(state):
    tmp = STATE_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE_PATH)
    except OSError as e:
        log("状态写入失败：%s" % str(e)[:100])


def blank_state():
    return {"boot_seeded": False, "urgent": {}, "tsig": {}, "p0_day": {},
            "cond": {}, "cond_day": {},
            "decision": {"day": "", "pre_hash": None, "post_hash": None}}


def cfg():
    return load_json(CFG_PATH, {}) or {}


def webhook():
    w = ((load_json(RADAR_PREFS, {}) or {}).get("wecom") or {})
    return str(w.get("webhook") or "").strip()


def fetch_brief(token, url):
    body = json.dumps({"token": token, "ts": time.time()}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8",
                 "User-Agent": "wb-push-bridge/1.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        d = json.loads(r.read().decode("utf-8", "ignore"))
    if not isinstance(d, dict) or not d.get("ok"):
        raise RuntimeError("brief 返回异常：%s" % str(d.get("error") or "")[:80])
    return d


# --------------------------------------------------------------------------
# 消息格式（三类新消息 + 现有 P3 保持原样）
# --------------------------------------------------------------------------
def _fmt_price(v):
    try:
        return "%.2f" % float(v)
    except (TypeError, ValueError):
        return "—"


def _fmt_pct(v):
    try:
        return "%+.1f%%" % (float(v) * 100)
    except (TypeError, ValueError):
        return "—"


LEVEL_LABEL = {"stop": "跌破止损线", "cleared": "跟单组合已清仓",
               "trend": "跌破大趋势线"}


def format_p0(items, brief, home):
    ts = str(brief.get("generated_at") or "")[-8:] or time.strftime("%H:%M:%S")
    lines = ["🚨【P0 紧急 · %d 条】%s" % (len(items), ts),
             "────────────────"]
    for i, x in enumerate(items[:P0_MAX_ITEMS], 1):
        lines.append("%d. %s(%s) %s" % (
            i, x.get("name") or "?", x.get("code") or "?",
            LEVEL_LABEL.get(x.get("level"), x.get("label") or "紧急信号")))
        bits = ["现价 " + _fmt_price(x.get("price"))]
        if x.get("stop_price") is not None:
            bits.append("止损价 " + _fmt_price(x.get("stop_price")))
        if x.get("pnl_pct") is not None:
            bits.append("浮盈亏 " + _fmt_pct(x.get("pnl_pct")))
        lines.append("   " + " / ".join(bits))
        why = str(x.get("reason") or "").strip()
        if why:
            lines.append("   " + why[:56])
    if len(items) > P0_MAX_ITEMS:
        lines.append("…另有 %d 条，打开工作台查看" % (len(items) - P0_MAX_ITEMS))
    lines += ["────────────────", "处理入口：" + home,
              "本条为即时高优先级通知；同一交易日同标的同级别只提醒一次，级别变化立即重推。"]
    return "\n".join(lines)


def format_p1(items, brief):
    ts = str(brief.get("generated_at") or "")[-8:] or time.strftime("%H:%M:%S")
    lines = ["【P1 做T信号】%d 只新出现可操作信号（%s）" % (len(items), ts)]
    for x in items[:P1_MAX_ITEMS]:
        act = "高抛" if x.get("signal") == "sell" else "低吸"
        sp = ("%.2f%%" % x["space"]) if isinstance(x.get("space"), (int, float)) else "—"
        ref = ""
        if x.get("in_px") is not None and x.get("out_px") is not None:
            ref = "｜参考 %s → %s" % (_fmt_price(x["in_px"]), _fmt_price(x["out_px"]))
        lines.append("%s %s(%s) 强度%s 空间%s%s" % (
            act, x.get("name") or "?", x.get("code") or "?",
            x.get("level") or "—", sp, ref))
    if len(items) > P1_MAX_ITEMS:
        lines.append("…另有 %d 只，打开工作台查看" % (len(items) - P1_MAX_ITEMS))
    lines += ["数据时间：" + str((brief.get("t_signal") or {}).get("updated_at") or "—"),
              "仅为信号提示，不代下单；强信号低吸已按 v2 规则硬过滤。"]
    return "\n".join(lines)


TRIG_LABEL = {"buy": "买点触发", "target": "目标达成", "stop": "止损触发"}


def format_cond(items, brief):
    """条件单触发（机会型：买点/目标达成），P1 入队，不 @all。"""
    ts = str(brief.get("generated_at") or "")[-8:] or time.strftime("%H:%M:%S")
    lines = ["【P1 条件单触发】%d 只（%s）" % (len(items), ts)]
    for x in items[:12]:
        trig = TRIG_LABEL.get(x.get("trigger"), "条件触发")
        lines.append("· %s(%s) %s　现价 %s" % (
            x.get("name") or "?", x.get("code") or "?", trig, _fmt_price(x.get("price"))))
        bits = []
        if x.get("buy") is not None:
            bits.append("买点 " + _fmt_price(x["buy"]))
        if x.get("target") is not None:
            bits.append("目标 " + _fmt_price(x["target"]))
        if x.get("stop") is not None:
            bits.append("止损 " + _fmt_price(x["stop"]))
        if bits:
            lines.append("    " + " / ".join(bits))
    if len(items) > 12:
        lines.append("…另有 %d 只触发，打开工作台查看" % (len(items) - 12))
    lines += ["────────────────",
              "三件套与工作台「波段操作 / 今日操作 / 我的持仓」同源；触发仅提示，不代下单。"]
    return "\n".join(lines)


def format_p2(dec, day, when):
    sections = [("必须今天做", dec.get("must") or []),
                ("可以等", dec.get("later") or []),
                ("只是观察", dec.get("watch") or [])]
    lines = ["【P2 今日决策卡】%s · %s" % (day, when)]
    any_row = False
    for title, rows in sections:
        if not rows:
            continue
        any_row = True
        lines.append("%s（%d）" % (title, len(rows)))
        for r in rows[:P2_MAX_ROWS]:
            bits = "%s %s" % (r.get("act") or "—", r.get("name") or "?")
            if r.get("code"):
                bits += "(%s)" % r["code"]
            if r.get("price") is not None:
                bits += " 价格 " + _fmt_price(r["price"])
            why = str(r.get("why") or "").strip()
            if why:
                bits += "｜" + why[:52]
            lines.append("· " + bits)
        if len(rows) > P2_MAX_ROWS:
            lines.append("· …另有 %d 条" % (len(rows) - P2_MAX_ROWS))
    if not any_row:
        lines.append("当前没有需要动手的动作：无触发止损 / 止盈、无可买清单、无显著低估标的。")
    lines += ["────────────────", str(dec.get("note") or "不代下单。")]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 发送与入队
# --------------------------------------------------------------------------
def deliver_p0(hook, text):
    """P0 即时直发：不经队列，不等 2 秒轮询 / 5 分钟合并 / 4 秒节流。"""
    validate_url(hook)
    state, note = send_rich(hook, text, mention_all=True)
    return state, note


def enqueue(identity, kind, title, text):
    """P1/P2 追加到信息雷达 wecom_jobs，由雷达发送线程统一发出。"""
    created = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    con = sqlite3.connect(RADAR_DB, timeout=10)
    try:
        for i, part in enumerate(chunks(text)):
            con.execute(
                "INSERT OR IGNORE INTO wecom_jobs"
                "(identity,kind,title,content,created_at) VALUES(?,?,?,?,?)",
                (identity + ":" + str(i), kind, title, part, created))
        con.commit()
        return True
    finally:
        con.close()


# --------------------------------------------------------------------------
# 时段与去重
# --------------------------------------------------------------------------
def local_hm():
    n = datetime.datetime.now()
    return n.hour * 60 + n.minute


def in_session():
    n = datetime.datetime.now()
    if n.weekday() >= 5:
        return False
    return SESSION_START_HM <= local_hm() < SESSION_END_HM


def seconds_until_next_session():
    n = datetime.datetime.now()
    if in_session():
        return POLL_SECONDS
    if n.weekday() < 5 and local_hm() < SESSION_START_HM:
        target = datetime.datetime.combine(n.date(), datetime.time(9, 0))
    else:
        d = n.date() + datetime.timedelta(days=1)
        while d.weekday() >= 5:
            d += datetime.timedelta(days=1)
        target = datetime.datetime.combine(d, datetime.time(9, 0))
    return max(30, int((target - n).total_seconds()))


def _cond_key(x):
    """条件单去重键：标的 + 触发类型（买点/目标）。止损不进机会型推送。"""
    return "%s|%s" % (x.get("code") or "?", x.get("trigger") or "?")


def decision_hash(dec):
    payload = json.dumps(dec, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def has_decision_content(dec):
    return any(dec.get(k) for k in ("must", "later", "watch"))


# --------------------------------------------------------------------------
# 单轮主流程
# --------------------------------------------------------------------------
def run_once(dry_run=False, force=False, ignore_session=False):
    c = cfg()
    token = str(c.get("token") or "").strip()
    brief_url = str(c.get("brief_url") or DEFAULT_BRIEF_URL).strip()
    home = str(c.get("workbench_url") or DEFAULT_HOME_URL).strip()
    if not token:
        log("跳过：config.json 未配置 token")
        return False
    hook = webhook()
    if not hook:
        log("跳过：信息雷达未配置企微 webhook")
        return False
    try:
        brief = fetch_brief(token, brief_url)
    except Exception as e:
        log("brief 拉取失败：%s" % str(e)[:140])
        return False

    state = load_json(STATE_PATH, None) or blank_state()
    now = time.time()
    day = datetime.date.today().isoformat()
    urgent_all = [x for x in (brief.get("urgent") or [])
                  if x.get("level") in URGENT_LEVELS]
    tsig_all = [x for x in ((brief.get("t_signal") or {}).get("items") or [])
                if x.get("signal") in ("buy", "sell")]
    cond_all = [x for x in ((brief.get("cond") or {}).get("push_items") or [])
                if x.get("trigger") in ("buy", "target") and x.get("code")]
    cond_ok = bool((brief.get("cond") or {}).get("ok"))
    dec = brief.get("decision") or {}
    dh = decision_hash(dec)
    out = []

    # 交易日闸门：brief 用引擎节假日表，比本机 weekday 更准
    # --ignore-session 仅供 --dry-run 在周末/夜间验证消息内容，不影响正式发送
    if not brief.get("trade_day") and not (ignore_session and dry_run):
        log("休市（%s），本轮不推送" % (brief.get("closed_reason") or "非交易日"))
        if ignore_session and not dry_run:
            log("拒绝：--ignore-session 只允许与 --dry-run 同用")
        return False

    # 首次运行：把存量预警 / 存量做T信号静默播种，绝不补发历史消息
    # --force 只跳过播种（用于验证链路），仍把 boot_seeded 置位，避免下轮重复播种
    if not state.get("boot_seeded"):
        state["boot_seeded"] = True
        if not force:
            state["urgent"] = {x["code"]: {"level": x["level"], "at": now}
                               for x in urgent_all if x.get("code")}
            state["tsig"] = {x["code"]: {"signal": x["signal"], "at": now}
                             for x in tsig_all if x.get("code")}
            state["p0_day"] = {"%s|%s|%s" % (day, x["code"], x["level"]): now
                               for x in urgent_all if x.get("code")}
            state["cond"] = {_cond_key(x): {"at": now} for x in cond_all}
            state["cond_day"] = {day + "|" + _cond_key(x): now for x in cond_all}
            # 当日两个决策卡时点都标记为「已处理」，首启当天不补发，
            # 次日 09:25 起按正常节奏推；想立刻验证可用 --test / --force。
            state["decision"] = {"day": day, "pre_hash": dh,
                                 "post_hash": dh, "last_hash": dh}
            if not dry_run:
                save_state(state)
            log("首次运行静默播种：存量预警 %d 条 / 做T信号 %d 条 / 条件单 %d 条，不补发历史消息"
                % (len(urgent_all), len(tsig_all), len(cond_all)))
            return True

    # ---- P0：三类紧急，合并成一条，即时 @all ----
    if not brief.get("holds_ok"):
        log("持仓数据不可用（holds_ok=false），跳过 P0，避免用旧价误报")
    else:
        p0_day = state.setdefault("p0_day", {})
        prefix = day + "|"
        for k in list(p0_day):
            if not k.startswith(prefix):
                del p0_day[k]                      # 只保留当日，跨交易日重新计数
        fresh = []
        for x in urgent_all:
            code = x.get("code") or ""
            if not code:
                continue
            level = x.get("level") or "?"
            key = "%s%s|%s" % (prefix, code, level)
            prev = state["urgent"].get(code) or {}
            # 只有「先前确有记录且级别不同」才算级别变化；记录被恢复逻辑清空时
            # 属于「重新出现」，必须继续受当日去重约束，否则 trend 缓存抖动会绕过闸门。
            level_changed = bool(prev.get("level")) and prev.get("level") != level
            # 同一交易日、同标的、同级别只提醒一次；级别变化立即重推。
            # 不能只用 1 小时冷却：trend 来自 1 小时 TTL 缓存，缓存刷新会让它
            # 「消失→重现」，按冷却推会稳定每小时 @all 一次，把强提醒刷成噪音。
            if p0_day.get(key) and not level_changed:
                continue
            if level_changed or not prev.get("at") or now - float(prev["at"]) >= P0_COOLDOWN:
                fresh.append(x)
        alive = {x.get("code") for x in urgent_all}
        for code in list(state["urgent"].keys()):
            if code not in alive:
                lvl = (state["urgent"][code] or {}).get("level")
                del state["urgent"][code]
                # stop 是价格实时判定：真回到止损线上方后再次破位算新事件，当日可再推。
                # 当日出现过 stop 的标的（即使后来变成 cleared/trend）恢复时也要清key，
                # 否则历史 |stop 键会把「再次破位」误判成重复。
                # cleared / trend 属状态型，保留当日记录以免缓存抖动重复 @all。
                had_stop = (lvl == "stop" or any(
                    k.startswith("%s%s|" % (prefix, code)) and k.endswith("|stop")
                    for k in p0_day))
                if had_stop:
                    for k in list(p0_day):
                        if k.startswith("%s%s|" % (prefix, code)):
                            del p0_day[k]
        if fresh:
            text = format_p0(fresh, brief, home)
            if dry_run:
                out.append(("P0 直发 @all", text))
            else:
                st, note = deliver_p0(hook, text)
                log("P0 已发 %d 条：%s / %s" % (len(fresh), st, note))
                if st != "accepted":
                    log("P0 未被受理，不记当日去重，下轮继续重试")
                    return False
            for x in fresh:
                state["urgent"][x["code"]] = {"level": x["level"], "at": now}
                p0_day["%s%s|%s" % (prefix, x["code"], x["level"])] = now

    # ---- P1：做T信号新进入买/卖，入雷达队列 ----
    tsig_stale = bool((brief.get("t_signal") or {}).get("stale"))
    fresh_t = []
    for x in tsig_all:
        code = x.get("code") or ""
        if not code:
            continue
        prev = state["tsig"].get(code) or {}
        if prev.get("signal") != x.get("signal") or now - float(prev.get("at") or 0) >= P1_COOLDOWN:
            fresh_t.append(x)
    alive_t = {x.get("code") for x in tsig_all}
    for code in list(state["tsig"].keys()):
        if code not in alive_t:
            del state["tsig"][code]
    if fresh_t and not tsig_stale:
        text = format_p1(fresh_t, brief)
        ident = "ext-tsig-%s-%s" % (day, hashlib.sha256(
            "|".join(sorted(x["code"] + x["signal"] for x in fresh_t)).encode()).hexdigest()[:12])
        if dry_run:
            out.append(("P1 入队 ext_tsig", text))
        else:
            try:
                enqueue(ident, "ext_tsig", "做T信号 · %d 只" % len(fresh_t), text)
                log("P1 入队 %d 只" % len(fresh_t))
            except Exception as e:
                log("P1 入队失败：%s" % str(e)[:120])
                return False
        for x in fresh_t:
            state["tsig"][x["code"]] = {"signal": x["signal"], "at": now}
    elif fresh_t and tsig_stale:
        log("做T快照已过期（stale=true），本轮不推 P1")

    # ---- P1b：条件单触发（买点/目标达成），同交易日同标的同类型只推一次，入队不 @all ----
    if cond_ok:
        cd = state.setdefault("cond_day", {})
        prefix_c = day + "|"
        for k in list(cd):
            if not k.startswith(prefix_c):
                del cd[k]                       # 只保留当日，跨交易日重新计数
        fresh_c = []
        for x in cond_all:
            ck = _cond_key(x)
            if cd.get(prefix_c + ck):
                continue                        # 当日已推过同标的同触发类型，安静
            old = (state.get("cond") or {}).get(ck) or {}
            if not old.get("at") or now - float(old["at"]) >= P1_COOLDOWN:
                fresh_c.append(x)
        alive_c = {_cond_key(x) for x in cond_all}
        for ck in list((state.get("cond") or {}).keys()):
            if ck not in alive_c:
                del state["cond"][ck]           # 触发消失后清状态，价格再到位可重推
        if fresh_c:
            text = format_cond(fresh_c, brief)
            ident = "ext-cond-%s-%s" % (day, hashlib.sha256(
                "|".join(sorted(_cond_key(x) for x in fresh_c)).encode()).hexdigest()[:12])
            if dry_run:
                out.append(("P1 入队 ext_cond(条件单)", text))
            else:
                try:
                    enqueue(ident, "ext_cond", "条件单触发 · %d 只" % len(fresh_c), text)
                    log("P1 条件单入队 %d 只" % len(fresh_c))
                except Exception as e:
                    log("P1 条件单入队失败：%s" % str(e)[:120])
                    return False
            for x in fresh_c:
                state.setdefault("cond", {})[_cond_key(x)] = {"at": now}
                cd[prefix_c + _cond_key(x)] = now
    else:
        log("条件单数据不可用（cond.ok=false），本轮不推 P1b")

    # ---- P2：今日决策卡，每交易日 09:25 一次 + 15:10 结论变化补推 ----
    ds = state.setdefault("decision", blank_state()["decision"])
    if ds.get("day") != day:
        ds.clear()
        ds.update({"day": day, "pre_hash": None, "post_hash": None, "last_hash": dh})
    hm = local_hm()
    if hm >= DECISION_PRE_HM and ds.get("pre_hash") is None:
        if has_decision_content(dec):
            when = "盘前" if hm < DECISION_POST_HM else "盘中/盘后首次汇总"
            text = format_p2(dec, day, when)
            ident = "ext-decision-%s-pre" % day
            if dry_run:
                out.append(("P2 入队 ext_decision(盘前)", text))
            else:
                try:
                    enqueue(ident, "ext_decision", "今日决策卡 · %s 盘前" % day, text)
                    log("P2 盘前决策卡已入队")
                except Exception as e:
                    log("P2 入队失败：%s" % str(e)[:120])
        ds["pre_hash"] = dh
    elif hm >= DECISION_POST_HM and ds.get("post_hash") is None:
        if has_decision_content(dec) and dh != ds.get("pre_hash"):
            text = format_p2(dec, day, "收盘前结论变化补推")
            ident = "ext-decision-%s-post" % day
            if dry_run:
                out.append(("P2 入队 ext_decision(补推)", text))
            else:
                try:
                    enqueue(ident, "ext_decision", "今日决策卡 · %s 补推" % day, text)
                    log("P2 结论变化补推已入队")
                except Exception as e:
                    log("P2 补推入队失败：%s" % str(e)[:120])
        ds["post_hash"] = dh
    ds["last_hash"] = dh

    if dry_run:
        for label, text in out:
            print("\n===== %s =====" % label)
            print(text)
        if not out:
            print("\n[DRY-RUN] 本轮无新消息（全部被去重 / 冷却 / 时段规则拦下）")
        print("\n[DRY-RUN] 未发送、未入队、未写状态")
    else:
        save_state(state)
    return True


def send_test():
    hook = webhook()
    if not hook:
        log("测试跳过：信息雷达未配置企微 webhook")
        return
    text = ("【链路测试】投资工作台 → 信息雷达企微推送\n"
            "本条用于确认桥接器到企业微信群机器人的通路可用。\n"
            "正式消息分 P0 紧急（@all 即时）/ P1 做T信号 / P1b 条件单触发 / P2 今日决策卡。\n"
            + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    try:
        validate_url(hook)
        st, note = send(hook, text)
        log("测试消息：%s / %s" % (st, note))
        print("测试消息：%s / %s" % (st, note))
    except Exception as e:
        log("测试消息失败：%s" % str(e)[:140])


def main():
    args = sys.argv[1:]
    if "--test" in args:
        send_test()
        return
    if "--loop" in args:
        log("进入常驻推送模式：交易时段每 %d 秒，非交易时段静默" % POLL_SECONDS)
        while True:
            try:
                if in_session():
                    run_once()
                    wait = POLL_SECONDS
                else:
                    wait = seconds_until_next_session()
                    log("非交易时段静默，%d 秒后再检查" % wait)
                time.sleep(wait)
            except Exception as e:
                log("循环异常：%s" % str(e)[:140])
                time.sleep(POLL_SECONDS)
        return
    dry = "--dry-run" in args
    force = "--force" in args
    ignore = "--ignore-session" in args
    if ignore and not dry:
        print("--ignore-session 只允许与 --dry-run 同用，已忽略该开关")
        ignore = False
    run_once(dry_run=dry, force=force, ignore_session=ignore)


if __name__ == "__main__":
    main()
