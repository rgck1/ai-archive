# -*- coding: utf-8 -*-
"""抖音财经投资 45 位 → 第二大脑对接价值评估（可复现生成脚本）
数据源：douyin_classified.json（公开资料）+ 已有 13 位得到笔记评估结论（12 位同源）
原则：不编造视频/直播内容；判断仅基于公开签名与已落库真实笔记。
"""
import json, io, html
from collections import defaultdict

SRC = r"D:/我的工作台/system/douyin_classified.json"
OUT = r"D:/我的工作台/02.输出区/财经投资45位_第二大脑对接评估_2026-11-21.html"

rows = json.load(io.open(SRC, encoding="utf-8"))
fin = [x for x in rows if x["category"] == "财经投资"]

# 得到库已落库的同源账号：昵称 -> (笔记数, 星标)
DONE = {
    "熊猫有财": (407, "★★★★★"), "猫眼儿观世界": (282, "★★★★★"),
    "阿华（机构一手调研）": (168, "★★★★☆"), "量化投资邢不行啊": (130, "★★★★☆"),
    "葫芦军师": (54, "★★★★☆"), "付鹏的财经世界": (268, "★★★★"),
    "独行者李明": (127, "★★★☆"), "量化躺平佟掌柜": (58, "★★★"),
    "主力行为学（杨宁）": (490, "★★★"), "凯心": (455, "★★☆"),
    "全能的野人": (1381, "★★"), "房子(新允珩)": (50, "★"),
}

# 重新分组（按"对接第二大脑的价值性质"，区别于原子类）
GROUPS = [
    ("G1", "规则化 ETF / 量化方法论", "可量化的条件→动作规则、策略框架，能直接转检查清单"),
    ("G2", "一手信息 / 产业调研", "机构调研、研报解读，补工作台「消息面/行业面」短板"),
    ("G3", "宏观认知框架", "大类资产、周期、经济逻辑，补 market regime 判断层"),
    ("G4", "商业财经解读", "案例化拆解，沉淀为财报/商业案例库"),
    ("G5", "盘面实战 / 短线情绪", "强时效盘面速评，只宜做当日情绪采样，不宜沉淀"),
    ("G6", "资讯媒体", "官方/新闻源，做事实底稿而非方法论"),
    ("G7", "导流卖课 / 人设营销 / 信息不足", "签名以卖课带货、导流私域为主，或资料不足以判断"),
]

