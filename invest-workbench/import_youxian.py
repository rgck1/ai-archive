# -*- coding: utf-8 -*-
"""把「优先」库 7 位博主笔记导入第二大脑（走应用幂等接口，逐位导入）。"""
import json, io, os, urllib.request, urllib.parse, sys

sys.stdout.reconfigure(encoding="utf-8")
APP = "http://127.0.0.1:8765"
VAULT = "D:/我的工作台/第二大脑/02-知识库/订阅主播/博主笔记"
LOG = "D:/Software/second-brain-youxian-import.log"

FILES = ["李善友_1490415.json", "粗人(力量矩阵营养学)_1490410.json",
         "黄执中_1490402.json", "陈石(营养，挨揍，撸铁)_1490399.json",
         "赵玉平老师讲国学_1490397.json", "厚大.罗翔说刑法_1490394.json",
         "无穷小亮的科普日常_1490392.json"]


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
    ta = ts = 0
    for f in FILES:
        path = os.path.join(VAULT, f)
        if not os.path.exists(path):
            log("  [缺失] %s" % f)
            continue
        r = post("/api/import-bloggers", {"file": f})
        ta += r["added"]; ts += r["skipped"]
        log("  %-24s 新增+%-5d 跳过%-5d (文件%d条)" %
            (r["blogger"][:24], r["added"], r["skipped"], r["total"]))
    after = get("/api/stats")
    log("\n合计: 新增 %d 条, 跳过 %d 条" % (ta, ts))
    log("导入后笔记总数: %d (预期 %d)" % (after["notes"], before + ta))

    log("\n=== 7位 source 分布 ===")
    keys = ["李善友", "粗人", "黄执中", "陈石", "赵玉平", "罗翔", "无穷小亮"]
    for s in after["sources"]:
        if any(k in s["source"] for k in keys):
            log("  %-28s %d 条" % (s["source"].replace("blogger:", ""), s["count"]))

    log("\n=== 搜索抽查 ===")
    for q in ["第一性原理", "罗翔", "减脂", "无穷小亮"]:
        r = get("/api/search?q=" + urllib.parse.quote(q))
        log("  [%s] %d 条" % (q, r["total"]))


if __name__ == "__main__":
    main()
