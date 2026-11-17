#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
雪球组合净值 · 本机一次性补刷脚本  v1
================================================================
用途：云端服务器 IP 被雪球风控，净值停在 2026-10-26 不再更新。
      在你自己的电脑（住宅 IP，雪球不风控）上运行本脚本，抓取每个组合
      2026-10-20 至今的新净值，生成增量文件，再推回服务器重建业绩曲线。

为什么必须本机跑：
      雪球对云服务器 IP 做了风控（返回 301 反爬页，不带 Cookie 也过不去）。
      你本机的住宅 IP 不在风控名单里，登录态 Cookie 也能正常用。

前置准备：
      1) 浏览器登录 xueqiu.com
      2) 打开开发者工具(F12) → Network → 任意雪球请求 → 复制 Request Headers 里的
         Cookie 整行（形如 xq_a_token=xxx; xq_r_token=yyy; u=zzz; ...）
      3) 把 Cookie 整行粘进本目录的 xq_cookie.txt（只保留本文件，不要提交/发给别人）
         —— 也可用环境变量 XQ_COOKIE 代替

运行：
      python refresh_nav_local.py              # 抓全部 74 个组合
      python refresh_nav_local.py --only-core  # 只抓核心池 5 只（最快）
      python refresh_nav_local.py --push       # 抓完直接推回服务器（需 TAT 凭据）

产出：
      nav_delta.json         增量数据（本机）
      merge_nav_delta.sh     已内嵌增量的服务器合并脚本（可直接 python tat.py run --file 它）

安全：本脚本只把「日期→净值」这种公开行情写回服务器，绝不把你的 Cookie 推上去。
      推送的内容里不含任何凭据。