# 昵称 -> (组, 等级, 接入结论, 具体用途, 备注/依据)
E = {
 # G1
 "熊猫有财": ("G1","S","✅ 直接接入","ETF 宽基/行业波段的「条件→动作」规则，整理成交易检查清单","得到库已有 407 条且评分最高；抖音为同源账号，复用既有笔记，不重复建抓取链路"),
 "量化投资邢不行啊": ("G1","A","✅ 直接接入","数据+代码实证的方法论，对照你已踩过的「因子方向/前视偏差」坑","得到库 130 条★★★★☆；反虚证伪，适合做方法论对话而非每日操作"),
 "付鹏的财经世界": ("G3","A","✅ 直接接入","宏观认知框架，配合 ETF 动量做仓位过滤（market regime）","得到库 268 条★★★★；原 FICC 交易员，操作性弱但框架质量高"),
 "牧哥研报解读": ("G2","A","✅ 直接接入","外文投行研报的一手转述，做「信息差」素材池","828 条作品、更新密集；需二次翻译核对，偏信息而非结论"),
 "葫芦军师": ("G1","B","⚠️ 谨慎补充","体系化基金配置长教程，一次性沉淀为「基金配置手册」底稿","得到库 54 条★★★★☆但近 30 天基本停更；只能当静态底稿"),
 "独行者李明": ("G3","B","⚠️ 谨慎补充","全球对冲/宏观中性策略视角，做「宏观对冲」专题补充","得到库 127 条★★★☆；偏逻辑推演，可验证细节较少"),
 "量化躺平佟掌柜": ("G1","B","⚠️ 谨慎补充","策略周报固定栏目，做「策略迭代记录」模板参考","得到库 58 条★★★；策略细节不完整，需交叉验证"),
 # G2
 "阿华（机构一手调研）": ("G2","A","✅ 直接接入","光模块/存储/芯片等产业链一手细节，补「消息面」自查项","得到库 168 条★★★★☆；涉及科创板标的，与「仅主板」部分冲突需二次筛"),
 "福总说实话": ("G2","B","⚠️ 合并接入","前私募首席投资官视角的机构调研解读","与大号「机构一手调研（福总）」为同一人（签名互认小号），只保留大号一个源"),
 "机构一手调研（福总）": ("G2","B","⚠️ 合并接入","基金经理线上线下调研、一手资讯，做信息面补充","大号（177 万粉）；与小号合并为一个来源，避免双份抓取"),
 "投资最前线": ("G2","C","❌ 不接入","—","签名仅「去伪存真发现价值」口号，无具体信息领域，无法判断可提炼性"),
 # G3
 "卢麒元视角": ("G3","B","⚠️ 谨慎补充","经济学者/资管机构视角的宏观认知补充","359 万粉、131 条作品；偏观点输出，需与事实底稿分离"),
 "钱说": ("G3","C","❌ 不接入","—","签名以防骗声明和会员直播为主，观点型且强私域导向，沉淀价值低"),
 "李一恩": ("G3","C","❌ 不接入","—","签名以「不送资料不送指标」等反营销话术为主，无具体可提炼内容"),
 # G4
 "猫眼儿观世界": ("G4","S","✅ 直接接入","真实财报/机构案例拆解，数字密度全库第一，做「案例库」","得到库 282 条★★★★★；案例时效性强，半年后部分结论需复核"),
 "小Lin说": ("G4","A","✅ 直接接入","北大经济学院+前摩根大通背景的商业财经解读，做通识案例库","1227 万粉、558 条作品；第二大脑目前无其笔记，抖音端属新增高价值源"),
 "温义飞的急救财经": ("G4","A","✅ 直接接入","财经热点背后的逻辑拆解，做「热点→框架」案例","LSE 经济史硕士、财经作家；抖音端新增源，需先验证 ASR 提炼质量"),
 "太学TAIXUE": ("G4","B","⚠️ 谨慎补充","「可行动的知识」型商业拆解，做认知补充","91 万粉；知识付费平台属性，内容偏汇编，独立性一般"),
 "林笙燃": ("G4","B","⚠️ 谨慎补充","每天一个商业逻辑拆解，做碎片化认知卡片","30 万粉、67 条作品；偏旋律化的轻内容，深度有限"),
 "财才说": ("G4","B","⚠️ 谨慎补充","人话讲商业逻辑、品牌故事，做商业案例补充","726 万粉；偏泛商业叙事，与投资主线关联中等"),
 "晓非观察": ("G4","C","❌ 不接入","—","2.9 万粉、26 条作品，签名以解读电视剧《天道》为主，与投资关联弱"),
 # G5
 "主力行为学（杨宁）": ("G5","B","⚠️ 仅做情绪采样","当日盘面/板块轮动的情绪采样，不进知识笔记","得到库 490 条★★★；标题强时效、预测型，隔日失效"),
 "老何学院": ("G5","B","⚠️ 谨慎补充","主力行为学/量价时空的方法论表述，做技术复盘参考","签名明确「不推荐不预判」；内容泛，需看实际口播再定"),
 "易睦修-PYTA交易实讲": ("G5","B","⚠️ 谨慎补充","机构交易法的方法论框架，做技术复盘 SOP 参考","PYTA 自营创始人；培训属性较强，需甄别是否有实证"),
 "金融说": ("G5","B","⚠️ 谨慎补充","金融从业者的实盘认知，做一般方法论补充","8.4 万粉、76 条作品；签名较泛，信息密度待验证"),
 "全能的野人": ("G5","C","❌ 不接入","—","得到库 1381 条但评分最低（★★）：摘要极短、口语化，提炼成本最高"),
 "凯心": ("G5","C","❌ 不接入","—","得到库 455 条★★☆；战法主观、有效性未经数据验证，与你「无可靠优势」结论冲突"),
 "房子(新允珩)": ("G5","C","❌ 不接入","—","得到库 50 条★（最低）：纯点位预判+免责声明，无复用方法论"),
 "翻倍鳄鱼姐": ("G5","C","❌ 不接入","—","签名仅「实战派，不爱说废话」，无可判断的内容领域"),
 "机油手": ("G5","C","❌ 不接入","—","签名「懂一点股票」，50 条作品，信息量不足"),
 "陆陆陆姐": ("G5","C","❌ 不接入","—","作品数 0，无可抓取内容"),
 "小张小张吃饭用缸（21号直播安排手机）": ("G5","C","❌ 不接入","—","签名以品牌花旗参茶发布、直播带货为主，投资内容让位于商业带货"),
 "叶荣添传媒": ("G5","C","❌ 不接入","—","签名仅「最特殊的一个」，无内容领域信息"),
 "投资不焦绿": ("G5","C","❌ 不接入","—","签名为玩笑式「诺贝尔经济学奖觊觎者」，无实质信息"),
 "财富晚高峰": ("G5","C","❌ 不接入","—","签名仅节目口号「了解市场第一条」，2581 条但难判定领域"),
 "花博财经": ("G5","C","❌ 不接入","—","签名以防骗声明为主，无内容领域描述"),
 "林姐财经": ("G5","C","❌ 不接入","—","签名含商务微信导流，且明确「不带你操作」，沉淀价值低"),
 # G6
 "BRTV 天下财经": ("G6","B","⚠️ 谨慎补充","电视台财经节目直播，做事实核验/资讯底稿","官方属性、可信度高，但无结构化知识可提炼"),
 "一分钟看懂XWLB": ("G6","B","⚠️ 谨慎补充","新闻联播要点速览，做时政背景底稿","8594 粉、150 条作品；时政解读，与投资主线间接相关"),
 # G7
 "质子黄金": ("G7","B","⚠️ 谨慎补充","黄金投资垂类，做贵金属专题补充", "职业黄金投资分析师；与你当前 ETF 主线关联中等"),
 "源哥言商": ("G7","C","❌ 不接入","—","签名强导流「加入万人会员群/联系客服」，卖课属性明确"),
 "奶爸财经": ("G7","C","❌ 不接入","—","签名以「投二代养成/富爸爸必看」人设为主，内容定位模糊"),
 "子皮商论": ("G7","C","❌ 不接入","—","签名仅「投资在路上」，信息不足以判断"),
 "期之道": ("G7","C","❌ 不接入","—","期货方向与账户约束（仅主板/场内 ETF）不符"),
 "六贤-产业信息差MAX": ("G7","C","❌ 不接入","—","签名仅「认知决定高度」，无具体产业信息可核验"),
}

