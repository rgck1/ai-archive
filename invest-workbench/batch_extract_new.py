# -*- coding: utf-8 -*-
"""
批量抽取「日常收集」库新关注博主的笔记（带断点续传 + 熔断）。

读取 _debug_archive/new_following_notes.json 里有笔记的博主，
逐位分页抽取，输出与 sync_blogger_notes.py 同格式的 JSON 到博主笔记目录。
token 中途失效自动刷新；单博主连续失败熔断；进度写 _new_batch_progress.json。

用法：python batch_extract_new.py            # 全量
      python batch_extract_new.py --retry    # 只重试上次熔断/失败的博主
"""
import json, os, sys, time, argparse
import token_refresh as TR
import sync_getnote_extra as SX

NOTES = "D:/Software/second-brain-tools/_debug_archive/new_following_notes.json"
VAULT = "D:/我的工作台/第二大脑/02-知识库/订阅主播/博主笔记"
PROGRESS = "D:/Software/second-brain-tools/_new_batch_progress.json"
TOPIC_ID = 5022804
PAGE_SIZE = 10
SLEEP = 1.1
MAX_FAILS = 6
BACKOFF = 3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--retry", action="store_true", help="只处理上次未完成的博主")
    args = ap.parse_args()

    state, tok, cookies = SX.load_state()
    targets = json.load(open(NOTES, encoding="utf-8"))
    targets = [t for t in targets if isinstance(t["total"], int) and t["total"] > 0]

    prog = {}
    if os.path.exists(PROGRESS):
        try:
            prog = json.load(open(PROGRESS, encoding="utf-8"))
        except Exception:
            pass

    if args.retry:
        targets = [t for t in targets if not prog.get(str(t["id"]), {}).get("done")]
        print("重试模式：%d 位未完成" % len(targets))

    grand = 0
    for t in targets:
        fid, name, expect = t["id"], t["name"], t["total"]
        key = str(fid)
        rec = prog.get(key, {"done_pages": [], "done": False})
        done_pages = set(rec.get("done_pages", []))
        out_file = "%s/%s_%d.json" % (VAULT, name.replace("/", "_"), fid)

        all_posts = {}
        if os.path.exists(out_file):
            try:
                for p in json.load(open(out_file, encoding="utf-8"))["posts"]:
                    all_posts[str(p["post_id"])] = p
            except Exception:
                pass
        if rec.get("done") and len(all_posts) >= expect:
            print("[跳过] %s 已完成 %d/%d" % (name, len(all_posts), expect))
            grand += len(all_posts)
            continue

        print("\n>>> %s (id=%d, 期望%d条) 已有%d条" % (name, fid, expect, len(all_posts)))
        fails, page = 0, 1
        while True:
            if page in done_pages:
                page += 1
                continue
            c, fails = SX.post(tok, cookies, {"topic_id": TOPIC_ID, "follow_id": fid,
                                              "page": page, "page_size": PAGE_SIZE},
                               fails, state)
            if fails == -999:
                print("!! token 失效且无法续期，中止")
                return
            if c is None:
                print("   第%d页失败(连续%d次)" % (page, fails))
                if fails >= MAX_FAILS:
                    print("   熔断，稍后 --retry 续传")
                    break
                time.sleep(min(BACKOFF * (2 ** (fails - 1)), 30))
                continue
            fails = 0
            posts = c.get("posts", [])
            for p in posts:
                all_posts[str(p["post_id"])] = p
            total = c.get("total", expect)
            print("   p%d +%d (累计%d/%d, more=%s)" %
                  (page, len(posts), len(all_posts), total, c.get("has_more")))
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
        print("   [完成] %s -> %d 条" % (name, len(all_posts)))

    print("\n=== 本轮累计 %d 条 ===" % grand)


if __name__ == "__main__":
    main()
