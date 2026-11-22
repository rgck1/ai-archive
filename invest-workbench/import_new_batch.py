# -*- coding: utf-8 -*-
"""把12位新关注博主笔记导入第二大脑（走应用幂等接口，逐位导入）。"""
import json, io, os, urllib.request, urllib.parse, sys, time

sys.stdout.reconfigure(encoding="utf-8")
APP = "http://127.0.0.1:8765"
VAULT = "D:/我的工作台/第二大脑/02-知识库/订阅主播/博主笔记"
LOG = "D:/Software/second-brain-import.log"

# 本轮12位的文件名
FILES = ["东风速探_1489987.json", "易睦修-PYTA交易实讲_1489976.json",
         "老何学院_1489966.json", "一分钟看懂XWLB_1489945.json",
         "BRTV 天下财经_1489942.json", "质子黄金_1489938.json",
         "林笙燃_1489935.json", "太学TAIXUE_1489933.json",
         "财才说_1489926.json", "卢麒元视角_1489920.json",
         "牧哥研报解读_1489914.json", "温义飞的急救财经_1489909.json"]


def get(p):
    with urllib.request.urlopen(APP + p, timeout=30) as r:
        return json.loads(r.read().decode())


def post(p, body):
    req = urllib.request.Request(APP + p, data=json.dumps(body, ensure_ascii=False).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode())


def main():
    lines = []
    def log(s):
        print(s, flush=True)
        lines.append(s)
        io.open(LOG, "w", encoding="utf-8").write("\n".join(lines))

    before = get("/api/stats")["notes"]
    log("导入前笔记总数: %d" % before)
    total_added = total_skip = 0
    for f in FILES:
        path = os.path.join(VAULT, f)
        if not os.path.exists(path):
            log("  [缺失] %s" % f)
            continue
        r = post("/api/import-bloggers", {"file": f})
        total_added += r["added"]; total_skip += r["skipped"]
        log("  %-24s 新增+%-5d 跳过%-5d (文件%d条)" %
            (r["blogger"][:24], r["added"], r["skipped"], r["total"]))
    after = get("/api/stats")
    log("\n合计: 新增 %d 条, 跳过 %d 条" % (total_added, total_skip))
    log("导入后笔记总数: %d (预期 %d)" % (after["notes"], before + total_added))

    log("\n=== 12位 source 分布 ===")
    for s in after["sources"]:
        if any(k in s["source"] for k in ["东风速探", "易睦修", "老何学院", "一分钟看懂",
               "BRTV", "质子黄金", "林笙燃", "太学", "财才说", "卢麒元", "牧哥", "温义飞"]):
            log("  %-28s %d 条" % (s["source"].replace("blogger:", ""), s["count"]))

    log("\n=== 搜索抽查 ===")
    for q in ["研报", "新闻联播", "黄金", "温义飞"]:
        r = get("/api/search?q=" + urllib.parse.quote(q))
        log("  [%s] %d 条" % (q, r["total"]))


if __name__ == "__main__":
    main()