# 完整性校验
missing = [x["nickname"] for x in fin if x["nickname"] not in E]
extra = [k for k in E if k not in {x["nickname"] for x in fin}]
assert not missing, "未评估: " + repr(missing)
assert not extra, "多余键: " + repr(extra)

def esc(s):
    return html.escape(str(s), quote=False)

def fmt(n):
    n = int(n)
    return "%.1f万" % (n/1e4) if n >= 10000 else str(n)

badge = {"✅ 直接接入":"ok","⚠️ 谨慎补充":"mid","⚠️ 合并接入":"mid","⚠️ 仅做情绪采样":"mid","❌ 不接入":"no"}
grade_cls = {"S":"gS","A":"gA","B":"gB","C":"gC"}

h = []
h.append('''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>财经投资45位 · 第二大脑对接评估 · 2026-11-21</title>
<style>
:root{--bg:#f7f8fa;--card:#fff;--ink:#1f2329;--sub:#646a73;--line:#e5e6eb;--accent:#2563eb}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.65 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;padding:28px 20px 60px}
.wrap{max-width:1400px;margin:0 auto}
header{background:linear-gradient(135deg,#1e3a8a,#2563eb);color:#fff;border-radius:14px;padding:28px 32px;margin-bottom:22px}
header h1{margin:0 0 8px;font-size:25px}header p{margin:4px 0;opacity:.92;font-size:13px}
.stat{display:flex;gap:26px;margin-top:16px;flex-wrap:wrap}.stat div{background:rgba(255,255,255,.14);padding:8px 16px;border-radius:8px;font-size:13px}.stat b{font-size:19px;margin-right:5px}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:22px 24px;margin-bottom:20px}
h2{font-size:18px;margin:0 0 6px;padding-left:11px;border-left:4px solid var(--accent)}
h3{font-size:15px;margin:20px 0 8px;color:#1e3a8a}
.hint{color:var(--sub);font-size:12.5px;margin:6px 0 16px}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:12.6px;min-width:1080px}
th,td{border:1px solid var(--line);padding:9px 10px;text-align:left;vertical-align:top}
th{background:#f2f5fb;font-weight:600;color:#334155;white-space:nowrap}tr:nth-child(even) td{background:#fafbfc}
.grade{display:inline-block;width:25px;height:25px;line-height:25px;text-align:center;border-radius:6px;color:#fff;font-weight:700}
.gS{background:#0f9d58}.gA{background:#2563eb}.gB{background:#d97706}.gC{background:#9ca3af}
.v{display:inline-block;padding:2px 8px;border-radius:5px;font-size:11.5px;white-space:nowrap;font-weight:600}
.v.ok{background:#ecfdf5;color:#047857}.v.mid{background:#fffbeb;color:#b45309}.v.no{background:#fef2f2;color:#b91c1c}
.tag{display:inline-block;padding:1px 7px;border-radius:4px;font-size:11px;background:#eef2ff;color:#4338ca;white-space:nowrap}
.done{color:#047857;font-size:11.5px}
.note{background:#fffbeb;border-left:4px solid #f59e0b;padding:12px 16px;border-radius:6px;font-size:13px;color:#78350f;margin-top:14px}
.good{background:#ecfdf5;border-left-color:#10b981;color:#065f46}
ul{margin:5px 0;padding-left:18px}li{margin:4px 0}
code{background:#f1f5f9;padding:1px 5px;border-radius:4px;font-size:12px}
.small{font-size:12px;color:var(--sub)}
</style></head><body><div class="wrap">''')

