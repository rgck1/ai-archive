# -*- coding: utf-8 -*-
"""生成「170位博主 × 得到库对接可行性全量排查」报告"""
import json, io, sys, datetime
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")
DATA = "D:/我的工作台/system/douyin_getnote_match.json"
OUT = "D:/我的工作台/02.输出区/全部博主_得到库对接排查_2026-11-21.html"


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def wan(v):
    try:
        v = int(v)
    except Exception:
        return "-"
    return "%.1f万" % (v / 10000.0) if v >= 10000 else str(v)


def main():
    d = json.load(io.open(DATA, encoding="utf-8"))
    items = d["items"]
    s = d["summary"]
    A = [x for x in items if x["status"].startswith("A")]
    B = [x for x in items if x["status"].startswith("B")]
    C = [x for x in items if x["status"].startswith("C")]
    Cbig = sorted([x for x in C if (isinstance(x["followers"], int) and x["followers"] >= 100000)],
                  key=lambda x: -int(x["followers"]))

    # 类别×状态矩阵
    catstat = defaultdict(Counter)
    for x in items:
        catstat[x["category"]][x["status"][0]] += 1

    h = []
    h.append("""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>全部博主 × 得到库对接排查 · 2026-11-21</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f5f6f8;color:#1f2430;font:14px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:24px;margin:0 0 6px}h2{font-size:18px;margin:30px 0 12px;padding-left:10px;border-left:4px solid #3457d5}
h3{font-size:15px;margin:18px 0 8px}.sub{color:#6b7280;font-size:13px;margin-bottom:20px}
.card{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:18px 20px;margin:14px 0}
.stats{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0}
.stat{flex:1;min-width:150px;background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:16px;text-align:center}
.stat b{display:block;font-size:28px;color:#3457d5}.stat span{color:#6b7280;font-size:13px}
.stat.a b{color:#0a7d3f}.stat.b b{color:#3457d5}.stat.c b{color:#c2410c}
table{width:100%;border-collapse:collapse;background:#fff;font-size:13px}
th,td{border:1px solid #e5e7eb;padding:7px 10px;text-align:left;vertical-align:top}
th{background:#f3f4f6;position:sticky;top:0;font-weight:600}tr:nth-child(even) td{background:#fafbfc}
.tag{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;font-weight:600}
.ta{background:#dcfce7;color:#0a7d3f}.tb{background:#dbeafe;color:#1d4ed8}.tc{background:#ffedd5;color:#c2410c}
.cat{color:#4b5563;font-size:12px}.num{text-align:right;white-space:nowrap}
.note{background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:12px 16px;color:#92400e;margin:14px 0}
.ok{background:#ecfdf5;border:1px solid #a7f3d0;border-radius:8px;padding:12px 16px;color:#065f46;margin:14px 0}
code{background:#f3f4f6;padding:1px 5px;border-radius:4px;font-size:12px}
.scroll{max-height:560px;overflow:auto;border:1px solid #e5e7eb;border-radius:8px}
.small{font-size:12px;color:#6b7280}
</style></head><body><div class="wrap">
<h1>全部博主 × 得到库对接可行性全量排查</h1>
<div class="sub">生成时间：2026-11-21 ｜ 数据源：抖音关注 170 位 × 得到公开库 43 个（223 位聚合博主）+ 你的「日常收集」库 13 位</div>
""")

    h.append('<div class="stats">')
    h.append('<div class="stat"><b>%d</b><span>抖音关注总数</span></div>' % len(items))
    h.append('<div class="stat a"><b>%d</b><span>A 已入库（不用做）</span></div>' % len(A))
    h.append('<div class="stat b"><b>%d</b><span>B 可直抽（今天可做）</span></div>' % len(B))
    h.append('<div class="stat c"><b>%d</b><span>C 需手动关注</span></div>' % len(C))
    h.append("</div>")

    h.append("""<div class="ok"><b>今天已经做完的：</b>小Lin说（商业素材库 34 条 AI 摘要）已抽取并入库，第二大脑笔记数 4113 → 4147。
全文搜索验证通过（如「稳定币」命中《一口气了解稳定币》）。</div>""")

    h.append("""<div class="note"><b>关键结论（为什么只有 1 位「可直抽」）：</b>
得到大脑里的「博主」是平台自己聚合的知识博主，跟你抖音关注的 170 位几乎不重合。
43 个公开库聚合的 223 位里，多为「得到系」和知识类博主（罗振宇、得到新商学、香帅等）；
你关注的是抖音生态。精确 + 归一化匹配后，除了你库里已订阅的 13 位，只多找到「张雪峰老师」1 位能直接抽。
程序化「加订阅/关注博主」接口（<code>follow/create</code>、<code>watch/blogger/list</code>）实测均报「服务异常」，
所以 C 类只能走<b>你在得到 App 里手动关注</b>这条路，且关注后是否聚合、多久聚合由平台决定，不可控。</div>""")

    # 三类说明
    h.append("<h2>一、三类结论与操作建议</h2>")
    h.append("""<div class="card">
<h3><span class="tag ta">A 已入库</span> %d 位 — 不用再做</h3>
<p class="small">已在第二大脑（你「日常收集」库订阅的 13 位，其中小Lin说为今天新增）。内容已抽取、可搜索，无需重复操作。</p>
<h3><span class="tag tb">B 可直抽</span> %d 位 — 今天就能做</h3>
<p class="small">张雪峰老师（教育成长类）：得到「高考志愿填报」库有两个 follow 源，分别 65 / 68 条带 AI 摘要的笔记，格式与现有 13 位一致，随时可抽。但与你的投资主线关联弱，可由你决定是否入库。</p>
<h3><span class="tag tc">C 需手动关注</span> %d 位 — 需你手动操作</h3>
<p class="small">得到库里目前没有这些博主。需在得到 App 关注该博主，等平台聚合出笔记后才能抽。聚合与否、时效由得到平台决定。下面列了按粉丝量排序的优先候选，供你挑重点去关注。</p>
</div>""" % (len(A), len(B), len(C)))

    # 类别矩阵
    h.append("<h2>二、按类别看分布</h2>")
    h.append("<table><tr><th>类别</th><th class='num'>总数</th><th class='num'>A 已入库</th><th class='num'>B 可直抽</th><th class='num'>C 需手动关注</th></tr>")
    for cat in sorted(catstat, key=lambda c: -sum(catstat[c].values())):
        c = catstat[cat]
        tot = sum(c.values())
        h.append("<tr><td>%s</td><td class='num'>%d</td><td class='num'>%d</td><td class='num'>%d</td><td class='num'>%d</td></tr>" %
                 (esc(cat), tot, c["A"], c["B"], c["C"]))
    h.append("</table>")

    # C类高价值候选
    h.append("<h2>三、C 类优先手动关注候选（粉丝 ≥ 10 万，共 %d 位）</h2>" % len(Cbig))
    h.append('<p class="small">这是「值得先去得到 App 手动关注」的重点名单。按粉丝量排序，粉丝量通常代表内容产量与平台聚合概率。标注为「财经投资 / 商业创业 / 认知成长」的与你第二大脑主线最相关。</p>')
    h.append('<div class="scroll"><table><tr><th>#</th><th>博主</th><th>类别</th><th class="num">粉丝</th><th class="num">作品</th><th>得到库状态</th></tr>')
    for i, x in enumerate(Cbig, 1):
        rel = "重点相关" if x["category"] in ("财经投资", "商业创业", "认知成长") else "一般"
        h.append("<tr><td>%d</td><td>%s</td><td class='cat'>%s</td><td class='num'>%s</td><td class='num'>%s</td><td class='cat'>未收录 · %s</td></tr>" %
                 (i, esc(x["nickname"]), esc(x["category"]), wan(x["followers"]),
                  esc(x["awemes"]), rel))
    h.append("</table></div>")

    # 全量明细
    h.append("<h2>四、全部 170 位逐位明细</h2>")
    h.append('<div class="scroll"><table><tr><th>#</th><th>博主</th><th>类别</th><th class="num">粉丝</th><th>状态</th><th>说明 / 所在库</th></tr>')
    status_order = {"A": 0, "B": 1, "C": 2}
    for i, x in enumerate(sorted(items, key=lambda y: (status_order[y["status"][0]], -int(y["followers"]) if isinstance(y["followers"], int) else 0)), 1):
        st = x["status"][0]
        cls = {"A": "ta", "B": "tb", "C": "tc"}[st]
        label = {"A": "已入库", "B": "可直抽", "C": "需关注"}[st]
        if x["where"]:
            wh = "; ".join("%s(topic=%s%s)" % (w["lib"], w["topic_id"],
                  ",follow=%s" % w["follow_id"] if w.get("follow_id") else "") for w in x["where"])
        else:
            wh = x["note"]
        h.append("<tr><td>%d</td><td>%s</td><td class='cat'>%s</td><td class='num'>%s</td><td><span class='tag %s'>%s</span></td><td class='cat'>%s</td></tr>" %
                 (i, esc(x["nickname"]), esc(x["category"]), wan(x["followers"]), cls, label, esc(wh)))
    h.append("</table></div>")

    h.append("""<h2>五、下一步（等你拍板）</h2><div class="card">
<p><b>选项 1：</b>把「张雪峰老师」也抽进来入库（65+68 条，但属教育类，与投资主线弱相关）。</p>
<p><b>选项 2：</b>你从第三节名单里挑出真正想要的几位，在得到 App 手动关注；等平台聚合后告诉我，我再按同一套脚本抽取入库。</p>
<p><b>选项 3：</b>维持现状——只保留已入库的 14 位（13 位日常收集 + 小Lin说），不再扩充。</p>
<p class="small">说明：本报告只做客观匹配与可行性判定，未改动任何关注/订阅设置，也未自动抓取 C 类内容。抖音视频/直播接口此前验证不稳定，本次没有依赖它。</p>
</div>
<div class="note">本报告为数据对接排查，不构成投资建议；任何主播观点需经你既有的七维自查后方可参考。</div>
</div></body></html>""")

    io.open(OUT, "w", encoding="utf-8").write("\n".join(h))
    print("报告生成:", OUT)
    print("字符数:", len("\n".join(h)))


if __name__ == "__main__":
    main()
