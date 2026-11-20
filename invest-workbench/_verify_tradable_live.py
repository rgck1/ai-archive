# -*- coding: utf-8 -*-
"""领涨组合「可交易性过滤」线上核验：API 字段 + 真浏览器卡片渲染。TAT 内联 b64 执行。"""
import os
import sys
import time
import hmac
import hashlib
import base64
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
TAT = os.path.join(HERE, "tat.py")

REMOTE = r'''
import os, sys, json, time, hmac, hashlib, urllib.request
BASE = "https://wt.likeke.top/"
SECRET = "/opt/invest-workbench/.session_secret"
results = {}
# 1) API 直检（带只读会话）
with open(SECRET, encoding="utf-8") as fh:
    s = fh.read().strip()
p = "user|%d" % (int(time.time()) + 3600)
cv = p + "|" + hmac.new(s.encode(), p.encode(), hashlib.sha256).hexdigest()
try:
    req = urllib.request.Request(BASE + "api/recs_momentum", headers={"Cookie": "xq_sess=" + cv})
    d = json.load(urllib.request.urlopen(req, timeout=20))
    items = d.get("items") or []
    results["api_ok"] = d.get("ok")
    results["api_as_of"] = d.get("as_of")
    results["api_tradable_excluded"] = d.get("tradable_excluded")
    results["api_top_codes"] = [x.get("code") for x in items]
    results["api_all_have_holdings"] = all(isinstance(x.get("tradable_holdings"), list) and x.get("tradable_holdings") for x in items)
    results["api_wangyidao_excluded"] = not any(x.get("code") == "ZH3289755" for x in (d.get("ranking") or []))
    results["api_method_has_gate"] = "≤65元" in (d.get("method") or "") and "高价股" in (d.get("method") or "")
    results["api_min"] = d.get("tradable_min")
    results["api_price_excluded"] = d.get("price_excluded")
    results["api_max_price"] = d.get("max_price")
    results["api_songfa_excluded"] = not any(x.get("code") == "ZH2237465" for x in (d.get("ranking") or []))
    results["api_all_have_price_field"] = all("price_affordable_ratio" in x for x in items)
    results["api_top_all_cheap"] = all((x.get("price_affordable_ratio") == 100.0) for x in items)
except Exception as e:
    results["api_err"] = str(e)[:150]
# 2) 真浏览器：切到跟单推荐，检查卡片显示可买持仓
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
        pg.wait_for_timeout(2500)
        try:
            pg.evaluate("switchTab('recs')")
            pg.wait_for_timeout(1500)
        except Exception as e:
            results["switch_err"] = str(e)[:100]
        results["pageerror"] = len(errs)
        results["pageerror_sample"] = errs[:2]
        results["card_count"] = pg.evaluate("document.querySelectorAll('[data-rec-mom-card]').length")
        txt = pg.evaluate("(document.getElementById('recMomBox')||{}).textContent||''")
        results["has_buyable_label"] = "可买持仓" in txt
        results["has_exclude_count"] = "买不了剔除" in txt
        results["has_price_exclude"] = "太贵剔除" in txt
        results["has_price_line"] = "单价 ≤65元" in txt
        results["has_etf_exempt"] = "基金免检" in txt
        results["card_has_stock_code"] = "SH600584" in txt or "SH601058" in txt
        results["sub_snippet"] = txt[:260].replace("\n", " ")
        b.close()
except Exception as e:
    results["browser_err"] = str(e)[:200]
print(json.dumps(results, ensure_ascii=False))
'''


def main():
    blob = base64.b64encode(REMOTE.encode("utf-8")).decode()
    cmd = ("echo %s | base64 -d > /tmp/tradchk.py && "
           "PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright /usr/bin/python3 /tmp/tradchk.py "
           "&& rm -f /tmp/tradchk.py") % blob
    proc = subprocess.run([sys.executable, TAT, "run", "--timeout", "180", "--cmd", cmd],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=240)
    print((proc.stdout or "") + (proc.stderr or ""))


if __name__ == "__main__":
    main()