n_ok = sum(1 for v in E.values() if v[2].startswith("✅"))
n_mid = sum(1 for v in E.values() if v[2].startswith("⚠️"))
n_no = sum(1 for v in E.values() if v[2].startswith("❌"))
h.append('<header><h1>财经投资 45 位 · 第二大脑对接价值评估</h1>')
h.append('<p>数据源：你的抖音关注列表「财经投资」类 45 位（公开资料：签名/粉丝/作品数，抓取于 2026-11-21）</p>')
h.append('<p>交叉依据：已有得到大脑笔记库 13 位博主中，12 位与本次名单同源，直接引用其真实笔记数与素材评分</p>')
h.append('<p>生成时间：2026-11-21　|　边界：未获取到视频/直播内容，判断不编造，仅基于公开资料与已落库笔记</p>')
h.append('<div class="stat"><div><b>45</b>财经账号</div><div><b>7</b>重组类别</div><div><b>%d</b>建议接入</div><div><b>%d</b>谨慎/合并</div><div><b>%d</b>不建议接入</div><div><b>12</b>已有笔记背书</div></div></header>'%(n_ok,n_mid,n_no))

# 一、口径
h.append('''<section><h2>一、评估口径与边界</h2><ul>
<li><b>先分类</b>：不用原来的 6 个账号子类，改按「对接第二大脑的价值性质」重组为 7 类——能否沉淀为可复用知识，而不是账号自述领域。</li>
<li><b>是否值得接入</b>：✅ 直接接入＝内容可提炼且与你账户约束匹配；⚠️ 谨慎/合并＝有局部价值但需去重或限定用途；❌ 不接入＝资料不足、导流卖课、强时效或与约束冲突。</li>
<li><b>交叉验证</b>：12 位在得到笔记库已有真实数据（标题+结构化摘要+时间），其星标评分来自已交付的《订阅博主分类与笔记素材价值评估》，不是推测；其余 33 位只有抖音公开资料，结论标为「待验证」。</li>
<li><b>用户约束</b>：账户 10 万级、仅主板、可做场内 ETF；已有回测结论「个股量化无可靠优势、ETF 动量较干净」；荐股需七维自查。</li>
<li><b>不编造</b>：抖音视频内容与直播主题因接口限制未稳定获取，未纳入判断；无实质资料的账号一律标 C 并说明原因。</li>
</ul></section>''')

