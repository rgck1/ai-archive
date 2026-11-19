# -*- coding: utf-8 -*-
"""把服务器侧企微直推（server_notify.py --daily）合并进现有 v47-daily.service。

只做一件事：在原 5 个 ExecStart 之后追加第 6 个，其余逐字保留。
不碰 timer（仍每天 20:30 / Persistent / AccuracySec=1min），不碰任何其他 unit/脚本。
webhook 私有文件已由部署 server_notify 时写好（600 / invest:invest），本脚本不重复写 key。
"""
import base64
import gzip
import subprocess
import sys

HERE = __import__("os").path.dirname(__import__("os").path.abspath(__file__))
TAT = HERE + "/tat.py"

SERVICE = """[Unit]
Description=Invest Workbench v47 daily maintenance
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=invest
Group=invest
WorkingDirectory=/opt/invest-workbench
EnvironmentFile=/opt/invest-workbench/env/workbench.env
Environment=XQ_CACHE_DIR=/opt/invest-workbench/data
ExecStart=-/usr/bin/python3 /opt/invest-workbench/mood_history.py --incremental
ExecStart=-/usr/bin/python3 /opt/invest-workbench/consensus_snapshot.py
ExecStart=-/usr/bin/python3 /opt/invest-workbench/recon_scan.py
ExecStart=-/usr/bin/python3 /opt/invest-workbench/module_review.py
ExecStart=-/usr/bin/python3 /opt/invest-workbench/recs_momentum_daily.py
ExecStart=-/usr/bin/python3 /opt/invest-workbench/server_notify.py --daily
StandardOutput=append:/opt/invest-workbench/logs/v47_daily.log
StandardError=append:/opt/invest-workbench/logs/v47_daily.err.log
"""


def b64(s):
    return base64.b64encode(gzip.compress(s.encode(), 9)).decode()


def tat(cmd, timeout=300):
    p = subprocess.run([sys.executable, TAT, "run", "--cmd", cmd],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    return (p.stdout or "") + (p.stderr or "")


def main():
    cmd = "\n".join([
        "set -e",
        "echo '%s' | base64 -d | gunzip > /tmp/wbn.service" % b64(SERVICE),
        "sudo install -o root -g root -m 644 /tmp/wbn.service "
        "/etc/systemd/system/invest-workbench-v47-daily.service",
        "rm -f /tmp/wbn.service",
        "echo SERVICE_EXEC_COUNT=$(grep -c '^ExecStart=' "
        "/etc/systemd/system/invest-workbench-v47-daily.service)",
        "echo NOTIFY_EXEC=$(grep -c 'server_notify.py --daily' "
        "/etc/systemd/system/invest-workbench-v47-daily.service)",
        "echo TIMER_ONCALENDAR=$(grep '^OnCalendar=' "
        "/etc/systemd/system/invest-workbench-v47-daily.timer)",
        "sudo systemctl daemon-reload",
        "echo UNIT_ACTIVE=$(systemctl is-active invest-workbench-v47-daily.timer)",
        "echo DEPLOY_NOTIFY_DONE",
    ])
    res = tat(cmd, timeout=300)
    print(res)
    ok = ("DEPLOY_NOTIFY_DONE" in res and "SERVICE_EXEC_COUNT=6" in res
          and "NOTIFY_EXEC=1" in res and "OnCalendar=*-*-* 20:30:00" in res)
    print("==> 校验：service恰好6个ExecStart + 含server_notify --daily + timer仍20:30 =", ok)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
