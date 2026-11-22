# -*- coding: utf-8 -*-
"""生成「其余125位非财经主播 分类+得到接入优先级」清单报告"""
import json, io, sys, time
from collections import defaultdict, Counter

sys.stdout.reconfigure(encoding="utf-8")
SRC = "D:/我的工作台/system/douyin_classified.json"
OUT = "D:/我的工作台/02.输出区/其余主播分类与得到接入清单_2026-11-21.html"
TXT = "D:/我的工作台/02.输出区/得到关注清单_可复制_2026-11-21.txt"

# 分级映射：博主名 -> (级别, 理由)。未列出的默认 C（信息不足/导流/娱乐/空号）
GRADE = {
    # ===== S 优先关注（知识密度高/主线强相关/权威） =====
    "李善友": ("S", "混沌创办人，《第一性原理》《第二曲线创新》，商业认知经典，沉淀价值高"),
    "黄执中": ("S", "奇葩说BBking、表达演讲导师，沟通表达方法论可沉淀"),
    "赵玉平老师讲国学": ("S", "百家讲坛主讲人，管理学+心理学+博弈论解读名著，知识密度高"),
    "无穷小亮的科普日常": ("S", "《博物》副主编、国家林草科普首席专家，权威自然科普"),
    "陈石（营养，挨揍，撸铁）": ("S", "循证运动营养、NSCA专业背景，契合你减脂保肌目标"),
    "粗人(力量矩阵营养学)": ("S", "SNC运动营养师、NSCA-CPT，力量训练营养，契合你的训练主线"),
    "厚大.罗翔说刑法": ("S", "中国政法大学教授，刑法科普，专业性与可沉淀性俱佳"),
    # ===== A 建议关注（明确知识内容） =====
    "程前朋友圈": ("A", "专注商业观察、传播商业案例，可作商业案例库补充"),
    "冯唐": ("A", "作家+战略管理专家，成事管理学，有体系化内容"),
    "金枪大叔": ("A", "广告营销30年，《借势》《主角》作者，营销方法论"),
    "李潇 格家网络CEO": ("A", "真实创业者，获经纬/顺为投资，创业案例实在"),
    "心理力量": ("A", "心理学内容，可补认知成长线的心理维度"),
    "十三邀": ("A", "深度访谈节目，知识型长内容，适合做观点素材"),
    "42号星球": ("A", "商业科技洞察深逻辑，契合认知+科技主线"),
    "徐和郑": ("A", "前阿里职业经理人、龙席创始人，商业+科技实战"),
    "白朴": ("A", "古书/人文/历史月更深度系列，内容扎实"),
    "历历在用": ("A", "中国史世界史，强调学以致用"),
    "混知": ("A", "知识科普头部，专治不明白，图形化知识密度高"),
    "名郑言顺": ("A", "百科科普360行，不贩卖焦虑，事实型内容"),
    "Q姐和老6": ("A", "消费科普信息差，985+复旦研究型团队"),
    "老雷瘦": ("A", "减脂塑形教练，契合你的健康/减脂主线"),
    "小黑子健身": ("A", "科学健身方法，契合你的训练主线"),
    "皮肤科叶医生": ("A", "公立三甲皮肤科医生，专业医疗科普"),
    "王勇 洪文律所": ("A", "劳动用工合规20年，垂直专业知识"),
    # ===== 已可直抽（特殊） =====
    "张雪峰老师": ("已可直抽", "得到「高考志愿填报」库已有65+68条，无需再手动关注"),
    # ===== B 可选（泛/垂直弱相关/人设向但有内容） =====
    "商业小纸条real": ("B", "商业观察，签名带商务联系，泛商业内容"),
    "胡说老王": ("B", "商业评论，签名信息少，需先观察内容质量"),
    "纯然商业-运准": ("B", "企业流量赋能，偏服务导流"),
    "工地蚂蚁哥": ("B", "20年工程经验，垂直但与主线弱相关"),
    "变强起点": ("B", "商业认知+读书，但橱窗卖书导流"),
    "公鸡大师研究员": ("B", "日化营销+生活小妙招，营销角度可看"),
    "村西边老王": ("B", "14年自媒体老IP，付费咨询导流"),
    "东叔人间帐": ("B", "供应链见闻，AI视频制作，见闻型内容"),
    "飞扬企源｜实体老板落地陪跑": ("B", "企业管理咨询，落地案例可看"),
    "亚马逊每日一店": ("B", "每日拆解跨境爆款，垂直跨境内容实在"),
    "闯商【启明星】": ("B", "商业解析，草根创业视角"),
    "鹤老师": ("B", "认知思维，鸡汤感悟偏多，先观察"),
    "亿文": ("B", "修心成长+中华文化，正能量向"),
    "哈密瓜微课": ("B", "用户手动归认知成长，但签名仅原创保护，资料不足"),
    "我是良哥": ("B", "人生励志，签名明确但内容偏鸡汤"),
    "斌的世界": ("B", "情感关系，带1v1分析导流，内容情感向"),
    "范不慌": ("B", "认知成长+情感关系，商务合作导流"),
    "雪野lovetactic": ("B", "认知实战、人性博弈，偏术与道"),
    "浩威Loveology": ("B", "情感关系、人格成长"),
    "顶层思考力": ("B", "认知思维+读书分享"),
    "子论道": ("B", "人生/感情/事业决策"),
    "明月": ("B", "人生感悟向"),
    "人生悟道 渡人渡己": ("B", "人生感悟向"),
    "大冰": ("B", "人文情感故事，有内容但非知识型"),
    "特务兔说剧": ("B", "影视解说深度解析，偏娱乐内容"),
    "特厨做饭": ("B", "央视美食节目嘉宾，厨艺内容"),
    "卡尼酱🍏": ("B", "生活访谈，人大本科，寻找快乐的人"),
    "清年阁": ("B", "AI教育，联合创始人背书"),
    "科技天选指南": ("B", "数码3C测评，消费决策参考"),
    "阿来说": ("B", "AI时代深度思考，认知向"),
    "程序员三千": ("B", "AI编程工具玩法，垂直实战"),
    "刘小排": ("B", "AI编程实战派，垂直小众"),
    "子墨说AI": ("B", "15年产品经理，AI工程化实战"),
    "（学习在合集）黑羽讲网安": ("B", "网络安全实操，垂直技能"),
    "AI全栈实战": ("B", "独立开发者15年+大厂架构，AI开发"),
    "未知文明研究所所长": ("B", "文明科普，强调客观理性"),
    "磨时艺术": ("B", "爆笑解读历史人文艺术"),
    "思想星丛": ("B", "思想典籍，《神思录》系统原创"),
    "时空管理局": ("B", "历史科普脑洞向"),
    "庸半史": ("B", "长视频深度解析中国古代史"),
    "国学·智慧": ("B", "国学，书籍导流"),
    "平盖尔": ("B", "三本逆袭清华，学习方法，咨询导流"),
    "育婴师韬爸": ("B", "科学育儿，多资质背书"),
    "兔老师讲家庭教育": ("B", "港大教育学硕士，升学规划"),
    "瑞杰谈英语-煜桐文化": ("B", "中英双母语，11年教学，情境学习"),
    "央视新闻": ("B", "权威新闻，可作事实底稿，但非知识博主"),
    "模型师老原儿": ("B", "模型艺术科普，垂直艺术"),
    "家电手记": ("B", "家电选购干货，消费参考"),
    "林霖心医": ("B", "心理健康内容"),
    "心医林霖（号外版）": ("B", "心理师视角解读国际风云"),
    "牛哥说家电": ("B", "20年家电，型号资料分享"),
    "Wilson学长": ("B", "家电测评选购干货"),
    "王洋律师": ("B", "知名律所，刑案民商"),
    "婚姻家事张洁律师": ("B", "婚姻家事法律，法治宣讲"),
}

