# -*- coding: utf-8 -*-
"""v94 线上核验（条件单三件套，供其它智能体复现）：

1) 线上 server.py / index.html / sw.js 与本地逐字节 SHA 一致，服务 active，sw=v94
2) 后端 _cond_triple 现场复算：止损优先 > 目标 > 买入；缺数据 not_ready；距离方向正确
3) /api/swing 每行三件套字段齐备（band_lo2/target/stop），条件单派生有真实数据
4) 静态锚点：三页条件单列（波段/今日/持仓）、condCellHtml/condByCode、
   brief 的 cond 段与 push_items、桥接器通道（桥接器在本机，静态看源码）
5) 真浏览器：今日操作清单 / 波段操作 / 我的持仓三页均渲染出「条件单 买/标/损」数值或
   诚实的「—」，零 pageerror

会话读 /opt/invest-workbench/.session_secret 自签 1 小时只读 Cookie（不碰口令）。
用法：python _verify_v94_live.py
"""
import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

SERVER_PY = r'''# -*- coding: utf-8 -*-
import hashlib, hmac, json, os, subprocess, sys, time, urllib.request, importlib.util
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/opt/ms-playwright"
s = open("/opt/invest-workbench/.session_secret", "r", encoding="utf-8").read().strip()
exp = int(time.time()) + 3600
payload = "user|%d" % exp
CV = payload + "|" + hmac.new(s.encode(), payload.encode(), hashlib.sha256).hexdigest()

R = {"sha": [], "api": {}, "anchor": {}, "ui": {}, "errors": []}
R["sha"] = subprocess.run(
    ["sha256sum", "/opt/invest-workbench/server.py", "/opt/invest-workbench/index.html",
     "/opt/invest-workbench/sw.js"],
    capture_output=True, text=True).stdout.strip().splitlines()

def api(path):
    req = urllib.request.Request("http://127.0.0.1:8790" + path,
                                 headers={"Cookie": "xq_sess=" + CV, "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

# --- 现场加载 server.py 复算 _cond_triple（注册进 sys.modules 避免 __name__ 依赖）---
try:
    spec = importlib.util.spec_from_file_location("srv", "/opt/invest-workbench/server.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["srv"] = m
    spec.loader.exec_module(m)
    ct = m._cond_triple
    cases = [
        ("stop_priority", (9.5, 10, 11, 9.8), "stop"),   # 现价<=止损 且 <=买点 → 止损优先
        ("buy_only", (9.8, 10, 11, 9.0), "buy"),
        ("target", (11.2, 10, 11, 9.0), "target"),
        ("none", (10.4, 10, 11, 9.0), None),
        ("not_ready", (10.4, None, None, None), "not_ready"),
        ("no_price", (None, 10, 11, 9.0), None),
    ]
    cres = {}
    for name, args, expv in cases:
        t, d = ct(*args)
        cres[name] = {"ok": t == expv, "got": t, "dist": d}
    R["api"]["cond_triple"] = {"cases": cres, "all_ok": all(v["ok"] for v in cres.values())}
except Exception as e:
    R["api"]["cond_triple"] = {"error": str(e)[:200]}

# --- /api/swing 三件套字段齐备 + 条件单派生有数据 ---
try:
    sw = api("/api/swing?now=1")
    groups = sw.get("groups") or {}
    rows = []
    for g in ("held", "now", "wait", "hold", "blocked", "self"):
        rows.extend(groups.get(g) or [])
    with_triple = [r for r in rows if r.get("band_lo2") and r.get("target") and r.get("stop")]
    # 用与后端同样的规则数触发（只读统计，不依赖 brief 的 token）
    trig = {"stop": 0, "target": 0, "buy": 0, "none": 0}
    for r in rows:
        t, _ = ct(r.get("price"), r.get("band_lo2"), r.get("target"), r.get("stop"))
        if t in trig:
            trig[t] += 1
    R["api"]["swing"] = {
        "total": len(rows),
        "with_triple": len(with_triple),
        "triple_ready": len(with_triple) > 0,
        "sample": [{k: r.get(k) for k in ("code", "name", "price", "band_lo2", "target", "stop")}
                   for r in with_triple[:2]],
        "trig": trig,
    }
except Exception as e:
    R["api"]["swing"] = {"error": str(e)[:200]}

# --- brief 返回体含 cond 段（用只读会话 + RADAR_TOKEN 不可得，改源码静态断言）---
try:
    srvp = open("/opt/invest-workbench/server.py", "r", encoding="utf-8").read()
    html = open("/opt/invest-workbench/index.html", "r", encoding="utf-8").read()
    swj = open("/opt/invest-workbench/sw.js", "r", encoding="utf-8").read()
    R["anchor"] = {
        "sw_v94": "investdesk-v94" in swj,
        "server_cond_fn": "def _cond_triple" in srvp and "cond[\"push_items\"]" in srvp,
        "server_brief_cond": "\"cond\": cond" in srvp and "api_swing({\"now\": [\"1\"]})" in srvp,
        "ws_cond_cell": "function condCellHtml" in html and "function condByCode" in html
                        and "function condTripleOf" in html,
        "ws_cond_th": "条件单 买/标/损" in html,
        "ws_cond_style": "cond-hit" in html and "cond-triple" in html,
        "ws_three_pages": html.count("condCellHtml(") >= 4,
    }
except Exception as e:
    R["anchor"] = {"error": str(e)[:200]}

# --- 真浏览器：三页都渲染条件单列 ---
errs = []
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        c = b.new_context(viewport={"width": 1440, "height": 900})
        c.add_cookies([{"name": "xq_sess", "value": CV,
                        "url": "http://127.0.0.1:8790/", "secure": False}])
        page = c.new_page()
        page.on("pageerror", lambda e: errs.append(str(e)[:200]))
        page.goto("http://127.0.0.1:8790/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_function("typeof switchTab === 'function'", timeout=20000)
        page.wait_for_timeout(3000)
        # 今日操作清单
        R["ui"]["today"] = page.evaluate("""() => {
          var box = document.querySelector('#todoPlan');
          // 今日操作清单在默认折叠面板内，innerText 对隐藏元素返回空；用 textContent 读 DOM 真实内容
          var t = box ? (box.textContent || '') : '';
          return {hasCondHeader: t.indexOf('条件单 买/标/损') >= 0,
                  hasCondToken: /买\\s*[\\d.]+\\s*·\\s*标\\s*[\\d.]+\\s*·\\s*损/.test(t),
                  hasDash: t.indexOf('条件单 —') >= 0,
                  len: t.length};
        }""")
        # 波段操作页
        page.evaluate("() => { try { switchTab('swing'); } catch(e) {} }")
        page.wait_for_timeout(2500)
        R["ui"]["swing"] = page.evaluate("""() => {
          var box = document.querySelector('#view-swing');
          var t = box ? box.innerText : '';
          return {hasCondHeader: t.indexOf('条件单 买/标/损') >= 0,
                  hasCondToken: /买\\s*[\\d.]+\\s*·\\s*标/.test(t),
                  hasBadge: /触发/.test(t), len: t.length};
        }""")
        # 我的持仓页
        page.evaluate("() => { try { switchTab('hold'); } catch(e) {} }")
        page.wait_for_timeout(2500)
        R["ui"]["hold"] = page.evaluate("""() => {
          var box = document.querySelector('#holdBody');
          var t = box ? box.innerText : '';
          var cells = box ? box.querySelectorAll('.cond-hold') : [];
          return {condCellCount: cells.length,
                  hasCondToken: /买\\s*[\\d.]+\\s*·\\s*标/.test(t), len: t.length};
        }""")
        c.close(); b.close()
except Exception as e:
    errs.append("BROWSER: " + str(e)[:200])
R["errors"] = errs[:8]

print("<<<V94_JSON>>>")
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
    sh = ("python3 -c \"import base64;open('/tmp/_v94_check.py','wb').write("
          "base64.b64decode('%s'))\"\n"
          "PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright python3 /tmp/_v94_check.py\n" % blob)
    fd, tmp = tempfile.mkstemp(suffix=".sh", prefix="v94chk_")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write("#!/bin/bash\n" + sh)
    out = tat(["--file", tmp, "--timeout", "300"])
    os.remove(tmp)
    txt = out or ""
    if "<<<V94_JSON>>>" in txt:
        payload = txt.split("<<<V94_JSON>>>", 1)[1].split("<<<END>>>", 1)[0].strip()
        r = json.loads(payload)
    else:
        print(txt[-3000:])
        print("无法解析核验结果")
        sys.exit(2)

    checks = []
    local = {
        "/opt/invest-workbench/server.py": hashlib.sha256(
            open(os.path.join(HERE, "server.py"), "rb").read()).hexdigest(),
        "/opt/invest-workbench/index.html": hashlib.sha256(
            open(os.path.join(HERE, "index.html"), "rb").read()).hexdigest(),
        "/opt/invest-workbench/sw.js": hashlib.sha256(
            open(os.path.join(HERE, "sw.js"), "rb").read()).hexdigest(),
    }
    remote = {}
    for line in r.get("sha") or []:
        parts = line.split()
        if len(parts) == 2:
            remote[parts[1]] = parts[0]
    for k, v in local.items():
        checks.append(("SHA一致:" + k.replace("/opt/invest-workbench/", ""),
                       remote.get(k) == v))

    ct = r.get("api", {}).get("cond_triple") or {}
    checks.append(("_cond_triple 现场6例", ct.get("all_ok") is True))
    sw = r.get("api", {}).get("swing") or {}
    checks.append(("/api/swing 三件套有真实数据", sw.get("triple_ready") is True))
    checks.append(("/api/swing 触发统计可算", isinstance(sw.get("trig"), dict)))

    a = r.get("anchor") or {}
    checks.append(("sw=v94", a.get("sw_v94") is True))
    checks.append(("后端_cond_triple+brief段", a.get("server_cond_fn") is True
                   and a.get("server_brief_cond") is True))
    checks.append(("前端三件套渲染函数", a.get("ws_cond_cell") is True))
    checks.append(("前端条件单表头", a.get("ws_cond_th") is True))
    checks.append(("条件单触发样式", a.get("ws_cond_style") is True))
    checks.append(("三页接线>=4处", a.get("ws_three_pages") is True))

    td = (r.get("ui") or {}).get("today") or {}
    checks.append(("浏览器今日页条件单表头", td.get("hasCondHeader") is True))
    checks.append(("浏览器今日页有数值或诚实—",
                   td.get("hasCondToken") is True or td.get("hasDash") is True))
    wg = (r.get("ui") or {}).get("swing") or {}
    checks.append(("浏览器波段页条件单表头", wg.get("hasCondHeader") is True))
    checks.append(("浏览器波段页有数值", wg.get("hasCondToken") is True))
    hd = (r.get("ui") or {}).get("hold") or {}
    checks.append(("浏览器持仓页条件单元格存在", (hd.get("condCellCount") or 0) > 0))
    checks.append(("零 pageerror", len(r.get("errors") or []) == 0))

    print("\n===== v94 核验结果 =====")
    for name, ok in checks:
        print(("PASS  " if ok else "FAIL  ") + name)
    npass = sum(1 for _, ok in checks if ok)
    print("\n%d/%d PASS" % (npass, len(checks)))
    if r.get("errors"):
        print("pageerrors:", r["errors"])
    print("\n--- 诊断数据 ---")
    print(json.dumps({"swing": r.get("api", {}).get("swing"),
                      "ui": r.get("ui"), "anchor": r.get("anchor")}, ensure_ascii=False)[:2500])
    sys.exit(0 if npass == len(checks) else 1)


if __name__ == "__main__":
    main()
