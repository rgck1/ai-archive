# -*- coding: utf-8 -*-
"""
抽取用户新建「优先」库(topic=5029201)里 7 位博主的聚合笔记。
复用 sync_getnote_extra 的 token/熔断逻辑，带断点续传。
输出与现有格式一致的 JSON 到博主笔记目录。
"""
import json, os, sys, time
sys.stdout.reconfigure(encoding="utf-8")
import token_refresh as TR
import sync_getnote_extra as SX

NOTES = "D:/Software/second-brain-tools/_debug_archive/youxian_notes_stat.json"
VAULT = "D:/我的工作台/第二大脑/02-知识库/订阅主播/博主笔记"
PROGRESS = "D:/Software/second-brain-tools/_youxian_progress.json"
TOPIC_ID = 5029201
PAGE_SIZE = 10
SLEEP = 1.1
MAX_FAILS = 6
BACKOFF = 3


def main():
    state, tok, cookies = SX.load_state()
    targets = json.load(open(NOTES, encoding="utf-8"))
    targets = [t for t in targets if isinstance(t["total"], int) and t["total"] > 0]

    prog = {}
    if os.path.exists(PROGRESS):
        try:
            prog = json.load(open(PROGRESS, encoding="utf-8"))
        except Exception:
            pass

    grand = 0
    for t in targets:
        fid, name, expect = t["id"], t["name"], t["total"]
        key = str(fid)
        rec = prog.get(key, {"done_pages": [], "done": False})
        done_pages = set(rec.get("done_pages", []))
        out_file = "%s/%s_%d.json" % (VAULT, name.replace("/", "_").replace("（", "(").replace("）", ")"), fid)

        all_posts = {}
        if os.path.exists(out_file):
            try:
                for p in json.load(open(out_file, encoding="utf-8"))["posts"]:
                    all_posts[str(p["post_id"])] = p
            except Exception:
                pass
        if rec.get("done") and len(all_posts) >= expect:
            print("[跳过] %s 已完成 %d/%d" % (name, len(all_posts), expect), flush=True)
            grand += len(all_posts)
            continue

        print("\n>>> %s (id=%d, 期望%d条) 已有%d条" % (name, fid, expect, len(all_posts)), flush=True)
        fails, page = 0, 1
        while True:
            if page in done_pages:
                page += 1
                continue
            c, fails = SX.post(tok, cookies, {"topic_id": TOPIC_ID, "follow_id": fid,
                                              "page": page, "page_size": PAGE_SIZE},
                               fails, state)
            if fails == -999:
                print("!! token 失效且无法续期，中止", flush=True)
                return
            if c is None:
                print("   第%d页失败(连续%d次)" % (page, fails), flush=True)
                if fails >= MAX_FAILS:
                    print("   熔断，稍后重跑续传", flush=True)
                    break
                time.sleep(min(BACKOFF * (2 ** (fails - 1)), 30))
                continue
            fails = 0
            posts = c.get("posts", [])
            for p in posts:
                all_posts[str(p["post_id"])] = p
            total = c.get("total", expect)
            print("   p%d +%d (累计%d/%d, more=%s)" %
                  (page, len(posts), len(all_posts), total, c.get("has_more")), flush=True)
            done_pages.add(page)
            if not c.get("has_more") or not posts:
                rec["done"] = True
                break
            page += 1
            time.sleep(SLEEP)

        os.makedirs(VAULT, exist_ok=True)
        payload = {"blogger_id": fid, "blogger_name": name, "expected_count": total,
                   "fetched_count": len(all_posts), "topic_id": TOPIC_ID,
                   "as_of": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "posts": sorted(all_posts.values(),
                                   key=lambda x: x.get("post_publish_time", 0), reverse=True)}
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        rec["done_pages"] = sorted(done_pages)
        rec["fetched"] = len(all_posts)
        prog[key] = rec
        json.dump(prog, open(PROGRESS, "w", encoding="utf-8"), ensure_ascii=False)
        grand += len(all_posts)
        print("   [完成] %s -> %d 条" % (name, len(all_posts)), flush=True)

    print("\n=== 本轮累计 %d 条 ===" % grand, flush=True)


if __name__ == "__main__":
    main()