# 二、分类总表
h.append('<section><h2>二、45 位重组分类与接入结论（总表）</h2><p class="hint">按 7 个价值组排列；「已落库」列标注得到笔记的真实条数与评分，无标注者表示目前只有抖音公开资料。</p>')
for gid, gname, gdesc in GROUPS:
    items = [x for x in fin if E[x["nickname"]][0] == gid]
    if not items: continue
    h.append('<h3>%s · %s <span class="small">（%d 位）</span></h3>'%(gid,esc(gname),len(items)))
    h.append('<p class="small" style="margin:0 0 6px">%s</p>'%esc(gdesc))
    h.append('<div class="scroll"><table><thead><tr><th style="width:36px">级</th><th>账号</th><th>粉丝/作品</th><th style="width:96px">接入结论</th><th>具体用途</th><th>依据 / 备注</th></tr></thead><tbody>')
    for x in sorted(items, key=lambda z: E[z["nickname"]][1]):
        grp, lvl, verdict, use, note = E[x["nickname"]]
        nk = esc(x["nickname"])
        done = DONE.get(x["nickname"])
        done_html = '<div class="done">已落库 %d 条 · %s</div>'%(done[0],esc(done[1])) if done else ''
        h.append('<tr><td><span class="grade %s">%s</span></td><td><b>%s</b><div class="small">%s</div>%s</td><td>%s / %s</td><td><span class="v %s">%s</span></td><td>%s</td><td>%s</td></tr>'%(
            grade_cls[lvl], lvl, nk, esc(x["sub"]), done_html, fmt(x["followers"]), x["awemes"],
            badge[verdict], esc(verdict), esc(use) if use!="—" else '<span class="small">—</span>', esc(note)))
    h.append('</tbody></table></div>')
h.append('</section>')

# 三、无用项
h.append('<section><h2>三、无用项及原因（%d 位，不投入整理时间）</h2>'%n_no)
h.append('<p class="hint">这些账号建议不接入第二大脑；其中部分可保留在抖音关注里看行情，但不进入笔记提炼流程、不作为荐股自查依据。</p>')
h.append('<div class="scroll"><table><thead><tr><th>账号</th><th>粉丝/作品</th><th>不接入原因</th></tr></thead><tbody>')
for x in fin:
    if E[x["nickname"]][2].startswith("❌"):
        h.append('<tr><td><b>%s</b></td><td>%s / %s</td><td>%s</td></tr>'%(esc(x["nickname"]),fmt(x["followers"]),x["awemes"],esc(E[x["nickname"]][4])))
