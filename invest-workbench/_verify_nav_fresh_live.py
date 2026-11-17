# -*- coding: utf-8 -*-
"""净值刷新后线上核验：业绩曲线数据日推进到 2026-11-16 + 真浏览器渲染无报错。

复用 _verify_poolchart_live.py 的 TAT + 服务器 Playwright + 自签只读会话套路。
"""
import base64
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

SERVER_PY = r'''# -*- coding: utf-8 -*-
import os, hashlib, hmac, json, time
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/opt/ms-playwright"
from playwright.sync_api import sync_playwright

with open("/opt/invest-workbench/.session_secret", "r", encoding="utf-8") as fh:
    s = fh.read().strip()
exp = int(time.time()) + 3600
payload = "user|%d" % exp
CV = payload + "|" + hmac.new(s.encode(), payload.encode(), hashlib.sha256).hexdigest()

R = {}
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
    ctx = browser.new_context(viewport={"width": 1280, "height": 1000})
    ctx.add_cookies([
        {"name": "xq_sess", "value": CV, "url": "https://wt.likeke.top/", "secure": True, "sameSite": "Lax"},
        {"name": "xq_sess", "value": CV, "url": "http://127.0.0.1:8790/", "secure": False},
    ])
    page = ctx.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)[:200]))
    try:
        page.goto("https://wt.likeke.top/", wait_until="domcontentloaded", timeout=30000)
    except Exception:
        page.goto("http://127.0.0.1:8790/", wait_until="domcontentloaded", timeout=30000)
    try:
        page.wait_for_function("typeof state !== 'undefined' && state.perf && state.perf.dates && state.perf.dates.length > 0", timeout=75000)
    except Exception as e:
        R["wait_err"] = str(e)[:120]
    page.wait_for_timeout(1200)
    R["state"] = page.evaluate("""() => {
      var p = (typeof state !== 'undefined') ? state.perf : null;
      return { dates: p&&p.dates?p.dates.length:0,
               from: p?p.from:null, to: p?p.to:null,
               lastDate: (p&&p.dates&&p.dates.length)?p.dates[p.dates.length-1]:null,
               perfDays: (p&&p.perf&&p.perf.days)||0,
               w1: (p&&p.perf&&p.perf.w1) };
    }""")
    # 切到业绩页并画曲线
    try:
        page.evaluate("() => switchTab('perftrack')")
        page.wait_for_timeout(1600)
        page.evaluate("() => { try { paintPoolChart('perf'); } catch(e){} }")
        page.wait_for_timeout(600)
    except Exception as e:
        R["switch_err"] = str(e)[:120]
    R["pix"] = page.evaluate("""() => {
      var cv=document.getElementById('poolChartPerf');
      if(!cv) return {missing:true};
      // poolChartPerf 可能是容器，里面才是 canvas
      if(typeof cv.getContext !== 'function') cv = cv.querySelector('canvas');
      if(!cv || typeof cv.getContext !== 'function') return {missing:true, tag:cv?cv.tagName:'none'};
      try {
        var ctx=cv.getContext('2d');var d=ctx.getImageData(0,0,cv.width,cv.height).data;
        var n=0;for(var i=0;i<d.length;i+=4){if(d[i+3]>0)n++;}
        return {w:cv.width,h:cv.height,opaque:n};
      } catch(e) { return {err:String(e).slice(0,80)}; }
    }""")
    R["errors"] = errs
    ctx.close(); browser.close()

print("<<<FRESH_JSON>>>")
print(json.dumps(R, ensure_ascii=False))
print("<<<END>>>")
'''


def tat(args, timeout=600):
    p = subprocess.run([sys.executable, os.path.join(HERE, "tat.py"), "run"] + args,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    return (p.stdout or "") + (p.stderr or "")


def main():
    blob = base64.b64encode(SERVER_PY.encode("utf-8")).decode()
    sh = ("python3 -c \"import base64;open('/tmp/_navfresh.py','wb').write("
          "base64.b64decode('%s'))\"\n"
          "PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright python3 /tmp/_navfresh.py\n" % blob)
    fd, tmp = tempfile.mkstemp(suffix=".sh", prefix="navfresh_")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(sh)
    print("==> 上传并执行服务器侧 Playwright 数据新鲜度核验")
    out = tat(["--file", tmp, "--timeout", "400"], timeout=600)
    os.remove(tmp)
    m = re.search(r"<<<FRESH_JSON>>>\s*\n(.*?)\n<<<END>>>", out, re.S)
    if not m:
        print("!! 未拿到结果，原始输出：\n" + out[-3000:])
        sys.exit(1)
    r = json.loads(m.group(1))
    print(json.dumps(r, ensure_ascii=False, indent=2))

    st = r.get("state") or {}
    pix = r.get("pix") or {}
    checks = [
        ("state.perf 有数据", (st.get("dates") or 0) > 100),
        ("数据日推进到 2026-11-16", st.get("to") == "2026-11-16" and st.get("lastDate") == "2026-11-16"),
        ("pool_daily 762 天", st.get("perfDays") == 762),
        ("业绩曲线画布有像素", (pix.get("opaque") or 0) > 500 and (pix.get("w") or 0) > 100),
        ("零 pageerror", len(r.get("errors") or []) == 0),
    ]
    print("\n=== 核验 ===")
    npass = 0
    for name, ok in checks:
        print(("  PASS " if ok else "  FAIL ") + name)
        npass += 1 if ok else 0
    print("结果: %d/%d PASS" % (npass, len(checks)))
    return 0 if npass == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
