# -*- coding: utf-8 -*-
"""
生成「170 位抖音博主 × 得到库可抽取性」逐位匹配清单。

三类结果：
  A 已入库      —— 已在第二大脑（日常收集库13位 + 小Lin说）
  B 可直抽      —— 在得到 43 公开库里找到同名博主，有 topic_id/follow_id，可直接抽
  C 需手动关注  —— 得到库里没有，需要在得到 App 手动关注后平台才会聚合

输出：D:/我的工作台/system/douyin_getnote_match.json
"""
import json, os, re, sys, io
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
USERS = "D:/我的工作台/system/douyin_classified.json"
ALLKB = "D:/Software/second-brain-tools/_debug_archive/all_kb_bloggers.json"
VAULT = "D:/我的工作台/第二大脑/02-知识库/订阅主播/博主笔记"
OUT = "D:/我的工作台/system/douyin_getnote_match.json"

# 用户自己「日常收集」库订阅的13位（可直抽，已大多入库）
MINE = {"房子(新允珩)", "葫芦军师", "量化投资邢不行啊", "独行者李明", "凯心",
        "猫眼儿观世界", "付鹏的财经世界", "量化躺平佟掌柜", "阿华（机构一手调研）",
        "熊猫有财", "主力行为学（杨宁）", "斌哥 Bg", "全能的野人"}
# 用户库 topic 与 follow 映射（从本地已入库文件名 + 之前的 stats 推断：日常收集库 topic=5022804）
MINE_TOPIC = 5022804


def core(s):
    s = (s or "").strip().lower()
    s = re.sub(r"[（(【\[].*?[）)】\]]", "", s)
    s = re.sub(r"[\s\u3000·・.,，。\-—_!！?？:：|｜]", "", s)
    for w in ["官方", "老师", "学长", "本人", "频道", "同学"]:
        s = s.replace(w, "")
    return s


def main():
    users = json.load(io.open(USERS, encoding="utf-8"))
    kbs = json.load(io.open(ALLKB, encoding="utf-8"))

    # 已入库博主名
    done_names = {}
    for f in os.listdir(VAULT):
        if f.endswith(".json"):
            d = json.load(io.open(os.path.join(VAULT, f), encoding="utf-8"))
            done_names[core(d.get("blogger_name", ""))] = d.get("blogger_name")

    # 得到公开库博主 -> 位置列表
    pub = defaultdict(list)
    for kb in kbs:
        for b in kb["bloggers"]:
            pub[b["name"]].append({"lib": kb["lib_name"], "alias": kb["alias"],
                                   "topic_id": kb["topic_id"], "follow_id": b["id"]})
    pub_core = defaultdict(list)
    for nm in pub:
        pub_core[core(nm)].append(nm)

    result = []
    stat = defaultdict(int)
    for u in users:
        nm = u["nickname"]
        c = core(nm)
        item = {"nickname": nm, "category": u["category"], "sub": u.get("sub", ""),
                "followers": u.get("followers"), "awemes": u.get("awemes"),
                "signature": (u.get("signature") or "")[:80], "status": "", "where": [], "note": ""}

        # 1) 是否已入库
        if c in done_names:
            item["status"] = "A_已入库"
            item["note"] = "已抽取到第二大脑，无需重复操作"
        # 2) 是否在用户自己日常收集库(13位)
        elif any(core(x) == c for x in MINE):
            item["status"] = "B_可直抽"
            item["where"] = [{"lib": "日常收集(你的库)", "topic_id": MINE_TOPIC,
                              "follow_id": None, "alias": "YvEVmZDn"}]
            item["note"] = "在你自己的得到库，可直接抽取（follow_id 需按名解析）"
        # 3) 是否在43公开库
        elif c in pub_core:
            item["status"] = "B_可直抽"
            for pnm in pub_core[c]:
                for w in pub[pnm]:
                    item["where"].append(w)
            item["note"] = "得到公开库已有聚合，可直接抽取"
        else:
            item["status"] = "C_需手动关注"
            item["note"] = "得到库未收录，需在得到 App 关注该博主后等平台聚合"

        stat[item["status"]] += 1
        result.append(item)

    json.dump({"generated": "2026-11-21", "total": len(result),
               "summary": dict(stat), "items": result},
              io.open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("匹配完成，总计 %d 位" % len(result))
    for k in sorted(stat):
        print("  %s: %d" % (k, stat[k]))
    print("\n=== B_可直抽 明细 ===")
    for x in result:
        if x["status"] == "B_可直抽":
            print("  [%s] %s -> %s" % (x["category"], x["nickname"],
                  [(w["lib"], w["topic_id"], w["follow_id"]) for w in x["where"]]))
    print("\n输出:", OUT)


if __name__ == "__main__":
    main()
