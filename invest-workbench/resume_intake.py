# -*- coding: utf-8 -*-
"""
一键接续：核查「日常收集」库订阅博主 → 比对已入库 → 列出可抽取的新博主。

用法：
  python resume_intake.py              # 只核查并列出新增（只读，安全）
  python resume_intake.py --extract    # 对新增博主跑抽取（生成 JSON 到博主笔记目录）
  python resume_intake.py --stat       # 额外打印关注额度 stat

设计：用户手动在得到 App 关注 + 加入知识库后，平台聚合出笔记，
本脚本拉库 following 全列表，与 vault 已入库博主比对，找出未入库的新博主。
"""
import json, os, sys, time, argparse, urllib.request
sys.stdout.reconfigure(encoding="utf-8")

VAULT = "D:/我的工作台/第二大脑/02-知识库/订阅主播/博主笔记"
BASE = "https://get-notes.luojilab.com/voicenotes/web/share/topics/YvEVmZDn/following"
UA = {"User-Agent": "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36",
      "Xi-App-Client-Source": "getnote"}
OUT = "D:/Software/second-brain-tools/_debug_archive/resume_intake_result.json"


def fetch_following():
    allb, page = [], 1
    while page <= 10:
        with urllib.request.urlopen(
            urllib.request.Request(BASE + "?page=%d&page_size=20" % page, headers=UA), timeout=15
        ) as r:
            c = json.loads(r.read().decode()).get("c", {})
        lst = c.get("list", [])
        allb += lst
        if len(allb) >= (c.get("count") or 0) or not lst:
            break
        page += 1
        time.sleep(0.4)
    return allb


def already_in_vault():
    done = {}
    if os.path.isdir(VAULT):
        for f in os.listdir(VAULT):
            if f.endswith(".json"):
                try:
                    d = json.load(open(os.path.join(VAULT, f), encoding="utf-8"))
                    done[str(d.get("blogger_id"))] = d.get("blogger_name")
                except Exception:
                    pass
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract", action="store_true", help="对新增博主跑抽取")
    ap.add_argument("--stat", action="store_true", help="打印关注额度")
    args = ap.parse_args()

    print("=== 核查「日常收集」库订阅博主 ===")
    allb = fetch_following()
    done = already_in_vault()
    print("库内博主 %d 位，已入库 %d 位" % (len(allb), len(done)))

    new = [b for b in allb if str(b.get("id")) not in done]
    print("\n=== 未入库（可抽取候选）%d 位 ===" % len(new))
    for b in new:
        print("  id=%-9s %s" % (b.get("id"), b.get("name")))
    if not new:
        print("  （无。说明新关注的博主还没[加入知识库]或平台未聚合，需用户在 App 操作）")

    json.dump({"count": len(allb), "already": done, "new": new},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n结果已存 %s" % OUT)

    if args.stat:
        import token_refresh as TR, uuid
        s = TR.load_state(); tok, ch = TR.ensure_fresh(s, margin=600); ck = TR.cookies_of(s)
        H = "https://knowledge-api.trytalks.com"
        hd = {"User-Agent": "Mozilla/5.0 AppleWebKit/537.36 Chrome/120", "Authorization": "Bearer " + tok,
              "Content-Type": "application/json", "Xi-Csrf-Token": ck.get("csrfToken", ""),
              "X-Request-ID": uuid.uuid4().hex, "Xi-Client-Source": "getnote", "X-Appid": "3", "X-Av": "1.2.2",
              "Cookie": "; ".join("%s=%s" % (k, v) for k, v in ck.items()), "Referer": "https://www.biji.com/"}
        req = urllib.request.Request(H + "/v1/web/follow/watch/bloggers/stat", data=b"{}", headers=hd, method="POST")
        with urllib.request.urlopen(req, timeout=20) as r:
            print("关注额度：", json.loads(r.read().decode())["c"])

    if args.extract and new:
        print("\n>>> 抽取模式：调用 sync_getnote_extra.py 逐位抽取（topic_id=5022804）")
        import subprocess
        for b in new:
            cmd = [sys.executable, "sync_getnote_extra.py", "--topic-id", "5022804",
                   "--follow-id", str(b["id"]), "--name", b["name"]]
            print("  ", " ".join(cmd))
            subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))
            time.sleep(1.2)


if __name__ == "__main__":
    main()
