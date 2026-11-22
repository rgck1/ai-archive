# -*- coding: utf-8 -*-
"""生成「新关注博主接入结果」HTML 报告（动态读数据）"""
import json, io, sys, os, time
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
BASE = "D:/Software/second-brain-tools"
VAULT = "D:/我的工作台/第二大脑/02-知识库/订阅主播/博主笔记"
OUT = "D:/我的工作台/02.输出区/新关注博主接入结果_2026-11-21.html"

# 分级标注（来自之前的财经45位评估 + 类别相关性）
TIER = {
    "温义飞的急救财经": ("第一梯队", "A", "热点逻辑拆解案例库，重点"),
    "牧哥研报解读": ("第一梯队", "A", "外文投行研报信息差素材池，重点"),
    "卢麒元视角": ("第二梯队", "B", "宏观框架补充，只做仓位过滤"),
    "财才说": ("第二梯队", "B", "泛财经观点，质量待验证"),
    "太学TAIXUE": ("第二梯队", "B", "时代信号拆解，泛认知向"),
    "林笙燃": ("第二梯队", "B", "商业逻辑案例素材"),
    "质子黄金": ("第二梯队", "B", "黄金主题，与ETF主线关联有限"),
    "BRTV 天下财经": ("第二梯队", "B", "财经媒体，仅做事实底稿"),
    "一分钟看懂XWLB": ("第二梯队", "B", "媒体类，价值低"),
    "老何学院": ("第二梯队", "B", "股票实战，谨慎"),
    "易睦修-PYTA交易实讲": ("第二梯队", "B", "机构交易法，谨慎"),
    "金融说": ("第二梯队", "B", "暂未聚合出笔记，待观察"),
    "东风速探": ("额外关注", "?", "未列入前两梯队，实际订阅中出现"),
}


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def main():
    notes = json.load(io.open(BASE + "/_debug_archive/new_following_notes.json", encoding="utf-8"))
    results = []
    for t in notes:
        n = t["name"]
        f = "%s/%s_%d.json" % (VAULT, n.replace("/", "_"), t["id"])
        cnt, asof, has_post = 0, "", ""
        if os.path.exists(f):
            d = json.load(io.open(f, encoding="utf-8"))
            cnt = d.get("fetched_count", 0)
            asof = d.get("as_of", "")
            posts = d.get("posts", [])
            if posts:
                has_post = (posts[0].get("post_title") or "")[:50]
        tier, grade, comment = TIER.get(n, ("未标注", "?", ""))
        results.append({"name": n, "id": t["id"], "expect": t["total"],
                        "cnt": cnt, "tier": tier, "grade": grade,
                        "comment": comment, "asof": asof, "sample": has_post})
    results.sort(key=lambda x: ({"第一梯队": 0, "第二梯队": 1, "额外关注": 2}.get(x["tier"], 3), -x["cnt"]))

    total = sum(x["cnt"] for x in results)
    ok = [x for x in results if x["cnt"] > 0]
    zero = [x for x in results if x["cnt"] == 0]

    h = []
    h.append("""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>新关注博主接入结果 · 2026-11-21</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f5f6f8;color:#1f2430;font:14px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:28px 20px 60px}h1{font-size:24px;margin:0 0 6px}
h2{font-size:18px;margin:28px 0 12px;padding-left:10px;border-left:4px solid #3457d5}
.sub{color:#6b7280;font-size:13px;margin-bottom:18px}
.card{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:16px 20px;margin:14px 0}
.stats{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}
.stat{flex:1;min-width:140px;background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:16px;text-align:center}
.stat b{display:block;font-size:26px;color:#3457d5}.stat span{color:#6b7280;font-size:13px}
table{width:100%;border-collapse:collapse;background:#fff;font-size:13px}
th,td{border:1px solid #e5e7eb;padding:7px 10px;text-align:left}th{background:#f3f4f6}
tr:nth-child(even) td{background:#fafbfc}.num{text-align:right;white-space:nowrap}
.tag{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;font-weight:600}
.t1{background:#fee2e2;color:#b91c1c}.t2{background:#dbeafe;color:#1d4ed8}
.tx{background:#fef3c7;color:#92400e}.ga{background:#dcfce7;color:#0a7d3f}
.gb{background:#e0e7ff;color:#3730a3}.note{background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:12px 16px;color:#92400e;margin:14px 0}
.ok{background:#ecfdf5;border:1px solid #a7f3d0;border-radius:8px;padding:12px 16px;color:#065f46;margin:14px 0}
.small{font-size:12px;color:#6b7280}
</style></head><body><div class="wrap">
<h1>新关注博主接入结果</h1>
<div class="sub">生成时间：{{GEN_TIME}} ｜ 数据源：得到「日常收集」库（topic=5022804）订阅博主</div>
""".replace("{{GEN_TIME}}", time.strftime("%Y-%m-%d %H:%M")))

    h.append('<div class="stats">')
    h.append('<div class="stat"><b>%d</b><span>新增订阅博主</span></div>' % len(results))
    h.append('<div class="stat"><b>%d</b><span>已抽取入库</span></div>' % len(ok))
    h.append('<div class="stat"><b>%d</b><span>待聚合（0条）</span></div>' % len(zero))
    h.append('<div class="stat"><b>%d</b><span>本轮笔记总数</span></div>' % total)
    h.append("</div>")

    h.append('<div class="ok"><b>完成情况：</b>你在得到 App 手动关注的博主已生效——「日常收集」库订阅数从 13 涨到 26。本轮抽取 %d 位博主、共 <b>%d 条</b> AI 结构化摘要笔记，已写入第二大脑库并导入数据库。</div>' % (len(ok), total))

    h.append("""<div class="note"><b>两点差异说明：</b><br>
① 你提到的是第一+第二梯队共 14 位，但实际订阅里<b>没有「福总说实话 / 机构一手调研（福总）」这对双号</b>——它们之前评估时是同一人的大小号，如需接入请再手动关注。<br>
② 订阅里多出一位<b>「东风速探」</b>（你没在前两梯队名单里提到），实际已订阅且有 281 条笔记，本轮一并按「额外关注」抽取，请确认是否保留。</div>""")

    h.append("<h2>接入明细</h2><table><tr><th>博主</th><th>梯队</th><th>等级</th><th class='num'>聚合总数</th><th class='num'>已抽条数</th><th>样例 / 备注</th></tr>")
    for x in results:
        tc = {"第一梯队": "t1", "第二梯队": "t2"}.get(x["tier"], "tx")
        gc = "ga" if x["grade"] == "A" else "gb"
        detail = (x["sample"] or "—") + (" ｜ " + x["comment"] if x["comment"] else "")
        h.append("<tr><td>%s</td><td><span class='tag %s'>%s</span></td><td><span class='tag %s'>%s</span></td><td class='num'>%d</td><td class='num'>%d</td><td class='small'>%s</td></tr>" %
                 (esc(x["name"]), tc, x["tier"], gc, x["grade"], x["expect"], x["cnt"], esc(detail)))
    h.append("</table>")

    h.append("""<h2>下一步</h2><div class="card">
<p>1. <b>福总双号</b>：如需接入，请在得到 App 关注「机构一手调研（福总）」（大号，178万粉）或「福总说实话」，关注后告诉我用同法抽取。</p>
<p>2. <b>东风速探</b>：确认是否保留在知识库；不需要的话我可以把它从第二大脑移除（但不影响你的得到订阅）。</p>
<p>3. <b>金融说</b>：已关注但聚合 0 条，可能平台尚未生成笔记，过几天再看；也可能内容源不被得到聚合。</p>
<p class="small">边界：本轮只做「抽取+入库」，未改动你的得到订阅设置；「得到聚合笔记」是平台 AI 生成的二手摘要，非原始视频口播，观点仍需经七维自查。</p>
</div></div></body></html>""")

    io.open(OUT, "w", encoding="utf-8").write("\n".join(h))
    print("报告生成:", OUT)
    print("已抽 %d 位 / %d 条，待聚合 %d 位" % (len(ok), total, len(zero)))


if __name__ == "__main__":
    main()
