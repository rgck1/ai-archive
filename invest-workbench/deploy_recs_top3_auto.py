# -*- coding: utf-8 -*-
"""通过 TAT 部署「跟单推荐 Top3 · 每月自动回测」管线并装 systemd timer。

推送内容：
  - strategy_lab.py                （加腾讯前复权 OHLC 兜底，东财被封时月度回测不空转）
  - monthly_strategy_backtest.py   （全量回测 + 结果校验 + 每策略自评分 + 运行审计）
  - invest-workbench-recs-top3.{service,timer}  每月 1 日 04:30，Persistent=true

顺序（外部编排）：
  1) 本脚本：推脚本 + 装 timer + 首次 --derive-only 生成运行审计
  2) deploy_server_now.py：推根 server.py（含 /api/recs_top3 路由）
  3) deploy_frontend_now.py：推 index.html + sw.js v84
  4) 可选：手动触发一次完整月度回测 systemctl start invest-workbench-recs-top3.service

注意：Top3 的选取放在 /api/recs_top3 里现场派生（唯一真值源 strategy_lab.json），
因此本脚本不生成第二份「快照」，从根上杜绝展示与回测口径不一致。
"""
import base64
import gzip
import hashlib
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TAT = os.path.join(HERE, "tat.py")
APP = "/opt/invest-workbench"
CHUNK = 18000

FILES = [
    ("strategy_lab.py", APP + "/strategy_lab.py"),
    ("monthly_strategy_backtest.py", APP + "/monthly_strategy_backtest.py"),
]

SERVICE = """[Unit]
Description=Invest Workbench Monthly Strategy Backtest / Recs Top3 Refresh
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=invest
Group=invest
WorkingDirectory=/opt/invest-workbench
EnvironmentFile=/opt/invest-workbench/env/workbench.env
ExecStart=/usr/bin/python3 /opt/invest-workbench/monthly_strategy_backtest.py
StandardOutput=append:/opt/invest-workbench/logs/recs_top3_monthly.log
StandardError=append:/opt/invest-workbench/logs/recs_top3_monthly.err.log
"""

# 每月 1 日 04:30：月初凌晨避开交易与日间定时任务；Persistent 保证关机错过也会补跑。
TIMER = """[Unit]
Description=Invest Workbench Monthly Strategy Backtest Timer

[Timer]
OnCalendar=*-*-01 04:30
Persistent=true
RandomizedDelaySec=600
Unit=invest-workbench-recs-top3.service

[Install]
WantedBy=timers.target
"""


def b64(raw):
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    return base64.b64encode(gzip.compress(raw, 9)).decode()


def main():
    for name, _ in FILES:
        if not os.path.isfile(os.path.join(HERE, name)):
            print("!! 缺少本地文件：" + name)
            return 1

    lines = ["set -e",
             "sudo mkdir -p %s/data %s/logs" % (APP, APP),
             "sudo chown invest:invest %s/data %s/logs" % (APP, APP)]
    expect = {}
    for i, (name, target) in enumerate(FILES):
        raw = open(os.path.join(HERE, name), "rb").read()
        sha = hashlib.sha256(raw).hexdigest()
        expect[i] = sha
        blob = b64(raw)
        parts = [blob[j:j + CHUNK] for j in range(0, len(blob), CHUNK)]
        tag = "wbrt%d" % i
        lines.append("rm -f /tmp/%s.b64 /tmp/%s.out" % (tag, tag))
        for part in parts:
            lines.append("printf '%%s' '%s' >> /tmp/%s.b64" % (part, tag))
        lines.append("base64 -d /tmp/%s.b64 | gunzip > /tmp/%s.out" % (tag, tag))
        lines.append("sudo install -o invest -g invest -m 644 /tmp/%s.out %s" % (tag, target))
        lines.append("echo INSTALLED_SHA_%d=$(sha256sum %s | awk '{print $1}')" % (i, target))
        lines.append("rm -f /tmp/%s.b64 /tmp/%s.out" % (tag, tag))
        print("本地 %-32s sha=%s size=%d 分片=%d" % (
            name, sha[:12], len(raw), len(parts)))

    lines.append("echo '%s' | base64 -d | gunzip > /tmp/wbrt.service" % b64(SERVICE))
    lines.append("echo '%s' | base64 -d | gunzip > /tmp/wbrt.timer" % b64(TIMER))
    lines.append("sudo install -o root -g root -m 644 /tmp/wbrt.service "
                 "/etc/systemd/system/invest-workbench-recs-top3.service")
    lines.append("sudo install -o root -g root -m 644 /tmp/wbrt.timer "
                 "/etc/systemd/system/invest-workbench-recs-top3.timer")
    lines.append("sudo rm -f /tmp/wbrt.service /tmp/wbrt.timer")
    lines.append("sudo systemctl daemon-reload")
    lines.append("sudo systemctl enable invest-workbench-recs-top3.timer")
    lines.append("sudo systemctl start invest-workbench-recs-top3.timer")
    lines.append("echo TIMER_INSTALLED")
    lines.append("sudo systemctl list-timers invest-workbench-recs-top3.timer --no-pager")

    # 服务端自检：确认 strategy_lab.py 能正常 import 根 server 模块并跑通合成行情
    lines.append("echo SELFTEST_ON_SERVER")
    lines.append("sudo -u invest env XQ_CACHE_DIR=%s/data /usr/bin/python3 "
                 "%s/strategy_lab.py --selftest" % (APP, APP))
    # 首次运行：不跑回测，只按现有 strategy_lab.json 刷新运行审计，页面立即可用
    lines.append("echo FIRST_DERIVE_ONLY_RUN")
    lines.append("sudo -u invest env XQ_CACHE_DIR=%s/data /usr/bin/python3 "
                 "%s/monthly_strategy_backtest.py --derive-only" % (APP, APP))
    lines.append("echo RUN_STATUS")
    lines.append("cat %s/data/recs_top3_run.json" % APP)
    lines.append("echo ALL_DONE")

    fd, tmp = tempfile.mkstemp(suffix=".sh", prefix="wbrtauto_")
    with os.fdopen(fd, "w", encoding="ascii", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    try:
        print("==> 执行 TAT 部署（脚本 %d 字节）" % os.path.getsize(tmp))
        p = subprocess.run([sys.executable, TAT, "run", "--file", tmp, "--timeout", "900"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=960)
        out = (p.stdout or "") + (p.stderr or "")
        print(out)
        print("EXIT=", p.returncode)
        ok = (p.returncode == 0 and "ALL_DONE" in out
              and "TIMER_INSTALLED" in out
              and "SELFTEST_STRATEGIES_OK=25" in out
              and all(("INSTALLED_SHA_%d=%s" % (i, s)) in out
                      for i, s in expect.items()))
        print("==> 校验：两文件 SHA 一致 + 服务端自检 25 策略通过 + timer 已装 + 首次派生完成 =", ok)
        return 0 if ok else 1
    finally:
        os.remove(tmp)


if __name__ == "__main__":
    sys.exit(main())
