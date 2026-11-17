#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把本机 nav_delta.json（74 只雪球净值增量）gzip+base64 分片推到服务器并合并。

解决 TAT 命令长度上限：merge_nav_delta.sh 内嵌明文 delta 达 154KB 会
InvalidParameterValue.TooLong；本脚本把 delta 压缩到 ~12KB、base64 分片上传，
服务器还原后执行合并 + chown + 重建 pool_daily + 重启 + SHA 校验。

用法：python push_nav_delta.py
前置：先跑 refresh_nav_local.py（--append --batch N 分批）生成完整 nav_delta.json。
"""
import os
import sys
import json
import gzip
import base64
import hashlib
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DELTA = os.path.join(HERE, "nav_delta.json")
CHUNK = 24000
B64_PATH = "/tmp/nav_delta.b64"
JSON_PATH = "/tmp/nav_delta.json"


def tat(cmd, timeout=300):
    p = subprocess.run([sys.executable, os.path.join(HERE, "tat.py"), "run", "--cmd", cmd],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    return (p.stdout or "") + (p.stderr or "")


def tat_file(path, timeout=300):
    p = subprocess.run([sys.executable, os.path.join(HERE, "tat.py"), "run", "--file", path],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    return (p.stdout or "") + (p.stderr or "")


# 服务器端合并脚本（delta 从 /tmp/nav_delta.json 读取，不内嵌）
MERGE_PY = r'''import json, os, time, pwd, grp
delta = json.load(open("/tmp/nav_delta.json", encoding="utf-8"))
deltas = delta.get("deltas") or {}
DATA = "/opt/invest-workbench/data"
try:
    uid = pwd.getpwnam("invest").pw_uid
    gid = grp.getgrnam("invest").gr_gid
except Exception:
    uid = gid = 0
n_merged = n_skip = n_points = 0
for code, pts in deltas.items():
    if not pts:
        n_skip += 1
        continue
    path = os.path.join(DATA, "nav_%s.json" % code)
    d = {}
    if os.path.isfile(path):
        try: d = json.load(open(path, encoding="utf-8"))
        except Exception: d = {}
    old = {p["date"]: p for p in (d.get("points") or []) if isinstance(p, dict) and p.get("date")}
    for p in pts:
        if isinstance(p, dict) and p.get("date"):
            old[p["date"]] = p
    d["points"] = sorted(old.values(), key=lambda x: x["date"])
    d["ts"] = time.time()
    d.pop("force_stale", None); d.pop("ts_real", None)
    tmp = path + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, path)
    try: os.chown(path, uid, gid)
    except Exception: pass
    n_merged += 1
    n_points = max(n_points, len(d["points"]))
print("MERGED=%d SKIP=%d MAX_POINTS=%d" % (n_merged, n_skip, n_points))
# 校验核心池最新日期
for c in ("ZH3553296","ZH3551808","ZH3295404","ZH3542293","ZH3289755"):
    p = os.path.join(DATA, "nav_%s.json" % c)
    if os.path.isfile(p):
        pts = json.load(open(p, encoding="utf-8")).get("points") or []
        print("CORE %s -> %s" % (c, pts[-1]["date"] if pts else "EMPTY"))
'''


def main():
    if not os.path.isfile(DELTA):
        sys.exit("[x] 找不到 " + DELTA)
    raw = open(DELTA, "rb").read()
    d = json.loads(raw.decode("utf-8"))
    deltas = d.get("deltas") or {}
    if len(deltas) < 70:
        sys.exit("[x] delta 只有 %d 只，不足 70，拒绝推送（先分批抓齐）" % len(deltas))
    # 直接上传完整 nav_delta.json（含 deltas/meta/fails 结构），服务器按需取 deltas
    local_sha = hashlib.sha256(raw).hexdigest()
    blob = base64.b64encode(gzip.compress(raw, 9)).decode("ascii")
    parts = [blob[i:i + CHUNK] for i in range(0, len(blob), CHUNK)]
    print("delta %d 只 / raw %d B / gzip+b64 %d B / 分片 %d / sha %s"
          % (len(deltas), len(raw), len(blob), len(parts), local_sha[:16]))

    # 1) 清空并分片上传
    print("==> 清空旧分片")
    tat("rm -f %s %s" % (B64_PATH, JSON_PATH))
    for i, part in enumerate(parts):
        cmd = "printf '%%s' '%s' >> %s" % (part, B64_PATH)
        fd, tmp = tempfile.mkstemp(suffix=".sh", prefix="navchunk_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(cmd)
        res = tat_file(tmp, timeout=300)
        os.remove(tmp)
        if "SUCCESS" not in res:
            sys.exit("[x] 分片 %d 上传失败:\n%s" % (i, res[-400:]))
    print("上传完成 %d 片" % len(parts))

    # 2) 还原 + 校验 sha + 合并
    fd, merge_sh = tempfile.mkstemp(suffix=".sh", prefix="navmerge_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("#!/bin/bash\nset -e\n")
        f.write("base64 -d %s | gunzip > %s\n" % (B64_PATH, JSON_PATH))
        f.write("echo REMOTE_SHA=$(sha256sum %s | awk '{print $1}')\n" % JSON_PATH)
        # 把合并 Python 以 heredoc 内嵌（无 delta，体积极小）
        f.write("python3 - <<'PYEOF'\n" + MERGE_PY + "PYEOF\n")
        f.write("echo '=== 重建 pool_daily 全历史 ==='\n")
        f.write("cd /opt/invest-workbench/engine && XQ_CACHE_DIR=/opt/invest-workbench/data python3 server.py --rebuild-pool-daily\n")
        f.write("chown invest:invest /opt/invest-workbench/data/pool_daily.json 2>/dev/null || true\n")
        f.write("echo '=== 重启服务 ==='\n")
        f.write("systemctl restart invest-workbench\n")
        f.write("echo '=== pool_daily 复核 ==='\n")
        f.write("python3 -c \"import json;p=json.load(open('/opt/invest-workbench/data/pool_daily.json'));print('POOL_DAYS=',len(p.get('days') or []));print('LAST=',(p.get('days') or [])[-1] if p.get('days') else 'NA')\"\n")
        f.write("systemctl is-active invest-workbench\n")
        f.write("echo DONE\n")
    res = tat_file(merge_sh, timeout=400)
    os.remove(merge_sh)
    print("===== 服务器执行结果 =====\n" + res[-2500:])

    if ("REMOTE_SHA=" + local_sha) not in res:
        print("[!] SHA 校验未在输出中匹配，请人工核对（上方 REMOTE_SHA）")
    if "DONE" not in res:
        print("[!] 未见 DONE，合并/重建/重启可能未完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