================================================================
"""
import os
import sys
import json
import time
import math
import datetime
import http.cookiejar
import urllib.request
import urllib.error
import urllib.parse
import base64
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CODES_FILE = os.path.join(BASE_DIR, "nav_codes.txt")
COOKIE_FILE = os.path.join(BASE_DIR, "xq_cookie.txt")
DELTA_FILE = os.path.join(BASE_DIR, "nav_delta.json")
MERGE_FILE = os.path.join(BASE_DIR, "merge_nav_delta.sh")

# 只保留这些雪球登录字段，其余忽略（避免污染会话）
COOKIE_KEYS = ("xq_a_token", "xq_r_token", "u", "xqat", "xq_id_token")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 核心池（观察源/业绩窗口真正用的 5 只）；其余 27 只在 watch 池也有展示
CORE_CODES = ["ZH3553296", "ZH3551808", "ZH3295404", "ZH3542293", "ZH3289755"]

# 增量窗口起点：最后已知净值日是 2026-10-26，往前多取 6 天做重叠保护
SINCE_DATE = "2026-10-20"

MIN_REQ_INTERVAL = 1.2          # 全局最小请求间隔（秒），压到接近真人浏览
_RE_MAIN = [0.0]


def _throttle():
    now = time.time()
    wait = _RE_MAIN[0] + MIN_REQ_INTERVAL - now
    if wait > 0:
        time.sleep(wait)
    _RE_MAIN[0] = time.time()


def _log(tag, msg):
    sys.stderr.write("[%s] %s: %s\n" % (datetime.datetime.now().strftime("%H:%M:%S"), tag, msg))
    sys.stderr.flush()


def is_rate_limit_text(txt):
    return bool(txt) and ("110017" in txt or "操作过于频繁" in txt)


class XQClient:
    """极简版雪球客户端：首页拿会话 Cookie → 注入登录 Cookie → 带限流 GET。"""

    def __init__(self):
        self.cj = http.cookiejar.CookieJar()
        handlers = [urllib.request.HTTPCookieProcessor(self.cj)]
        handlers.insert(0, urllib.request.ProxyHandler({}))   # 不用系统代理，住宅 IP 更稳
        self.opener = urllib.request.build_opener(*handlers)

    def add_user_cookie(self, cookie_str):
        kept = {}
        for part in (cookie_str or "").split(";"):
            part = part.strip()
            if "=" not in part:
                continue
            k, v = part.split("=", 1)
            k, v = k.strip(), v.strip()
            if k.lower() in COOKIE_KEYS and v:
                kept[k] = v
        for k, v in kept.items():
            try:
                self.cj.set_cookie(http.cookiejar.Cookie(
                    0, k, v, None, False, ".xueqiu.com", True, True,
                    "/", True, False, None, False, None, None, {}))
            except Exception as e:
                _log("cookie", "字段 %s 注入失败：%s" % (k, str(e)[:80]))
        return kept

    def bootstrap(self):
        try:
            req = urllib.request.Request("https://xueqiu.com/",
                headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
            _throttle()
            with self.opener.open(req, timeout=15) as r:
                r.read()
        except Exception as e:
            _log("bootstrap", "首页会话建立失败（可忽略，继续）：%s" % str(e)[:100])

    def get(self, url):
        _throttle()
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://xueqiu.com/",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        with self.opener.open(req, timeout=20) as r:
            data = r.read()
            return data.decode("utf-8", "replace"), r.headers.get("Content-Type", "")


def _load_codes(only_core):
    if only_core:
        return list(CORE_CODES)
    if not os.path.isfile(CODES_FILE):
        _log("codes", "未找到 %s，改用核心池 5 只" % CODES_FILE)
        return list(CORE_CODES)
    with open(CODES_FILE, encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip() and ln.strip().startswith("ZH")]


def _load_existing_delta():
    """读取已有的 nav_delta.json，用于 --append 增量累积（避免分批抓时覆盖）。"""
    if not os.path.isfile(DELTA_FILE):
        return {}, {}, []
    try:
        d = json.load(open(DELTA_FILE, encoding="utf-8"))
        return (d.get("deltas") or {}, d.get("meta") or {}, d.get("fails") or [])
    except Exception as e:
        _log("append", "读取已有 delta 失败，按空处理：%s" % str(e)[:80])
        return {}, {}, []


def _load_cookie():
    raw = os.environ.get("XQ_COOKIE", "").strip()
    if not raw and os.path.isfile(COOKIE_FILE):
        raw = open(COOKIE_FILE, encoding="utf-8").read().strip()
    if not raw:
        sys.stderr.write(
            "\n[x] 没找到 Cookie。请把雪球登录 Cookie 整行写进 xq_cookie.txt，\n"
            "    或设置环境变量 XQ_COOKIE。\n"
            "    获取方式：浏览器登录 xueqiu.com → F12 → Network → 复制 Request Headers 的 Cookie。\n")
        sys.exit(2)
    return raw


def _norm_date(d):
    """雪球 nav_daily 的 date 一般是 'YYYY-MM-DD' 字符串；兼容时间戳。"""
    if isinstance(d, str):
        s = d.strip()
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            return s[:10]
        try:
            d = float(s)
        except ValueError:
            return None
    if isinstance(d, (int, float)):
        try:
            if d > 1e12:
                d = d / 1000.0
            return datetime.date.fromtimestamp(d).isoformat()
        except Exception:
            return None
    return None


def _clean_points(lst):
    out = []
    for p in lst or []:
        if not isinstance(p, dict):
            continue
        dd = _norm_date(p.get("date"))
        if not dd:
            continue
        try:
            v = float(p.get("value"))
        except (TypeError, ValueError):
            continue
        out.append({"date": dd, "value": v, "percent": p.get("percent")})
    try:
        out.sort(key=lambda x: x["date"])
    except Exception:
        pass
    return out


def _fetch_window(client, code, since_ms, until_ms):
    url = ("https://xueqiu.com/cubes/nav_daily/all.json?cube_symbol=%s"
           "&since=%d&until=%d" % (code, since_ms, until_ms))
    try:
        txt, ct = client.get(url)
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            pass
        if "400016" in body or is_rate_limit_text(body) or "登录" in body:
            return None, "NEED_COOKIE"
        if is_rate_limit_text(txt if False else body):
            return None, "RATE_LIMITED"
        return None, "HTTP %s" % e.code
    except Exception as e:
        return None, str(e)[:120]
    if not ct or "json" not in ct.lower():
        return None, "BLOCKED"        # 拿到反爬页而非 JSON：被风控
    try:
        j = json.loads(txt)
    except Exception:
        return None, "BADFORMAT"
    if isinstance(j, dict):
        if j.get("error_code") == "400016":
            return None, "NEED_COOKIE"
        if is_rate_limit_text(txt):
            return None, "RATE_LIMITED"
        return None, "接口返回 %s" % (j.get("error_code") or "异常")
    if not (isinstance(j, list) and j and isinstance(j[0], dict) and j[0].get("list")):
        return None, "BADFORMAT"
    info = j[0]
    pts = _clean_points(info.get("list"))
    name = info.get("name") or ""
    return {"name": name, "points": pts}, None


def _scrape(client, codes):
    since_dt = datetime.datetime.combine(
        datetime.date.fromisoformat(SINCE_DATE), datetime.time.min)
    until_ms = int(time.time() * 1000)
    since_ms = int(since_dt.timestamp() * 1000)

    deltas = {}
    meta = {}
    fails = []
    for i, code in enumerate(codes, 1):
        info, err = _fetch_window(client, code, since_ms, until_ms)
        if err:
            # 关键错误：明确停手，避免雪球把 IP 拉黑
            if err == "BLOCKED":
                _log("abort", "第 %d/%d 个 %s 被风控拦截（BLOCKED）。本机住宅 IP 理应不被拦，"
                      "若反复出现请检查网络是否走了代理/公司出口。已抓到的先保留。"
                      % (i, len(codes), code))
                break
            if err == "NEED_COOKIE":
                _log("abort", "Cookie 失效（NEED_COOKIE）。请重新从浏览器复制最新 Cookie 到 xq_cookie.txt。")
                break
            if err == "RATE_LIMITED":
                _log("ratelimit", "触发雪球限流(110017)，暂停 60s 后继续…")
                time.sleep(60)
                info, err = _fetch_window(client, code, since_ms, until_ms)
                if err:
                    _log("skip", "%s 仍失败（%s），跳过" % (code, err))
                    fails.append({"code": code, "err": err})
                    continue
            else:
                _log("skip", "%s 失败（%s），跳过，继续下一个" % (code, err))
                fails.append({"code": code, "err": err})
                continue
        pts = info["points"]
        if pts:
            deltas[code] = pts
            meta[code] = {"name": info["name"], "new_points": len(pts),
                          "last_date": pts[-1]["date"]}
            _log("ok", "%s %s 取到 %d 点，最新 %s" % (code, info["name"], len(pts), pts[-1]["date"]))
        else:
            _log("empty", "%s 无新净值（可能已关闭/停牌）" % code)
            fails.append({"code": code, "err": "EMPTY"})
    return deltas, meta, fails


def _build_merge_shell(delta_b64):
    return r'''#!/bin/bash
# 自动生成：雪球净值增量合并 + 重建业绩曲线 + 重启服务（由 refresh_nav_local.py 产出）
DELTA_B64="__DELTA_B64__"
echo "$DELTA_B64" | base64 -d > /tmp/nav_delta.json
python3 - <<'PY'
import json, os, time, pwd, grp
delta = json.load(open("/tmp/nav_delta.json", encoding="utf-8"))
DATA = "/opt/invest-workbench/data"
deltas = delta.get("deltas") or {}
try:
    uid = pwd.getpwnam("invest").pw_uid
    gid = grp.getgrnam("invest").gr_gid
except Exception:
    uid = gid = 0
n_merged = 0
n_skip = 0
for code, pts in deltas.items():
    if not pts:
        n_skip += 1
        continue
    path = os.path.join(DATA, "nav_%s.json" % code)
    d = {}
    if os.path.isfile(path):
        try:
            d = json.load(open(path, encoding="utf-8"))
        except Exception:
            d = {}
    old = {p["date"]: p for p in (d.get("points") or []) if isinstance(p, dict) and p.get("date")}
    for p in pts:
        if isinstance(p, dict) and p.get("date"):
            old[p["date"]] = p
    d["points"] = sorted(old.values(), key=lambda x: x["date"])
    if not d.get("name") and isinstance(pts, list) and pts and pts[0].get("name"):
        d["name"] = pts[0]["name"]
    d["ts"] = time.time()
    d.pop("force_stale", None)
    d.pop("ts_real", None)
    tmp = path + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, path)
    try:
        os.chown(path, uid, gid)
    except Exception:
        pass
    n_merged += 1
print("MERGED=%d SKIP=%d" % (n_merged, n_skip))
PY
    echo "=== 重建 pool_daily 全历史 ==="
cd /opt/invest-workbench/engine && XQ_CACHE_DIR=/opt/invest-workbench/data python3 server.py --rebuild-pool-daily
echo "=== 重启服务（清内存净值缓存）==="
systemctl restart invest-workbench
sleep 3
systemctl is-active invest-workbench || echo "is-active 暂未返回 active，请稍后自查"
echo "DONE"
'''.replace("__DELTA_B64__", delta_b64)


def _emit(deltas, meta, fails, base=None):
    """写 delta。base 为已有 delta（--append 时的累积基线），本次结果覆盖同 code。"""
    if base:
        all_d = dict(base.get("deltas") or {})
        all_m = dict(base.get("meta") or {})
        all_f = list(base.get("fails") or [])
        done = set(all_d.keys())
        all_d.update(deltas)
        all_m.update(meta)
        # 已成功的 code 从 fails 里移除
        all_f = [f for f in all_f if f.get("code") not in done]
        deltas, meta, fails = all_d, all_m, all_f
    delta = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "since": SINCE_DATE,
        "until": datetime.date.today().isoformat(),
        "deltas": deltas,
        "meta": meta,
        "fails": fails,
    }
    with open(DELTA_FILE, "w", encoding="utf-8") as f:
        json.dump(delta, f, ensure_ascii=False, indent=2)
    if deltas:
        b64 = base64.b64encode(
            json.dumps(deltas, ensure_ascii=False).encode("utf-8")).decode("ascii")
        shell = _build_merge_shell(b64)
        with open(MERGE_FILE, "w", encoding="utf-8") as f:
            f.write(shell)
        os.chmod(MERGE_FILE, 0o755)
    return delta


def _push():
    if not os.path.isfile(MERGE_FILE):
        sys.stderr.write("[x] 没有可推送的 %s，先跑抓取（不带 --push）\n" % MERGE_FILE)
        return 1
    env_ok = bool(os.environ.get("TENCENTCLOUD_SECRET_ID") and os.environ.get("TENCENTCLOUD_SECRET_KEY"))
    if not env_ok:
        sys.stderr.write(
            "[!] 本机未设置 TENCENTCLOUD_SECRET_ID/KEY，无法直接推送。\n"
            "    二选一：\n"
            "    a) 设置这两个环境变量后重试：python refresh_nav_local.py --push\n"
            "    b) 把本目录的 merge_nav_delta.sh 交给 A，由 A 用 TAT 代推（无需你配云凭据）\n")
        return 1
    _log("push", "经 TAT 推送合并脚本到服务器并执行…")
    r = subprocess.run([sys.executable, "tat.py", "run", "--file", MERGE_FILE],
                       cwd=BASE_DIR)
    return r.returncode


def _argv_val(flag, default=None):
    """取 --flag VALUE 形式的值。"""
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def main():
    only_core = "--only-core" in sys.argv
    do_push = "--push" in sys.argv
    do_append = "--append" in sys.argv
    batch_size = int(_argv_val("--batch", "0") or 0)   # 0=不限；>0=每批最多抓 N 个未抓的 code
    codes = _load_codes(only_core)
    base = {"deltas": {}, "meta": {}, "fails": []}
    if do_append:
        d, m, f = _load_existing_delta()
        base = {"deltas": d, "meta": m, "fails": f}
        done = set(d.keys())
        codes = [c for c in codes if c not in done]
        _log("append", "已有 %d 个，本批待抓 %d 个" % (len(done), len(codes)))
    if batch_size > 0:
        codes = codes[:batch_size]
        _log("batch", "本批上限 %d 个" % batch_size)
    _log("start", "准备抓取 %d 个组合（since=%s）" % (len(codes), SINCE_DATE))
    if not codes:
        _log("skip", "没有待抓的 code（可能已全部抓取）")
        if do_push and os.path.isfile(MERGE_FILE):
            return _push()
        return 0

    client = XQClient()
    cookie_raw = _load_cookie()
    kept = client.add_user_cookie(cookie_raw)
    _log("cookie", "注入字段：%s" % (", ".join(sorted(kept)) or "（空，请检查 Cookie）"))
    if not kept:
        sys.stderr.write("[x] Cookie 里没有可用的雪球登录字段，请确认复制的是完整 Cookie 行\n")
        sys.exit(2)
    client.bootstrap()

    # 连通性自检：先抓第一个，确认不是 BLOCKED/NEED_COOKIE 再继续，避免白跑
    probe = codes[0]
    info, err = _fetch_window(client, probe,
        int(datetime.datetime.combine(datetime.date.fromisoformat(SINCE_DATE), datetime.time.min).timestamp()*1000),
        int(time.time()*1000))
    if err == "BLOCKED":
        _log("abort", "连通性自检失败：被风控(BLOCKED)。本机住宅 IP 不应被拦，请确认没走代理；终止。")
        sys.exit(3)
    if err == "NEED_COOKIE":
        _log("abort", "连通性自检失败：Cookie 无效(NEED_COOKIE)。请更新 xq_cookie.txt；终止。")
        sys.exit(3)
    if err == "RATE_LIMITED":
        _log("ratelimit", "自检即遇限流，暂停 60s 后继续")
        time.sleep(60)
    elif err:
        _log("warn", "自检异常(%s)，仍尝试继续" % err)

    deltas, meta, fails = _scrape(client, codes)
    delta = _emit(deltas, meta, fails, base=base if do_append else None)
    total = len(delta["deltas"])
    _log("done", "累计 %d 个 / 本批成功 %d 个 / 失败 %d 个 / 累计净值点 %d 个"
         % (total, len(deltas), len(fails), sum(len(v) for v in delta["deltas"].values())))
    if delta["deltas"] and os.path.isfile(MERGE_FILE):
        _log("ready", "已生成 %s（含累计 %d 个），可推送" % (MERGE_FILE, total))
    if do_push:
        return _push()
    return 0


if __name__ == "__main__":
    sys.exit(main())
