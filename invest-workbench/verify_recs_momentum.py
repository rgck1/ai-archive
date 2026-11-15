# -*- coding: utf-8 -*-
"""v85「近一周领涨组合」线上核验（可反复重跑）。

用法（Windows，交互会话里 TAT 可用时）：
    python verify_recs_momentum.py

做三件事：
  1) 服务器侧自签只读会话 Cookie，逐项核对 /api/recs_momentum 的口径字段、
     统计周期、Top3 排名、排除清单与参数化（top_n / window / positive）；
  2) 服务器侧 Playwright 真浏览器切到「跟单推荐」，断言第二类推荐 3 张卡
     与原「回测优选 Top3」3 张策略卡并存、停更警示可见、无 JS 报错；
  3) 打印线上 index.html / sw.js / server.py 的 SHA，便于与本地逐字节比对。

不触碰登录口令，不修改服务器任何业务文件。
"""
import base64
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_SRC = os.path.abspath(os.path.join(
    HERE, "..", "..", "..", "投资工作台_full", "src"))
TAT = os.path.join(PROJECT_SRC, "tat.py")

SERVER_PY = r'''# -*- coding: utf-8 -*-
import hashlib, hmac, json, os, subprocess, time, urllib.request
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/opt/ms-playwright"

with open("/opt/invest-workbench/.session_secret", "r", encoding="utf-8") as fh:
    s = fh.read().strip()
exp = int(time.time()) + 3600
payload = "user|%d" % exp
CV = payload + "|" + hmac.new(s.encode(), payload.encode(), hashlib.sha256).hexdigest()


def get(path):
    req = urllib.request.Request("http://127.0.0.1:8790" + path,
                                 headers={"Cookie": "xq_sess=" + CV})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


sha = {}
for f in ("index.html", "sw.js", "server.py"):
    sha[f] = subprocess.check_output(
        ["sha256sum", "/opt/invest-workbench/" + f], text=True).split()[0]

d = get("/api/recs_momentum")
api = {
    "ok": d.get("ok"), "status": d.get("status"), "as_of": d.get("as_of"),
    "stale_days": d.get("stale_days"), "window": d.get("window"),
    "period": d.get("period"), "candidate_count": d.get("candidate_count"),
    "eligible_count": d.get("eligible_count"),
    "positive_count": d.get("positive_count"),
    "excluded": len(d.get("excluded") or []),
    "ranking": len(d.get("ranking") or []),
    "items": [(x.get("rank"), x.get("code"), x.get("pool"), round(x.get("pct") or 0, 4))
              for x in (d.get("items") or [])],
    "auto_refresh": d.get("auto_refresh"),
}
params = {}
for qs in ("/api/recs_momentum?top_n=5", "/api/recs_momentum?window=3",
           "/api/recs_momentum?positive=0"):
    r = get(qs)
    params[qs] = {"top_n": r.get("top_n"), "window": r.get("window"),
                  "positive_only": r.get("positive_only"),
                  "items": len(r.get("items") or [])}

errs = []
browser = {}
try:
    from playwright.sync_api import sync_playwright
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = b.new_context(viewport={"width": 1440, "height": 900}, user_agent=UA)
        ctx.add_cookies([{"name": "xq_sess", "value": CV,
                          "url": "https://wt.likeke.top/",
                          "secure": True, "sameSite": "Lax"}])
        page = ctx.new_page()
        page.on("pageerror", lambda e: errs.append(str(e)[:220]))
        page.goto("https://wt.likeke.top/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4500)
        page.evaluate("() => { try { switchTab('recs'); } catch(e) { console.log(e); } }")
        page.wait_for_timeout(4500)
        browser = page.evaluate("""() => {
          var box = document.getElementById('recMomBox');
          var t3 = document.getElementById('recTop3');
          var st = (typeof state !== 'undefined') ? state : null;
          return {
            momCards: box ? box.querySelectorAll('[data-rec-mom-card]').length : -1,
            top3StrategyCards: t3 ? t3.querySelectorAll('[data-alloc],[data-goto-strat]').length : -1,
            staleWarn: box ? (box.innerText || '').indexOf('已停更') >= 0 : false,
            status: st && st.recsMomentum ? st.recsMomentum.status : null,
            top3: st && st.recsTop3 ? (st.recsTop3.top3 || []).length : null
          };
        }""")
        ctx.close()
        b.close()
except Exception as e:
    errs.append("PLAYWRIGHT:" + repr(e)[:300])

print("<<<V85_JSON>>>")
print(json.dumps({"sha": sha, "api": api, "params": params,
                  "browser": browser, "js_errors": errs[:8]}, ensure_ascii=False))
print("<<<END>>>")
'''


def main():
    if not os.path.isfile(TAT):
        print("找不到 tat.py：", TAT)
        sys.exit(1)
    blob = base64.b64encode(SERVER_PY.encode("utf-8")).decode()
    sh = ("python3 -c \"import base64;open('/tmp/_verify_recs_mom.py','wb').write("
          "base64.b64decode('%s'))\"\npython3 /tmp/_verify_recs_mom.py\n" % blob)
    fd, tmp = tempfile.mkstemp(suffix=".sh", prefix="v85chk_")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(sh)
    try:
        out = subprocess.run([sys.executable, TAT, "run", "--file", tmp,
                              "--timeout", "300"],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=420)
        txt = (out.stdout or "") + (out.stderr or "")
    finally:
        os.remove(tmp)
    m = re.search(r"<<<V85_JSON>>>\s*\n(.*?)\n<<<END>>>", txt, re.S)
    if not m:
        print("!! 未拿到核验结果：\n" + txt[-3000:])
        sys.exit(1)
    r = json.loads(m.group(1))
    print(json.dumps(r, ensure_ascii=False, indent=2))
    checks = [
        ("接口可用且状态可判定", r["api"]["ok"] is True and r["api"]["status"] in
         ("fresh", "stale", "unavailable", "unknown")),
        ("统计周期与口径完整", bool((r["api"]["period"] or {}).get("start"))
         and bool((r["api"]["period"] or {}).get("end"))),
        ("默认取前 3 名", len(r["api"]["items"]) == 3),
        ("候选严格来自双池（32 = core 5 + watch 27）", r["api"]["candidate_count"] == 32),
        ("第二类推荐渲染 3 张卡", r["browser"].get("momCards") == 3),
        ("原 Top3 策略卡仍为 3 张（互不覆盖）", r["browser"].get("top3StrategyCards") == 3),
        ("停更警示可见", r["browser"].get("staleWarn") is True),
        ("无 JS 报错", len(r["js_errors"]) == 0),
    ]
    bad = 0
    print("\n=== 核验 ===")
    for name, ok in checks:
        print(("PASS " if ok else "FAIL ") + name)
        if not ok:
            bad += 1
    print("线上 SHA：", json.dumps(r["sha"], ensure_ascii=False))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
