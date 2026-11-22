# -*- coding: utf-8 -*-
"""
全量拉取 43 个得到公开分享库的「全部订阅博主」名录。
之前只拉每库 page_size=10，覆盖不全；本脚本分页拉到底。

输出：_debug_archive/all_kb_bloggers.json
结构：[{alias,lib_name,topic_id_digits,creator,bloggers:[{id,name,...}],count}, ...]
"""
import json, urllib.request, sys, time

sys.stdout.reconfigure(encoding="utf-8")
BASE = "https://get-notes.luojilab.com/voicenotes/web/share/topics/"
UA = {"User-Agent": "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 "
                     "Chrome/120 Mobile Safari/537.36", "Xi-App-Client-Source": "getnote"}
KBS = "D:/Software/second-brain-tools/_debug_archive/topic_list.json"
OUT = "D:/Software/second-brain-tools/_debug_archive/all_kb_bloggers.json"
PAGE_SIZE = 20


def get(url, retry=2):
    for i in range(retry + 1):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
                return json.loads(r.read().decode("utf-8", "replace")).get("c", {})
        except Exception as e:
            if i == retry:
                print("    [err] %s" % str(e)[:70])
                return {}
            time.sleep(1.5 * (i + 1))
    return {}


def main():
    kbs = json.load(open(KBS, encoding="utf-8"))
    result = []
    total_bloggers = 0
    for i, kb in enumerate(kbs):
        al = kb.get("id_alias")
        if not al:
            continue
        # 库的数字 topic_id 与名称：share/topic 接口
        tinfo = get(BASE + al)
        tid = tinfo.get("id", "") if isinstance(tinfo, dict) else ""

        allb, page = [], 1
        count = 0
        while page <= 30:
            c = get("%s%s/following?page=%d&page_size=%d" % (BASE, al, page, PAGE_SIZE))
            lst = c.get("list", [])
            if page == 1:
                count = c.get("count", 0)
            allb.extend(lst)
            if not lst or len(allb) >= count:
                break
            page += 1
            time.sleep(0.35)

        # 去重（按 id）
        seen, uniq = set(), []
        for b in allb:
            if b.get("id") in seen:
                continue
            seen.add(b.get("id"))
            uniq.append(b)
        result.append({"alias": al, "lib_name": kb.get("name"), "topic_id": tid,
                       "creator": kb.get("creator"), "count": count,
                       "bloggers": [{"id": b.get("id"), "name": b.get("name"),
                                     "avatar": b.get("avatar", "")} for b in uniq]})
        total_bloggers += len(uniq)
        print("[%2d/%d] %-18s 声明%-4d 实拉%-4d" %
              (i + 1, len(kbs), str(kb.get("name"))[:18], count, len(uniq)))
        time.sleep(0.4)

    json.dump(result, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n完成：%d 个库，累计 %d 个博主条目（含跨库重复）" % (len(result), total_bloggers))
    print("输出:", OUT)


if __name__ == "__main__":
    main()
