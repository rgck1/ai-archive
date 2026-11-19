# -*- coding: utf-8 -*-
"""v108 线上核验：freshness API + 前端黄条 + 服务器直推底座。TAT 内联 b64 执行。"""
import os
import sys
import json
import time
import hmac
import hashlib
import base64
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
TAT = os.path.join(HERE, "tat.py")

REMOTE = r'''
import os, sys, json, time, hmac, hashlib
BASE = "https://wt.likeke.top/"
SECRET = "/opt/invest-workbench/.session_secret"
results = {}
# 1) API 直检（免登录白名单）
import urllib.request
try:
    d = json.load(urllib.request.urlopen(BASE + "api/freshness", timeout=15))
    results["api_ok"] = d.get("ok")
    results["api_rows"] = len(d.get("rows") or [])
    results["api_stale_count"] = d.get("stale_count")
    results["api_row_names"] = [r.get("name") for r in (d.get("rows") or [])]
except Exception as e:
    results["api_err"] = str(e)[:120]
# 2) server_notify 模块 & webhook 文件
results["notify_module"] = os.path.isfile("/opt/invest-workbench/server_notify.py")
results["hook_file_mode"] = oct(os.stat("/opt/invest-workbench/data/server_notify_webhook").st_mode & 0o777) if os.path.isfile("/opt/invest-workbench/data/server_notify_webhook") else "missing"
# 3) service 6 ExecStart + timer
try:
    svc = open("/etc/systemd/system/invest-workbench-v47-daily.service", encoding="utf-8").read()
    results["exec_count"] = svc.count("ExecStart=")
    results["notify_in_service"] = "server_notify.py --daily" in svc
except Exception as e:
    results["svc_err"] = str(e)[:80]
# 4) 真浏览器
with open(SECRET, encoding="utf-8") as fh:
    s = fh.read().strip()
p = "user|%d" % (int(time.time()) + 3600)
cv = p + "|" + hmac.new(s.encode(), p.encode(), hashlib.sha256).hexdigest()
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_cookies([{"name": "xq_sess", "value": cv, "url": BASE, "secure": True}])
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(BASE, wait_until="networkidle", timeout=60000)
        pg.wait_for_timeout(3000)
        results["pageerror"] = len(errs)
        results["pageerror_sample"] = errs[:2]
        results["fn_wbLoadFresh"] = pg.evaluate("typeof window.wbLoadFresh === 'function'")
        results["freshbar_dom"] = pg.evaluate("!!document.getElementById('wbFreshBar')")
        results["freshbar_hidden"] = pg.evaluate("document.getElementById('wbFreshBar')?.hidden")
        results["freshbar_items"] = pg.evaluate("(document.getElementById('wbFreshItems')?.textContent||'').slice(0,200)")
        results["sw_cache"] = pg.evaluate("""() => { try { return caches.keys().then?null:null; } catch(e){ return 'na'; } }""")
        b.close()
except Exception as e:
    results["browser_err"] = str(e)[:200]
print(json.dumps(results, ensure_ascii=False))
'''

def main():
    blob = base64.b64encode(REMOTE.encode("utf-8")).decode()
    cmd = ("echo %s | base64 -d > /tmp/v108chk.py && "
           "PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright /usr/bin/python3 /tmp/v108chk.py "
           "&& rm -f /tmp/v108chk.py") % blob
    p = subprocess.run([sys.executable, TAT, "run", "--timeout", "180", "--cmd", cmd],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=240)
    out = (p.stdout or "") + (p.stderr or "")
    print(out)

if __name__ == "__main__":
    main()
