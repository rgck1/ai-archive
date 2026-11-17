#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""雪球净值一键补刷（本机住宅 IP）：分批抓取 → 累积 → 推送服务器 → 重建 → 核验。

背景：云服务器 IP 被雪球风控，净值靠本机住宅 IP 抓。雪球对短时间连续请求
会临时限流（约 16-17 个/轮后 BLOCKED），所以分批抓、批间冷却。

用法：
    python refresh_nav_all.py            # 全流程：抓齐 74 只 + 推送 + 重建 + 重启
    python refresh_nav_all.py --fetch-only  # 只抓不推（先看 nav_delta.json）
    python refresh_nav_all.py --batch 12 --cooldown 45   # 自定义批量与冷却秒数

前置：xq_cookie.txt 是最新的雪球登录 Cookie（失效会 NEED_COOKIE 中止）。
"""
import os
import sys
import json
import time
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
DELTA = os.path.join(HERE, "nav_delta.json")
BATCH = 12
COOLDOWN = 45


def run(args, timeout=300):
    p = subprocess.run([sys.executable] + args, cwd=HERE, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def delta_count():
    if not os.path.isfile(DELTA):
        return 0
    try:
        d = json.load(open(DELTA, encoding="utf-8"))
        return len(d.get("deltas") or {})
    except Exception:
        return 0


def main():
    fetch_only = "--fetch-only" in sys.argv
    if "--batch" in sys.argv:
        BATCH = int(sys.argv[sys.argv.index("--batch") + 1])
    if "--cooldown" in sys.argv:
        COOLDOWN = int(sys.argv[sys.argv.index("--cooldown") + 1])

    # 首次抓：清空旧 delta，从头开始（--append 后续批次累积）
    if os.path.isfile(DELTA):
        os.remove(DELTA)
    print("=== 开始分批抓取（每批 %d 只，冷却 %ds）===" % (BATCH, COOLDOWN))
    round_no = 0
    while True:
        n = delta_count()
        if n >= 74:
            print("已抓齐 74 只，停止抓取")
            break
        round_no += 1
        cmd = [os.path.join(HERE, "refresh_nav_local.py"), "--append", "--batch", str(BATCH)]
        rc, out = run(cmd, timeout=300)
        got = delta_count()
        print("[批 %d] 退出=%d 累计=%d/74" % (round_no, rc, got))
        print("  " + "\n  ".join([ln for ln in out.splitlines() if "[ok]" in ln or "[abort]" in ln or "[done]" in ln][-4:]))
        if rc != 0 and got == n:
            # 本批完全没进展且异常（如 NEED_COOKIE / BLOCKED）
            if "NEED_COOKIE" in out:
                print("[x] Cookie 失效，请更新 xq_cookie.txt 后重跑")
                return 2
            if "BLOCKED" in out:
                print("! 遇到风控，延长冷却 90s 后重试本批")
                time.sleep(90)
                continue
            print("[x] 本批异常且无进展，中止：\n" + out[-500:])
            return 1
        if got >= 74:
            break
        time.sleep(COOLDOWN)

    # 完整性校验
    d = json.load(open(DELTA, encoding="utf-8"))
    deltas = d.get("deltas") or {}
    codes = set(x.strip() for x in open(os.path.join(HERE, "nav_codes.txt"), encoding="utf-8")
                if x.strip().startswith("ZH"))
    missing = codes - set(deltas.keys())
    core = ["ZH3553296", "ZH3551808", "ZH3295404", "ZH3542293", "ZH3289755"]
    print("=== 抓取完成：%d 只 / 缺失 %d / 核心5只全在=%s ==="
          % (len(deltas), len(missing), all(c in deltas for c in core)))
    if missing or not all(c in deltas for c in core):
        print("[x] 数据不完整，拒绝推送。缺失：" + str(sorted(missing)))
        return 1
    if fetch_only:
        print("--fetch-only：仅抓取，未推送")
        return 0

    # 推送 + 重建 + 重启
    print("=== 推送服务器 ===")
    rc, out = run([os.path.join(HERE, "push_nav_delta.py")], timeout=500)
    print(out[-2000:])
    if "MERGED=74" not in out or "DONE" not in out:
        print("[!] 推送可能异常，请核对上方输出")
        return 1
    print("=== 全部完成 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
