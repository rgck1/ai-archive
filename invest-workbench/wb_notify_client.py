# -*- coding: utf-8 -*-
"""本机 → 服务器侧企微直推的轻量客户端（无第三方依赖，标准库）。

本机探测脚本（nav_hourly_probe / holdings_probe）检测到 Cookie 失效 / 风控时调用，
POST /api/notify，由服务器用私有 webhook 发企微（服务器 7x24，不依赖本机信息雷达）。

配置从 工作台联动/config.json 读 token + workbench_url（复用已有的 radar_token，
不新增密钥）；可用环境变量 WB_NOTIFY_URL / XQ_RADAR_TOKEN 覆盖。

用法（模块）：
    import wb_notify_client as NC
    NC.cookie_alert("雪球净值探测", "BLOCKED", "连续返回 BLOCKED")
"""
import json
import os
import time
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_CFG = os.path.join(os.path.dirname(_HERE), "..", "工作台联动", "config.json")
CONFIG = os.environ.get("WB_LINK_CONFIG", os.path.normpath(_DEFAULT_CFG))


def _cfg():
    try:
        with open(CONFIG, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def notify(text, kind="misc", all_=False):
    """POST /api/notify。返回 (ok, msg)。失败静默，不影响探测脚本主流程。"""
    cfg = _cfg()
    url = (os.environ.get("WB_NOTIFY_URL") or cfg.get("workbench_url") or "").strip().rstrip("/")
    token = (os.environ.get("XQ_RADAR_TOKEN") or cfg.get("token") or "").strip()
    if not url or not token:
        return False, "no_config"
    endpoint = url + "/api/notify"
    payload = json.dumps({
        "token": token, "ts": time.time(),
        "text": text[:1500], "kind": kind[:24], "all": bool(all_),
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(endpoint, data=payload,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=12) as r:
            res = json.loads(r.read(2000))
        return bool(res.get("ok")), (res.get("reason") or res.get("error") or "")
    except Exception as e:
        return False, str(e)[:100]


def cookie_alert(module, err, detail=""):
    """Cookie 失效告警（kind=cookie，服务器侧 6 小时冷却避免刷屏）。"""
    text = ("【Cookie / 风控告警】%s\n检测到：%s\n%s\n"
            "请到工作台「设置」重新粘贴雪球 Cookie 或稍后重试；"
            "数据可能停更，页面若显示旧日期请勿作为今日依据。" % (
                module, err, detail))
    return notify(text, kind="cookie", all_=True)
