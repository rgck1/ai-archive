# -*- coding: utf-8 -*-
"""
得到大脑「任意公开库 × 任意博主」笔记抽取器（通用版）

与 sync_blogger_notes.py 的区别：topic_id / follow_id 全部参数化，
用于抽取散落在 43 个公开分享库里的博主（如商业素材库里的小Lin说）。

输出格式与 sync_blogger_notes.py 完全一致，可直接用 db.import_blogger_json 入库。

用法：
  python sync_getnote_extra.py --topic-id 58674 --follow-id 80055 --name 小Lin说
  python sync_getnote_extra.py --topic-id 58674 --follow-id 80055 --name 小Lin说 --max-pages 2
  python sync_getnote_extra.py --topic-id 58674 --follow-id 80055 --name 小Lin说 --dry-run
"""
import json, os, sys, time, uuid, argparse, urllib.request, urllib.error
import token_refresh as TR

VAULT = r"D:/我的工作台/第二大脑/02-知识库/订阅主播/博主笔记"
HOST = "https://knowledge-api.trytalks.com"
POSTS_PATH = "/v1/web/follow/account/posts"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")
PAGE_SIZE = 10
SLEEP = 1.2
MAX_FAILS = 6
BACKOFF_BASE = 3


def load_state():
    s = TR.load_state()
    if not s.get("_token"):
        raise RuntimeError("web_token.json 缺少 _token")
    tok, changed = TR.ensure_fresh(s, margin=600)
    tag = "已自动续期" if changed else "当前有效"
    print("[token] %s，剩余 %d 秒" % (tag, TR.jwt_exp(tok) - int(time.time())))
    return s, tok, {c["name"]: c["value"] for c in s.get("cookies", [])}


def make_headers(tok, cookies):
    return {
        "User-Agent": UA, "Authorization": "Bearer " + tok,
        "Content-Type": "application/json", "Xi-Csrf-Token": cookies.get("csrfToken", ""),
        "X-Request-ID": uuid.uuid4().hex, "Xi-Client-Source": "getnote",
        "X-Appid": "3", "X-Av": "1.2.2",
        "Cookie": "; ".join("%s=%s" % (k, v) for k, v in cookies.items()),
        "Referer": "https://www.biji.com/",
    }


def post(tok, cookies, params, fails, state):
    req = urllib.request.Request(HOST + POSTS_PATH, data=json.dumps(params).encode(),
                                 headers=make_headers(tok, cookies), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
            hcode = d.get("h", {}).get("c")
            if hcode not in (0, None):
                raise RuntimeError("业务错误: %s" % d.get("h", {}).get("e"))
            return d.get("c", {}), 0
    except urllib.error.HTTPError as e:
        if e.code in (401, 403) and state is not None:
            try:
                newtok = TR.refresh(state)
                print("   [token] 请求中失效，已续期，重试本页")
                return post(newtok, cookies, params, fails, state)
            except Exception as re:
                print("   [token] 续期失败: %s" % str(re)[:80])
                return None, -999
        return None, fails + 1
    except Exception:
        return None, fails + 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic-id", type=int, required=True)
    ap.add_argument("--follow-id", type=int, required=True)
    ap.add_argument("--name", required=True, help="博主名（用于输出文件名与 source）")
    ap.add_argument("--max-pages", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    state, tok, cookies = load_state()
    if not args.dry_run:
        os.makedirs(VAULT, exist_ok=True)
    out_file = "%s/%s_%d.json" % (VAULT, args.name.replace("/", "_"), args.follow_id)
    all_posts = {}
    if os.path.exists(out_file):
        try:
            for p in json.load(open(out_file, encoding="utf-8"))["posts"]:
                all_posts[str(p["post_id"])] = p
        except Exception:
            pass
    print(">>> %s (topic=%d, follow=%d) 已有%d条" %
          (args.name, args.topic_id, args.follow_id, len(all_posts)))

    fails, page = 0, 1
    while True:
        if args.max_pages and page > args.max_pages:
            break
        c, fails = post(tok, cookies, {"topic_id": args.topic_id, "follow_id": args.follow_id,
                                       "page": page, "page_size": PAGE_SIZE}, fails, state)
        if fails == -999:
            print("!! token 失效且无法续期，请重新抓取网页 token")
            return
        if c is None:
            print("   第%d页失败(连续%d次)" % (page, fails))
            if fails >= MAX_FAILS:
                print("   熔断，停止")
                break
            time.sleep(min(BACKOFF_BASE * (2 ** (fails - 1)), 30))
            continue
        fails = 0
        posts = c.get("posts", [])
        for p in posts:
            all_posts[str(p["post_id"])] = p
        total = c.get("total", 0)
        print("   第%d页 +%d条 (累计%d/%d, has_more=%s)" %
              (page, len(posts), len(all_posts), total, c.get("has_more")))
        if not c.get("has_more") or not posts:
            break
        page += 1
        time.sleep(SLEEP)

    if not args.dry_run:
        payload = {"blogger_id": args.follow_id, "blogger_name": args.name,
                   "expected_count": total, "fetched_count": len(all_posts),
                   "topic_id": args.topic_id,
                   "as_of": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "posts": sorted(all_posts.values(),
                                   key=lambda x: x.get("post_publish_time", 0), reverse=True)}
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        print("已写入:", out_file)
    print("[完成] %s -> %d 条" % (args.name, len(all_posts)))


if __name__ == "__main__":
    main()
