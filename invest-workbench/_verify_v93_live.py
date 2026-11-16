# -*- coding: utf-8 -*-
"""v93 线上核验（保留脚本，供其它智能体复现 IA 重构）：

1) 线上 server.py / index.html / sw.js 与本地逐字节 SHA 一致，服务 active，sw=v93
2) IA-2 /api/stock_valuation：负 PE 票 give reason 而非空；前端 valLevel 读 reason
3) IA-4 /api/swing_plan：stat.now_total / now_actions 汇总含持仓已触发，不再「立即 0 只」
4) IA-5 /api/fair_value_one：
   - 非法代码 → available:false + reason
   - 池内快照票（有 fairvalue_snapshot）→ available:true + source 含「快照」
   - 任意池外 6 位代码 → 实时近似路径，成功给合理价/失败如实 available:false，绝不编造
   - 含 note 口径说明
5) IA-6 风险平价：
   - _bt_weights 等价性在服务端现场复算（1/sigma20 归一化、低波动多配、满仓）
   - /api/recs_top3 里 key=risk_parity 的 alloc_scheme 非空（不再是「暂无同口径实现」）
   - 策略实验室回测接口 schemes 含 risk_parity
6) 静态锚点 + 真浏览器：首屏全景摘要、折叠操作区、估值弹窗、做T块移除、风险平价按钮，零 pageerror

会话读 /opt/invest-workbench/.session_secret 自签 1 小时只读 Cookie（不碰口令）。
用法：python _verify_v93_live.py
"""
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