# C 级理由按子类批量给
C_REASON = {
    "待确认": "信息不足/空号/切片号/作品为0，无法可靠判断内容领域",
    "生活娱乐": "纯娱乐/带货/日常/才艺/婚恋，知识沉淀价值低",
    "家居生活": "家居装修家具销售向，导流或消费内容，与主线弱相关",
}


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def wan(v):
    try:
        v = int(v)
    except Exception:
        return "-"
    return "%.0f万" % (v / 10000.0) if v >= 10000 else str(v)


def grade_of(x):
    nm = x["nickname"]
    if nm in GRADE:
        return GRADE[nm]
    sub = x.get("sub", "")
    reason = C_REASON.get(x["category"], "内容偏营销导流/人设口号，知识沉淀价值低")
    return ("C", reason)


def main():
    d = json.load(io.open(SRC, encoding="utf-8"))
    others = [x for x in d if x["category"] != "财经投资"]
    for x in others:
        x["grade"], x["reason"] = grade_of(x)

    cnt = Counter(x["grade"] for x in others)
    # 按大类分组，组内按级别+粉丝排序
    order = {"S": 0, "A": 1, "已可直抽": 2, "B": 3, "C": 4}
    bycat = defaultdict(list)
    for x in others:
        bycat[x["category"]].append(x)
    for cat in bycat:
        bycat[cat].sort(key=lambda y: (order[y["grade"]],
                         -int(y["followers"]) if isinstance(y["followers"], int) else 0))

    h = []
    h.append("""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>其余主播分类与得到接入清单 · 2026-11-21</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f5f6f8;color:#1f2430;font:14px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:28px 20px 60px}h1{font-size:24px;margin:0 0 6px}
h2{font-size:18px;margin:30px 0 12px;padding-left:10px;border-left:4px solid #3457d5}
.sub{color:#6b7280;font-size:13px;margin-bottom:18px}
.card{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:16px 20px;margin:14px 0}
.stats{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}
.stat{flex:1;min-width:110px;background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:14px 10px;text-align:center}
.stat b{display:block;font-size:24px}.stat span{font-size:12px;color:#6b7280}
table{width:100%;border-collapse:collapse;background:#fff;font-size:13px}
th,td{border:1px solid #e5e7eb;padding:6px 9px;text-align:left;vertical-align:top}
th{background:#f3f4f6}tr:nth-child(even) td{background:#fafbfc}
.num{text-align:right;white-space:nowrap}.cat{color:#6b7280;font-size:12px}
.g{display:inline-block;width:20px;height:20px;line-height:20px;text-align:center;border-radius:5px;font-size:12px;font-weight:700;color:#fff}
.gS{background:#b91c1c}.gA{background:#ea580c}.gB{background:#0284c7}.gC{background:#94a3b8}.gR{background:#16a34a}
.tagS{color:#b91c1c;font-weight:700}.tagA{color:#ea580c;font-weight:700}.tagB{color:#0284c7}.tagC{color:#94a3b8}
.note{background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:12px 16px;color:#92400e;margin:14px 0}
.ok{background:#ecfdf5;border:1px solid #a7f3d0;border-radius:8px;padding:12px 16px;color:#065f46;margin:14px 0}
.scroll{max-height:480px;overflow:auto;border:1px solid #e5e7eb;border-radius:8px}
pre{background:#1f2430;color:#e5e7eb;padding:16px;border-radius:8px;overflow:auto;font-size:13px;line-height:1.6}
.small{font-size:12px;color:#6b7280}
</style></head><body><div class="wrap">
<h1>其余主播分类与得到大脑接入清单</h1>
<div class="sub">生成时间：2026-11-21 ｜ 范围：抖音关注 170 位中除「财经投资 45 位」外的其余 {{N}} 位 ｜ 共 11 个类别</div>
""".replace("{{N}}", str(len(others))))

    h.append('<div class="stats">')
    h.append('<div class="stat"><b>%d</b><span>其余主播</span></div>' % len(others))
    h.append('<div class="stat"><b style="color:#b91c1c">%d</b><span>S 优先关注</span></div>' % cnt["S"])
    h.append('<div class="stat"><b style="color:#ea580c">%d</b><span>A 建议关注</span></div>' % cnt["A"])
    h.append('<div class="stat"><b style="color:#16a34a">%d</b><span>已可直抽</span></div>' % cnt["已可直抽"])
    h.append('<div class="stat"><b style="color:#0284c7">%d</b><span>B 可选</span></div>' % cnt["B"])
    h.append('<div class="stat"><b style="color:#94a3b8">%d</b><span>C 不建议</span></div>' % cnt["C"])
    h.append("</div>")

    h.append("""<div class="note"><b>先读懂「得到大脑」的边界：</b><br>
① 得到聚合的是它平台自己用 AI 生成的<b>知识型结构化摘要</b>，不是原始视频口播——纯娱乐、带货、日常、空号即便关注了，也未必能产出有价值的笔记。<br>
② 这些是抖音博主，得到平台<b>未必全部收录</b>。你按下面清单去得到 App 逐个关注后，告诉我，我用现成脚本去核查哪些真的聚合出了笔记再抽——和上次 12 位的流程一样。<br>
③ 分级依据：知识密度 + 与你第二大脑主线（投资/认知/商业/AI/健康训练）的相关度 + 内容可持续性 + 导流纯度。<b>S/A 值得先加，B 可选，C 建议跳过。</b></div>""")

    # 优先关注清单表
    h.append("<h2>一、优先关注清单（S + A + 已可直抽，共 %d 位）</h2>" %
             (cnt["S"] + cnt["A"] + cnt["已可直抽"]))
    h.append('<table><tr><th>级别</th><th>博主</th><th>类别</th><th class="num">粉丝</th><th>为什么值得加</th></tr>')
    top = [x for x in others if x["grade"] in ("S", "A", "已可直抽")]
    top.sort(key=lambda y: (order[y["grade"]], -int(y["followers"]) if isinstance(y["followers"], int) else 0))
    for x in top:
        gc = {"S": "gS", "A": "gA", "已可直抽": "gR"}[x["grade"]]
        h.append("<tr><td><span class='g %s'>%s</span></td><td>%s</td><td class='cat'>%s</td><td class='num'>%s</td><td class='cat'>%s</td></tr>" %
                 (gc, x["grade"][0], esc(x["nickname"]), esc(x["category"]),
                  wan(x["followers"]), esc(x["reason"])))
    h.append("</table>")

    # 可复制清单
    h.append("<h2>二、可复制的去得到 App 关注名单</h2>")
    h.append('<p class="small">按优先级排列，直接复制去得到 App 逐个搜索关注。关注完回来告诉我，我核查聚合情况再抽。</p>')
    h.append("<pre>")
    lines = []
    for label, gset in [("【S 优先】", ["S"]), ("【A 建议】", ["A"]), ("【B 可选】", ["B"])]:
        names = [x["nickname"] for x in top if x["grade"] in gset] if label != "【B 可选】" else \
                [x["nickname"] for x in others if x["grade"] == "B"]
        lines.append(label + " " + "、".join(names))
    h.append(esc("\n".join(lines)))
    h.append("</pre>")

    # 分类明细
    h.append("<h2>三、按 11 类完整明细（125 位）</h2>")
    cat_order = sorted(bycat, key=lambda c: (
        min(order[x["grade"]] for x in bycat[c]), -len(bycat[c])))
    for cat in cat_order:
        items = bycat[cat]
        c2 = Counter(x["grade"] for x in items)
        h.append("<h3>%s（%d 位：S%d / A%d / B%d / C%d）</h3>" %
                 (esc(cat), len(items), c2["S"], c2["A"], c2["B"], c2["C"]))
        h.append('<div class="scroll"><table><tr><th>级别</th><th>博主</th><th class="num">粉丝</th><th class="num">作品</th><th>子类/理由</th></tr>')
        for x in items:
            g = x["grade"]
            gc = {"S": "gS", "A": "gA", "B": "gB", "C": "gC", "已可直抽": "gR"}.get(g, "gC")
            h.append("<tr><td><span class='g %s'>%s</span></td><td>%s</td><td class='num'>%s</td><td class='num'>%s</td><td class='cat'>%s</td></tr>" %
                     (gc, g[0], esc(x["nickname"]), wan(x["followers"]),
                      esc(x["awemes"]), esc("[%s] %s" % (x.get("sub", ""), x["reason"]))))
        h.append("</table></div>")

    h.append("""<h2>四、下一步</h2><div class="card">
<p>1. 从第二节复制名单，去得到 App 逐个搜索关注（先做 S+A，B 随缘）。</p>
<p>2. 关注完回来说一声，我按上次 12 位的同一套脚本核查聚合情况并抽取入库。</p>
<p>3. C 级 {{NC}} 位（待确认/生活娱乐/家居销售/导流空号）建议跳过，避免稀释知识库质量。</p>
<p class="small">说明：本报告只做公开资料分级，未改动任何账号设置；分级是我的判断，最终以你关注后得到实际聚合出的内容为准。</p>
</div></div></body></html>""")

    h = "\n".join(h).replace("{{NC}}", str(cnt["C"]))
    io.open(OUT, "w", encoding="utf-8").write(h)

    # 纯文本清单
    io.open(TXT, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("HTML:", OUT)
    print("TXT:", TXT)
    print("分级统计:", dict(cnt), "总", len(others))
    print("字符数:", len("\n".join(h)))


if __name__ == "__main__":
    main()