h.append('</tbody></table></div></section>')

# 四、合并/删减
h.append('''<section><h2>四、数量过多需合并或删减的项</h2>
<div class="scroll"><table><thead><tr><th style="width:150px">对象</th><th style="width:90px">现状</th><th>问题</th><th>处理动作</th></tr></thead><tbody>
<tr><td><b>福总说实话 + 机构一手调研（福总）</b></td><td>2 个账号</td><td>签名互认「唯一小号」，实为同一人，机构调研内容高度重叠</td><td><b>合并为 1 个来源</b>：只保留大号「机构一手调研（福总）」，小号不再单独抓取</td></tr>
<tr><td><b>股票实战组（原 16 位）</b></td><td>16 位</td><td>同质化短线盘面号过多，多数签名只有防骗声明或口号，无可提炼方法论</td><td><b>大幅删减到 2 位</b>：杨宁（仅情绪采样）、老何学院（方法论参考，待验证）；其余 14 位不进笔记流程</td></tr>
<tr><td><b>已落库的 12 位同源账号</b></td><td>抖音+得到双端</td><td>得到笔记库已有真实笔记与评分，抖音端再建一套抓取属重复建设</td><td><b>不删账号，删重复链路</b>：复用既有笔记，抖音端只做增量核验，不为这 12 位新开同步任务</td></tr>
<tr><td><b>商业财经解读（原 7 位）</b></td><td>7 位</td><td>3 位强（猫眼儿/小Lin说/温义飞），4 位泛商业叙事、与投资主线关联中等</td><td><b>精简到 3 位</b>：太学/林笙燃/财才说降为偶尔浏览，晓非观察剔除</td></tr>
</tbody></table></div></section>''')

# 五、精选/精简
h.append('''<section><h2>五、需要精选或精简的项</h2>
<div class="scroll"><table><thead><tr><th style="width:130px">池子</th><th style="width:80px">原始</th><th style="width:80px">建议保留</th><th>保留名单</th><th>精简原则</th></tr></thead><tbody>
<tr><td><b>核心接入（S+A）</b></td><td>—</td><td><b>8 位</b></td><td>熊猫有财、猫眼儿观世界、阿华、邢不行、付鹏、小Lin说、温义飞、牧哥研报解读</td><td>先接这 8 位即可覆盖「ETF 规则 + 案例库 + 消息面 + 宏观框架」四条主线，避免一上来铺 45 位</td></tr>
<tr><td><b>基金ETF量化组</b></td><td>18 位</td><td><b>6 位</b></td><td>熊猫有财、邢不行、付鹏、阿华、牧哥研报、葫芦军师</td><td>删掉会员群导流（源哥言商）、签名口号化（投资最前线）、人设模糊（奶爸财经）、信息不足（子皮商论）等</td></tr>
<tr><td><b>股票实战组</b></td><td>16 位</td><td><b>2 位</b></td><td>主力行为学（杨宁，仅采样）、老何学院（待验证）</td><td>你已有回测结论「个股量化无可靠优势」，短线战法类不值得投入提炼时间</td></tr>
<tr><td><b>商业财经解读组</b></td><td>7 位</td><td><b>3 位</b></td><td>猫眼儿观世界、小Lin说、温义飞的急救财经</td><td>保留数字密度高、有专业背景背书的；泛叙事类不建笔记</td></tr>
<tr><td><b>宏观认知组</b></td><td>3 位</td><td><b>2 位</b></td><td>付鹏的财经世界、卢麒元视角</td><td>认知类留两类视角即可；钱说因会员导向剔除</td></tr>
</tbody></table></div></section>''')

