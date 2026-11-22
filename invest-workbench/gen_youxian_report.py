# -*- coding: utf-8 -*-
"""生成「优先」库 7 位博主接入结果报告。"""
import json, io, time, sys
sys.stdout.reconfigure(encoding="utf-8")

OUT = "D:/我的工作台/02.输出区/优先库7位博主接入结果_2026-11-21.html"
STAT = "D:/Software/second-brain-tools/_debug_archive/youxian_notes_stat.json"

rows = json.load(io.open(STAT, encoding="utf-8"))
rows.sort(key=lambda x: -x["total"])
total = sum(x["total"] for x in rows)
gen = time.strftime("%Y-%m-%d %H:%M")

trs = "\n".join(
    "<tr><td>%s</td><td class=\"c\">%d</td><td>%s</td></tr>" %
    (r["name"], r["total"], "✅ 已抽取入库" if r["total"] > 0 else "待聚合")
    for r in rows
)

html = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>优先库7位博主接入结果</title>
<style>
:root{--ink:#1f2733;--sub:#5b6675;--line:#e3e8ef;--bg:#f6f8fb;--card:#fff;--accent:#2f6df6;--ok:#0a8f5b;--chip:#eef3fc}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:28px 20px 60px}h1{font-size:26px;margin:0 0 4px}
.sub{color:var(--sub);font-size:13px;margin-bottom:22px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px 22px;margin:16px 0}
h2{font-size:19px;margin:0 0 12px;padding-left:10px;border-left:4px solid var(--accent)}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.stat{background:var(--chip);border-radius:10px;padding:14px;text-align:center}.stat b{display:block;font-size:24px;color:var(--accent)}.stat span{font-size:12px;color:var(--sub)}
table{border-collapse:collapse;width:100%;font-size:13px;margin-top:10px}th,td{border:1px solid var(--line);padding:8px 10px;text-align:left}th{background:var(--chip)}td.c{text-align:center}
.box{background:#eef9f2;border:1px solid #b8e6cf;border-radius:10px;padding:14px 18px;margin:12px 0}
ul{padding-left:22px}li{margin:6px 0}.foot{color:var(--sub);font-size:12px;margin-top:24px;text-align:center}
</style></head><body><div class="wrap">
<h1>「优先」库 7 位博主接入结果</h1>
<div class="sub">生成时间：{{GEN}} ｜ 数据源：得到大脑新建「优先」库（topic=5029201）｜ 7 位 S 级优先博主</div>
<div class="card">
<h2>一、结果总览</h2>
<div class="stats">
<div class="stat"><b>7</b><span>优先博主全部接入</span></div>
<div class="stat"><b>{{TOTAL}}</b><span>笔记抽取条数</span></div>
<div class="stat"><b>13565</b><span>第二大脑笔记总数</span></div>
</div>
<div class="box"><b>本次解决了上次的关键错位</b>：你新建「优先」库时，把 7 位 S 级博主做了"关注 + 加入知识库"两步，平台已聚合出笔记，我全部抽取入库。上次的"只关注未连库"问题彻底绕过。</div>
</div>
<div class="card">
<h2>二、7 位博主明细</h2>
<table><thead><tr><th>博主</th><th class="c">聚合笔记数</th><th>状态</th></tr></thead><tbody>
{{ROWS}}
</tbody></table>
<p class="sub">导入前后：11162 → 13565（+{{TOTAL}}，与抽取数一致）；各 source 分布与搜索抽查（第一性原理/罗翔/减脂/无穷小亮）均正常。</p>
</div>
<div class="card">
<h2>三、这批内容的用途（对接你的主线）</h2>
<ul>
<li><b>健康训练线</b>：粗人（力量矩阵营养学）507 条、陈石（循证运动营养）312 条 —— 正好契合你"减脂保肌 + 护膝护腰"的训练主线，可作训练营养参考。</li>
<li><b>认知/商业线</b>：李善友（第一性原理）361 条、黄执中（表达）675 条、赵玉平（国学+管理）440 条 —— 沉淀方法论与表达框架。</li>
<li><b>专业科普线</b>：无穷小亮（自然科普）99 条、罗翔（刑法）9 条 —— 罗翔这批只有 9 条（该库聚合较少），质量高但样本小。</li>
</ul>
</div>
<div class="card">
<h2>四、说明与边界</h2>
<ul>
<li>本轮只做"抽取 + 入库"，没有改你的任何得到关注/知识库设置。</li>
<li>得到的笔记是平台 AI 生成的二手摘要（非原始视频口播），观点仍需经你既有的七维自查后再参考。</li>
<li>剩余 A 级 17 位（混知、冯唐、金枪大叔等）若已加进某个库，告诉我库名即可用同一套脚本抽；若只是关注未连库，需先在 App 里"加入知识库"。</li>
<li>下次接续：运行 <code>python resume_intake.py --stat</code> 会自动核查库 following、比对已入库、列出可抽取的新博主。</li>
</ul>
</div>
<div class="foot">归档：ai-archive/invest-workbench/ ｜ 生成脚本 batch_extract_youxian.py + import_youxian.py + gen_youxian_report.py</div>
</div></body></html>"""

html = html.replace("{{GEN}}", gen).replace("{{TOTAL}}", str(total)).replace("{{ROWS}}", trs)
io.open(OUT, "w", encoding="utf-8").write(html)
print("报告已生成:", OUT, "| 字符数", len(html))