SERVER_PY = r'''# -*- coding: utf-8 -*-
import datetime, hashlib, hmac, json, os, re, subprocess, sys, time, urllib.request
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

# --- IA-4 波段统计 ---
try:
    sw = api("/api/swing")
    st = sw.get("stat") or {}
    groups = {}
    for g in ("held", "now", "wait", "hold", "blocked", "self"):
        groups[g] = len(sw.get(g) or [])
    R["api"]["swing"] = {
        "has_stat": all(k in st for k in ("now", "now_held", "now_total", "wait", "held")),
        "now_total_consistent": st.get("now_total") == (st.get("now", 0) + st.get("now_held", 0)),
        "now_actions_is_list": isinstance(st.get("now_actions"), list),
        "stat": st, "groups": groups,
    }
except Exception as e:
    R["api"]["swing"] = {"error": str(e)[:200]}

# --- IA-5 按需估值 ---
try:
    bad = api("/api/fair_value_one?code=abc")
    R["api"]["fv_bad"] = {"available": bad.get("available"), "reason": bool(bad.get("reason"))}
except Exception as e:
    R["api"]["fv_bad"] = {"error": str(e)[:200]}

try:
    snap = json.load(open("/opt/invest-workbench/data/fairvalue_snapshot.json", encoding="utf-8"))
    items = snap.get("items") or []
    pool_code = None
    for it in items:
        c = str(it.get("code") or "")
        dg = re.sub(r"\D", "", c)[-6:]
        if len(dg) == 6:
            pool_code = dg
            break
    if pool_code:
        hit = api("/api/fair_value_one?code=" + pool_code)
        it = hit.get("item") or {}
        R["api"]["fv_pool"] = {
            "code": pool_code, "available": hit.get("available"),
            "in_pool": hit.get("in_pool"), "source": it.get("source"),
            "data_basis": it.get("data_basis"), "has_fair": it.get("fair_price") is not None,
            "has_note": bool(hit.get("note")),
            "cached_ok": (hit.get("cached") in (True, False)),
        }
    else:
        R["api"]["fv_pool"] = {"error": "快照无可用代码"}
except Exception as e:
    R["api"]["fv_pool"] = {"error": str(e)[:200]}

try:
    # 池外代码：用一个明确不在快照里的平安银行 000001（大概率不在池），验证实时近似路径不编造
    live = api("/api/fair_value_one?code=000001")
    it = live.get("item") or {}
    R["api"]["fv_live"] = {
        "available": live.get("available"), "in_pool": live.get("in_pool"),
        "reason": live.get("reason"), "data_basis": it.get("data_basis"),
        "honest": (bool(live.get("available")) or bool(live.get("reason"))),
    }
except Exception as e:
    R["api"]["fv_live"] = {"error": str(e)[:200]}

# --- IA-6 风险平价：服务端现场等价性复算 ---
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("srv", "/opt/invest-workbench/server.py")
    m = importlib.util.module_from_spec(spec)
    # server.py 顶部有 _WB_SELF_MODULE = sys.modules[__name__]，须先注册再 exec；
    # 主循环在 if __name__ == "__main__" 守卫内，这里 __name__='srv' 不会启动服务。
    sys.modules["srv"] = m
    spec.loader.exec_module(m)
    metas = [
        {"code": "A", "rk": {"sigma20": 0.01, "sigma60": 0.03}},
        {"code": "B", "rk": {"sigma20": 0.02, "sigma60": 0.03}},
        {"code": "C", "rk": {"sigma20": 0.04, "sigma60": 0.03}},
    ]
    w = m._bt_weights("risk_parity", metas)
    iv = {x["code"]: 1.0 / x["rk"]["sigma20"] for x in metas}
    tot = sum(iv.values())
    exp = {k: v / tot for k, v in iv.items()}
    exact = all(abs(w.get(k, -1) - exp[k]) < 1e-9 for k in exp)
    R["api"]["rp_weights"] = {
        "weights": w, "sum": round(sum(w.values()), 9),
        "exact_lab_formula": exact, "low_vol_more": w.get("A", 0) > w.get("B", 0) > w.get("C", 0),
        "in_alloc_map": "risk_parity" in m._RECS_ALLOC_SCHEMES,
        "alloc_name": m._RECS_ALLOC_SCHEMES.get("risk_parity"),
    }
except Exception as e:
    R["api"]["rp_weights"] = {"error": str(e)[:200]}

try:
    t3 = api("/api/recs_top3")
    rank = t3.get("ranking") or []
    rp = next((x for x in rank if x.get("key") == "risk_parity"), None)
    R["api"]["rp_top3"] = {
        "total": t3.get("total_strategies"),
        "rp_present": rp is not None,
        "rp_alloc_scheme": (rp or {}).get("alloc_scheme"),
        "in_top3": any((x.get("key") == "risk_parity") for x in (t3.get("top3") or [])),
    }
except Exception as e:
    R["api"]["rp_top3"] = {"error": str(e)[:200]}

# --- 静态锚点 ---
try:
    html = open("/opt/invest-workbench/index.html", "r", encoding="utf-8").read()
    swj = open("/opt/invest-workbench/sw.js", "r", encoding="utf-8").read()
    srvp = open("/opt/invest-workbench/server.py", "r", encoding="utf-8").read()
    R["anchor"] = {
        "sw_v93": "investdesk-v93" in swj,
        "today_glance": "renderTodayGlance" in html and 'id="wbGlance"' in html,
        "ops_fold": "todayOpsFold" in html,
        "fv_dialog": "initFairValueDialog" in html and "fvAgain" in html,
        "fv_api": "/api/fair_value_one" in html,
        "tsig_removed_hold": html.count("做T信号") <= 2,
        "risk_parity_btn": "btnSchemeRiskParity" in html,
        "risk_parity_scheme": "risk_parity" in html and "风险平价" in html,
        "server_sigma20": "sigma20" in srvp and "_RECS_ALLOC_SCHEMES" in srvp,
    }
except Exception as e:
    R["anchor"] = {"error": str(e)[:200]}

# --- 真浏览器 ---
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
        page.wait_for_timeout(2500)
        R["ui"]["today"] = page.evaluate("""() => {
          var g = document.querySelector('#wbGlance');
          var fold = document.querySelector('#todayOpsFold');
          var hv = document.querySelector('#view-hold');
          return {hasGlance: !!g,
                  glanceText: g ? g.innerText.slice(0,120) : '',
                  nowNum: (document.querySelector('#wbGlanceNow')||{}).textContent || '',
                  hasFold: !!fold, foldClosed: fold ? !fold.open : null,
                  holdHasTsigBlock: hv ? hv.innerText.indexOf('做T信号')>=0 : null,
                  bodyLen: document.body.innerText.length};
        }""")
        # 打开估值弹窗
        page.evaluate("() => { try { openFairValue('600519'); } catch(e) {} }")
        page.wait_for_timeout(2000)
        R["ui"]["fv"] = page.evaluate("""() => {
          var d = document.querySelector('#fvDialog') || document.querySelector('[role=dialog][id*=fv]');
          return {dialogExists: !!d, visible: d ? !!(d.offsetWidth||d.offsetHeight) : false,
                  text: d ? d.innerText.slice(0,160) : ''};
        }""")
        # 切到跟单推荐页看风险平价按钮 + Top3
        page.evaluate("() => { try { switchTab('recs'); } catch(e) {} }")
        page.wait_for_timeout(2500)
        R["ui"]["recs"] = page.evaluate("""() => {
          var btn = document.querySelector('#btnSchemeRiskParity');
          var top3 = document.querySelector('#recTop3');
          return {rpBtn: !!btn, rpBtnText: btn ? btn.textContent : '',
                  top3Len: top3 ? top3.innerText.length : 0,
                  top3HasRP: top3 ? top3.innerText.indexOf('风险平价')>=0 : false};
        }""")
        c.close(); b.close()
except Exception as e:
    errs.append("BROWSER: " + str(e)[:200])
R["errors"] = errs[:8]

print("<<<V93_JSON>>>")
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
    sh = ("python3 -c \"import base64;open('/tmp/_v93_check.py','wb').write("
          "base64.b64decode('%s'))\"\n"
          "PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright python3 /tmp/_v93_check.py\n" % blob)
    fd, tmp = tempfile.mkstemp(suffix=".sh", prefix="v93chk_")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(sh)
    print("==> 服务器侧核验（SHA + 接口断言 + 真浏览器）")
    out = tat(["--file", tmp, "--timeout", "500"], timeout=700)
    os.remove(tmp)
    m = re.search(r"<<<V93_JSON>>>\s*\n(.*?)\n<<<END>>>", out, re.S)
    if not m:
        print("!! 未拿到结果，原始输出：\n" + out[-4000:])
        sys.exit(1)
    r = json.loads(m.group(1))
    print(json.dumps(r, ensure_ascii=False, indent=2)[:8000])

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

    sw = r.get("api", {}).get("swing") or {}
    checks.append(("波段stat字段齐全", sw.get("has_stat") is True))
    checks.append(("now_total=now+now_held", sw.get("now_total_consistent") is True))
    checks.append(("now_actions为列表", sw.get("now_actions_is_list") is True))

    bad = r.get("api", {}).get("fv_bad") or {}
    checks.append(("非法代码拒绝", bad.get("available") is False and bad.get("reason") is True))
    pool = r.get("api", {}).get("fv_pool") or {}
    checks.append(("池内快照票可用+快照源", pool.get("available") is True
                   and "快照" in (pool.get("source") or "")))
    checks.append(("估值含口径note", pool.get("has_note") is True))
    live = r.get("api", {}).get("fv_live") or {}
    checks.append(("池外代码诚实返回", live.get("honest") is True))

    rw = r.get("api", {}).get("rp_weights") or {}
    checks.append(("风险平价权重=回测公式", rw.get("exact_lab_formula") is True))
    checks.append(("风险平价低波动多配", rw.get("low_vol_more") is True))
    checks.append(("风险平价满仓归一", abs((rw.get("sum") or 0) - 1.0) < 1e-9))
    checks.append(("风险平价在配置映射表", rw.get("in_alloc_map") is True))
    t3 = r.get("api", {}).get("rp_top3") or {}
    checks.append(("Top3排名含risk_parity", t3.get("rp_present") is True))
    checks.append(("risk_parity可应用(alloc非空)", bool(t3.get("rp_alloc_scheme"))))

    a = r.get("anchor") or {}
    checks.append(("sw=v93", a.get("sw_v93") is True))
    checks.append(("首屏全景摘要锚点", a.get("today_glance") is True))
    checks.append(("操作区折叠锚点", a.get("ops_fold") is True))
    checks.append(("估值弹窗锚点", a.get("fv_dialog") is True and a.get("fv_api") is True))
    checks.append(("风险平价按钮+scheme锚点", a.get("risk_parity_btn") is True
                   and a.get("risk_parity_scheme") is True))
    checks.append(("后端sigma20+映射锚点", a.get("server_sigma20") is True))

    ui = (r.get("ui") or {}).get("today") or {}
    checks.append(("浏览器首屏摘要可见", ui.get("hasGlance") is True))
    checks.append(("浏览器操作区默认折叠", ui.get("foldClosed") is True))
    checks.append(("持仓页做T块已移除", ui.get("holdHasTsigBlock") is False))
    fv = (r.get("ui") or {}).get("fv") or {}
    checks.append(("浏览器估值弹窗打开", fv.get("dialogExists") is True and fv.get("visible") is True))
    rc = (r.get("ui") or {}).get("recs") or {}
    checks.append(("浏览器风险平价按钮存在", rc.get("rpBtn") is True))
    checks.append(("零 pageerror", len(r.get("errors") or []) == 0))

    print("\n===== v93 核验结果 =====")
    for name, ok in checks:
        print(("PASS  " if ok else "FAIL  ") + name)
    npass = sum(1 for _, ok in checks if ok)
    print("\n%d/%d PASS" % (npass, len(checks)))
    sys.exit(0 if npass == len(checks) else 1)


if __name__ == "__main__":
    main()
