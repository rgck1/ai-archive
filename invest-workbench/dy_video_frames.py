#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 aweme_id 列表从抖音单条视频详情页取直链、下载、抽帧拼网格。

关键点：不走"博主主页最近30条"限制，直接打开 https://www.douyin.com/video/{id}
拦截 aweme/detail 接口拿 play_addr。只要手上有视频 ID 就能下，与是否最近无关。

用法（服务器上）：
    python3 dy_video_frames.py --ids 770870...,770272... --out /opt/invest-workbench/data/blog_frames \
        --step 12 --cols 5

输出：每条一个 <id>.jpg 缩略图网格 + manifest.json（含标题/时长/帧时间轴）。
抽帧间隔 --step 秒，网格 --cols 列。图按时间顺序排列，局部放大的示意图可再单帧精抽。
"""
import os
import sys
import json
import re
import time
import argparse
import importlib.util

BASE = "/opt/invest-workbench"
sys.path.insert(0, BASE)
_spec = importlib.util.spec_from_file_location("wb_server", os.path.join(BASE, "server.py"))
S = importlib.util.module_from_spec(_spec)
sys.modules["wb_server"] = S
_spec.loader.exec_module(S)

import auto_asr as A
from playwright.sync_api import sync_playwright


def get_playurl_and_meta(aid, cookies, ua):
    """打开单条详情页，返回 (play_url, title, duration_sec)。"""
    cap = {}

    def on_resp(resp):
        try:
            if resp.status == 200 and "aweme/detail" in resp.url:
                j = resp.json()
                d = j.get("aweme_detail") or {}
                if d:
                    cap["d"] = d
        except Exception:
            pass

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True,
                              args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = b.new_context(user_agent=ua, locale="zh-CN",
                            viewport={"width": 1280, "height": 900})
        if cookies:
            try:
                ctx.add_cookies(cookies)
            except Exception:
                pass
        pg = ctx.new_page()
        pg.on("response", on_resp)
        try:
            pg.goto("https://www.douyin.com/video/" + str(aid),
                    wait_until="domcontentloaded", timeout=45000)
        except Exception:
            pass
        for _ in range(12):
            if cap.get("d"):
                break
            pg.wait_for_timeout(1000)
        title = (pg.title() or "").replace(" - 抖音", "")
        b.close()

    d = cap.get("d") or {}
    urls = ((d.get("video") or {}).get("play_addr") or {}).get("url_list") or []
    url = next((u for u in urls if u), "")
    dur = int(((d.get("video") or {}).get("duration") or 0) / 1000)
    return url, title, dur


def extract_frames(mp4, out_jpg, exe, step, cols):
    """等间隔抽帧拼网格；返回帧数。"""
    # 限制帧数不超过 40（8行x5列），避免图过大
    vf = "fps=1/%d,scale=240:-1,tile=%dx8" % (step, cols)
    cmd = [exe, "-y", "-i", mp4, "-vf", vf, "-q:v", "9",
           "-frames:v", "1", out_jpg]
    r = __import__("subprocess").run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out_jpg):
        return 0
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True, help="逗号分隔的 aweme_id")
    ap.add_argument("--out", default=os.path.join(BASE, "data", "blog_frames"))
    ap.add_argument("--step", type=int, default=12, help="抽帧间隔秒")
    ap.add_argument("--cols", type=int, default=5)
    ap.add_argument("--limit", type=int, default=0, help="最多处理几条(0=全部)")
    args = ap.parse_args()

    ids = [x.strip() for x in args.ids.split(",") if x.strip().isdigit()]
    if args.limit:
        ids = ids[:args.limit]
    os.makedirs(args.out, exist_ok=True)

    cfg = S._dy_cfg_load()
    cookies = [{"name": k, "value": v, "domain": ".douyin.com", "path": "/"}
               for k, v in S._dy_cookie_pairs(cfg.get("cookie") or "")]
    ua = S._DY_UA_PC
    exe = A.get_ffmpeg_exe() if hasattr(A, "get_ffmpeg_exe") else None
    if not exe:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()

    manifest = []
    for idx, aid in enumerate(ids):
        rec = {"aweme_id": aid, "ok": False}
        try:
            url, title, dur = get_playurl_and_meta(aid, cookies, ua)
            rec.update({"title": title, "duration": dur, "has_url": bool(url)})
            print("[%d/%d] %s url=%s dur=%ss %s" %
                  (idx + 1, len(ids), aid, bool(url), dur, title[:30]), flush=True)
            if not url:
                manifest.append(rec)
                continue
            mp4 = os.path.join("/tmp", "df_" + aid + ".mp4")
            sz = A.download(url, mp4, A._cookie(S))
            rec["mp4_bytes"] = sz
            jpg = os.path.join(args.out, aid + ".jpg")
            ok = extract_frames(mp4, jpg, exe, args.step, args.cols)
            rec["frame_ok"] = bool(ok)
            rec["jpg"] = jpg
            print("    mp4=%dB frame_ok=%s" % (sz, bool(ok)), flush=True)
        except Exception as e:
            rec["error"] = str(e)[:200]
            print("    ERR", str(e)[:120], flush=True)
        rec["ok"] = bool(rec.get("frame_ok"))
        manifest.append(rec)
        try:
            if os.path.exists("/tmp/df_" + aid + ".mp4"):
                os.remove("/tmp/df_" + aid + ".mp4")
        except Exception:
            pass

    mf = os.path.join(args.out, "manifest.json")
    with open(mf, "w", encoding="utf-8") as f:
        json.dump({"step": args.step, "cols": args.cols, "items": manifest},
                  f, ensure_ascii=False, indent=1)
    print("DONE ok=%d/%d manifest=%s" %
          (sum(1 for x in manifest if x["ok"]), len(manifest), mf), flush=True)


if __name__ == "__main__":
    main()