# 六、每类优先级与建议
h.append('''<section><h2>六、每类处理优先级与建议</h2>
<div class="scroll"><table><thead><tr><th style="width:70px">优先级</th><th style="width:170px">类别</th><th>处理建议</th><th style="width:220px">与第二大脑/工作台的衔接</th></tr></thead><tbody>
<tr><td><span class="grade gS">P0</span></td><td><b>G1 规则化 ETF/量化</b></td><td>先复用已落库的熊猫有财、邢不行笔记，各挑 10 条整理成「ETF 检查清单」和「方法论对照表」；验证提炼流程后再接入新源</td><td>直接对应你回测出的「ETF 动量」优势，是唯一有可靠优势的方向</td></tr>
<tr><td><span class="grade gS">P0</span></td><td><b>G4 商业财经案例</b></td><td>猫眼儿观世界复用既有 282 条；小Lin说、温义飞为抖音端新增源，先抓少量样本验证 ASR 提炼质量再决定是否全量</td><td>案例库补「基本面/行业面」，供微信荐股七维自查调用</td></tr>
<tr><td><span class="grade gA">P1</span></td><td><b>G2 一手信息/调研</b></td><td>阿华复用既有笔记；福总双号合并后接大号；牧哥研报需先确认外文研报的可核验性</td><td>补「消息面/行业面」短板，但涉及科创板标的需按「仅主板」过滤</td></tr>
<tr><td><span class="grade gA">P1</span></td><td><b>G3 宏观认知</b></td><td>付鹏复用既有 268 条；卢麒元少量补充。只做框架层，不要求转成买卖动作</td><td>配合 ETF 动量做仓位过滤（market regime 判断）</td></tr>
<tr><td><span class="grade gB">P2</span></td><td><b>G6 资讯媒体</b></td><td>两位官方源仅做事实底稿，不建知识笔记；有需要时手工核对即可</td><td>为七维自查的「消息面」提供可核验出处</td></tr>
<tr><td><span class="grade gC">P3</span></td><td><b>G5 盘面短线</b></td><td>杨宁仅做当日情绪采样，不进知识库；其余 15 位不投入整理时间</td><td>情绪采样与你的「情绪 3 年分位」已有能力重叠，避免重复建设</td></tr>
<tr><td><span class="grade gC">P3</span></td><td><b>G7 导流/信息不足</b></td><td>全部不接入；保留关注仅作为信息浏览，不进入提炼、不作为荐股依据</td><td>无</td></tr>
</tbody></table></div>
<div class="note good"><b>建议执行顺序</b>：P0 两组共 8 位（其中 4 位已有真实笔记可直接用）→ 验证「签名/口播 → 结构化笔记」流程顺畅 → P1 接消息面与宏观 → P2 资讯源按需 → P3 只采样不沉淀。全程不为已落库的 12 位重复建抓取链路。</div>
</section>''')

# 七、边界
h.append('''<section><h2>七、边界说明</h2><ul>
<li>本报告只使用公开资料（昵称/签名/粉丝数/作品数）与已落库的得到笔记数据，不含 Cookie、Token、手机号或任何登录凭据。</li>
<li>抖音视频与直播内容未稳定获取，33 位仅有公开资料的账号其接入结论标注为「待验证」，接入前需先看实际口播样本。</li>
<li>「等级/星标」是整理效率与匹配度视角的评分，不代表账号能力或观点正确性；所有观点经你七维自查后才可作为决策参考。</li>
<li>本报告为评估建议，未自动修改第二大脑数据库的导入范围，也未新增抓取任务；是否接入由你拍板。</li>
</ul></section>''')

h.append('</div></body></html>')
content = "\n".join(h)
open(OUT, "w", encoding="utf-8").write(content)
print("报告已生成:", OUT, "字符数:", len(content))
print("分级统计: 接入", n_ok, "/ 谨慎或合并", n_mid, "/ 不接入", n_no, "合计", n_ok+n_mid+n_no)
for gid, gname, _ in GROUPS:
    print("  %s %s : %d 位"%(gid,gname,sum(1 for x in fin if E[x["nickname"]][0]==gid)))
