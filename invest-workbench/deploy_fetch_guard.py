# -*- coding: utf-8 -*-
"""P1 限流熔断底座部署：推 fetch_guard.py（新）+ sector_rotation_update.py（改）。

只推两个脚本，不动 timer/service/其他脚本/数据。每份 gzip+b64 分片 + SHA 校验 + chown invest。
"""
import base64
import gzip
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TAT = os.path.join(HERE, "tat.py")
APP = "/opt/invest-workbench"
CHUNK = 18000
_ALL_FILES = ["fetch_guard.py", "sector_rotation_update.py"]
# 支持命令行只推单个文件（绕开 TAT --cmd 长度限制）：python deploy_fetch_guard.py fetch_guard.py
FILES = [a for a in sys.argv[1:] if a in _ALL_FILES] or _ALL_FILES


def tat(cmd, timeout=300):
    p = subprocess.run([sys.executable, TAT, "run", "--cmd", cmd],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    return (p.stdout or "") + (p.stderr or "")


def main():
    lines = ["set -e", "cd %s" % APP]
    expects = []
    for idx, fn in enumerate(FILES):
        raw = open(os.path.join(HERE, fn), "rb").read()
        sha = hashlib.sha256(raw).hexdigest()
        expects.append((fn, sha))
        blob = base64.b64encode(gzip.compress(raw, 9)).decode()
        parts = [blob[j:j + CHUNK] for j in range(0, len(blob), CHUNK)]
        tag = "fg%d" % idx
        lines.append("rm -f /tmp/%s.b64 /tmp/%s.out" % (tag, tag))
        for part in parts:
            lines.append("printf '%%s' '%s' >> /tmp/%s.b64" % (part, tag))
        lines += [
            "base64 -d /tmp/%s.b64 | gunzip > /tmp/%s.out" % (tag, tag),
            "sudo install -o invest -g invest -m 644 /tmp/%s.out %s/%s" % (tag, APP, fn),
            "rm -f /tmp/%s.b64 /tmp/%s.out" % (tag, tag),
            "echo SHA_%s=$(sha256sum %s/%s | awk '{print $1}')" % (fn, APP, fn),
        ]
    # 自测 fetch_guard 在服务器可运行（仅当本次推了它）
    if "fetch_guard.py" in FILES:
        lines += ["echo ===GUARD_SELFTEST===",
                  "sudo -u invest /usr/bin/python3 %s/fetch_guard.py" % APP]
    lines.append("echo ===DEPLOY_GUARD_DONE===")
    res = tat("\n".join(lines), timeout=360)
    print(res)
    ok = ("DEPLOY_GUARD_DONE" in res
          and all(("SHA_%s=%s" % (fn, sha)) in res for fn, sha in expects))
    print("==> 校验：两脚本 SHA 一致 + 服务器自测通过 =", ok)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
