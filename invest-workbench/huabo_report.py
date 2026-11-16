# -*- coding: utf-8 -*-
"""生成「花臂博士 5 张图」研究报告 HTML（口播溯源 + 量化近似回测）"""
import json, datetime
BASE = r'D:\我的工作台\02.输出区'
d = json.load(open(BASE + r'\huabo_five_shapes_result.json', encoding='utf-8'))
R = d['results']; M = d['meta']; DEF = d['definitions']; GAP = d['g5_vs_g4']

def esc(s): return str(s).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
def pct(x, dig=1): return ('%.'+str(dig)+'f%%') % (x*100) if x is not None else '—'
def bp(x): return ('%+d') % round(x) if x is not None else '—'
def col(x): return '#c0392b' if (x is not None and x > 0) else ('#1e8449' if x is not None else '#8a93a0')

LABEL = {
 'G1_鱼尾顶_回避': '图形一 · 鱼尾顶（回避）',
 'G2a_平台回踩下沿': '图形二a · 高位平台回踩下沿',
 'G2b_平台放量突破': '图形二b · 高位平台放量突破',
 'G3_低位放量拐点': '图形三 · 价值拐点',
 'G4_下跌反弹_不扎实': '图形四 · 下跌反弹（不扎实）',
 'G5_扎实底_V反转': '图形五 · 扎实底（V反转）',
}
QUOTE = {
 'G1_鱼尾顶_回避': '「这就是我们讲的图形一，图形一鱼尾，那这一部分你就可以正常放弃它」「图形一出的是银行红利的顶」「不要接飞刀」',
 'G2a_平台回踩下沿': '「在高位强行横盘……这就是图形二，图形二怎么做？平台战法小一小二」「给你一个平台，比方说十个点十二个点的这种平台，你在这个平台上怎么能低成本地去赌这个突破，把高盈亏比的点在哪里」',
 'G2b_平台放量突破': '「高位强行横盘……这些反手票里边资金都非常扎实」「跟我画的图是不是一模一样的」',
 'G3_低位放量拐点': '「图形三做的是价值，大价值战法现在全是拐点」「回调小三」',
 'G4_下跌反弹_不扎实': '「双双龙头属于图形四，图形四下跌反弹属于底部不扎实的，你还不能把它完全看成底，还需要再次确认」「对应的操作方法就是底部建仓快进快出……不恋战、不贪胜」',
 'G5_扎实底_V反转': '「图形四踩踩踩，踩扎实了走到图形五……很多蓝筹白马的图形」「背靠底边滚动把仓位往上做」「抄底只抄图形五，因为这对于我们来讲是有概率优势的，是有资金共识的」',
}
VID = {
 'G1_鱼尾顶_回避': '7699461634275691830',
 'G2a_平台回踩下沿': '7708707422357032207',
 'G2b_平台放量突破': '7707237226137734434',
 'G3_低位放量拐点': '7704246730937634102',
 'G4_下跌反弹_不扎实': '7708707422357032207',
 'G5_扎实底_V反转': '7703516159081041171',
}

def table_main():
    rows = ''
    for k, v in R.items():
        h = v['main_H']; r = v['H%d' % h]
        if not r: continue
        rows += ('<tr>'
                 f'<td style="text-align:left"><b>{esc(LABEL[k])}</b><br><span class="sub">主持有 H={h} 交易日</span></td>'
                 f'<td>{r["events"]}</td>'
                 f'<td>{pct(r["mean_ret"])}</td>'
                 f'<td>{pct(r["win_rate"])}</td>'
                 f'<td style="color:{col(r["edge_bp"])};font-weight:700">{bp(r["edge_bp"])}</td>'
                 f'<td class="sub">{bp(r["ci95_bp"][0])} ~ {bp(r["ci95_bp"][1])}</td>'
                 f'<td style="color:{col(r["is"]["edge_bp"])}">{bp(r["is"]["edge_bp"])}</td>'
                 f'<td style="color:{col(r["oos"]["edge_bp"])}">{bp(r["oos"]["edge_bp"])}</td>'
                 f'<td style="color:{col(r["edge_after_20bp"])}">{bp(r["edge_after_20bp"])}</td>'
                 f'<td style="color:{col(r["edge_after_50bp"])}">{bp(r["edge_after_50bp"])}</td>'
                 '</tr>')
    return ('<table><tr><th style="text-align:left">图形</th><th>事件数</th><th>平均收益</th><th>胜率</th>'
            '<th>edge vs 随机</th><th>95%CI</th><th>样本内</th><th>样本外</th><th>扣20bp</th><th>扣50bp</th></tr>'
            + rows + '</table>')

def bars_edge():
    items = []
    for k, v in R.items():
        h = v['main_H']; r = v['H%d' % h]
        if r: items.append((k, r['edge_bp'], r['oos']['edge_bp']))
    row = 32
    W, H, L, Rp = 680, len(items)*row+62, 172, 82
    pw = W-L-Rp; zero = L+pw/2
    mx = max(max(abs(a or 0), abs(b or 0)) for _, a, b in items) * 1.18 or 1
    s = [f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:680px">',
         f'<line x1="{zero}" y1="14" x2="{zero}" y2="{H-38}" stroke="#c9d0d8" stroke-dasharray="3 3"/>']
    for i, (k, allv, oosv) in enumerate(items):
        y = 20+i*row
        s.append(f'<text x="{L-8}" y="{y+13}" font-size="11" fill="#333" text-anchor="end">{esc(LABEL[k].split(" · ")[0]+" · "+LABEL[k].split(" · ")[1][:10])}</text>')
        for j, (val, ht, alpha) in enumerate([(allv, 7, '1'), (oosv, 18, '.55')]):
            if val is None: continue
            w = abs(val)/mx*(pw/2)
            x = zero if val > 0 else zero-w
            s.append(f'<rect x="{x:.1f}" y="{y+ht}" width="{w:.1f}" height="9" rx="2" fill="{col(val)}" opacity="{alpha}"/>')
            tx = zero+w+4 if val > 0 else zero-w-4
            s.append(f'<text x="{tx:.1f}" y="{y+ht+9}" font-size="10" fill="{col(val)}" text-anchor="{"start" if val>0 else "end"}">{bp(val)}</text>')
    s.append(f'<rect x="{L}" y="{H-31}" width="11" height="9" rx="2" fill="#7b8794"/><text x="{L+16}" y="{H-23}" font-size="10" fill="#6b7480">全期</text>')
    s.append(f'<rect x="{L+58}" y="{H-31}" width="11" height="9" rx="2" fill="#7b8794" opacity=".55"/><text x="{L+74}" y="{H-23}" font-size="10" fill="#6b7480">样本外</text>')
    s.append(f'<text x="{L+130}" y="{H-23}" font-size="10" fill="#8a93a0">相对同期全市场随机30只的 edge（bp），红正绿负</text></svg>')
    return ''.join(s)

def heat_year():
    years = sorted({int(y) for v in R.values() for r in (v['H20'], v['H60']) if r for y in r['by_year_edge_bp']})
    head = '<tr><th style="text-align:left">图形</th>' + ''.join(f'<th>{y}</th>' for y in years) + '</tr>'
    rows = ''
    for k, v in R.items():
        h = v['main_H']; r = v['H%d' % h]
        if not r: continue
        cells = ''
        for y in years:
            val = r['by_year_edge_bp'].get(str(y))
            if val is None: cells += '<td>—</td>'; continue
            bg = (f'rgba(192,57,43,{min(abs(val)/4500,.82):.2f})' if val > 0
                  else f'rgba(30,132,73,{min(abs(val)/4500,.82):.2f})')
            cells += f'<td style="background:{bg};color:{"#7b1c14" if val>0 else "#125e35"}">{bp(val)}</td>'
        rows += f'<tr><td style="text-align:left">{esc(LABEL[k].split(" · ")[0])}</td>{cells}</tr>'
    return f'<table class="heat">{head}{rows}</table>'

def defs_table():
    rows = ''
    for k in DEF:
        rows += (f'<tr><td style="text-align:left"><b>{esc(LABEL[k])}</b><br><span class="sub">'
                 f'<a href="https://www.douyin.com/video/{VID[k]}" target="_blank">口播视频 {VID[k]}</a></span></td>'
                 f'<td style="text-align:left" class="quote">{esc(QUOTE[k])}</td>'
                 f'<td style="text-align:left" class="sub">{esc(DEF[k])}</td></tr>')
    return ('<table><tr><th style="text-align:left">图形</th><th style="text-align:left">口播原话</th>'
            '<th style="text-align:left">量化近似定义</th></tr>' + rows + '</table>')

def gap_text():
    out = []
    for h in ('20', '60'):
        g = GAP['H' + h]
        out.append(f'<li><b>H={h}</b>：图形五减图形四的配对 edge 差 <span style="color:{col(g["gap_bp"])};font-weight:700">{bp(g["gap_bp"])} bp</span>'
                   f'（95%CI {bp(g["ci95_bp"][0])} ~ {bp(g["ci95_bp"][1])}，配对日 {g["n_days"]}，图形五胜出天数占比 {pct(g["win_rate"],0)}）。'
                   f'分年：' + '、'.join(f'{y} {bp(v)}' for y, v in g['by_year'].items()) + '。</li>')
    return '<ul>' + ''.join(out) + '</ul>'

positive = [k for k, v in R.items() if (v['H%d' % v['main_H']] or {}).get('edge_bp', 0) > 0]
positive_oos = [k for k, v in R.items() if ((v['H%d' % v['main_H']] or {}).get('oos') or {}).get('edge_bp', 0) > 0]

HTML = f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>花臂博士「5 张图」到底是什么 · 溯源与回测 · 2026-11-16</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f4f6f9;color:#222b38;font-family:-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;line-height:1.68}}
.wrap{{max-width:1080px;margin:0 auto;padding:28px 22px 70px}}
.hero{{background:linear-gradient(135deg,#17263b,#2b4468);color:#fff;border-radius:14px;padding:30px 34px;box-shadow:0 8px 24px rgba(23,38,59,.18)}}
.hero h1{{margin:0 0 8px;font-size:25px;letter-spacing:.4px}}.hero .meta{{font-size:12.5px;opacity:.85}}
.hero .tag{{display:inline-block;background:rgba(255,255,255,.14);border-radius:20px;padding:3px 12px;font-size:11.5px;margin:10px 6px 0 0}}
.card{{background:#fff;border-radius:12px;padding:22px 26px;margin:18px 0;box-shadow:0 2px 10px rgba(20,40,70,.06)}}
.card h2{{font-size:18px;margin:0 0 6px;color:#1b2a41;border-left:4px solid #c0392b;padding-left:11px}}
.card h3{{font-size:14px;margin:20px 0 8px;color:#2c3e50}}
.lead{{font-size:13.5px;color:#596273;margin:6px 0 14px}}
table{{border-collapse:collapse;width:100%;font-size:12px;margin:10px 0}}
th,td{{border-bottom:1px solid #e8ecf1;padding:8px 7px;text-align:center;vertical-align:top}}
th{{background:#f0f3f7;color:#3a4658;font-weight:600;font-size:11.5px}}
tr:hover td{{background:#fafbfd}}.sub{{color:#8a93a0;font-size:10.5px}}
.quote{{font-size:11.5px;color:#45505f;line-height:1.55}}
table.heat td{{font-size:10.5px;padding:6px 4px}}table.heat th{{font-size:10.5px}}
.warn{{background:#fff7e8;border-left:4px solid #d98922;padding:12px 16px;border-radius:6px;font-size:12.5px;color:#6b4b1b;margin:14px 0}}
.ok{{background:#f0f8f3;border-left:4px solid #1e8449;padding:12px 16px;border-radius:6px;font-size:13px;color:#1e5a37;margin:14px 0}}
.bad{{background:#fdf1f0;border-left:4px solid #c0392b;padding:12px 16px;border-radius:6px;font-size:13px;color:#7b2c22;margin:14px 0}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0}}
.kpi{{background:#f7f9fc;border:1px solid #e8edf3;border-radius:9px;padding:13px 15px}}
.kpi .n{{font-size:21px;font-weight:700;color:#1b2a41}}.kpi .t{{font-size:11px;color:#8a93a0;margin-top:3px}}
ul{{font-size:13px;padding-left:20px}}li{{margin:6px 0}}
code{{background:#f0f3f7;padding:1px 5px;border-radius:4px;font-size:11.5px}}
.foot{{font-size:11px;color:#9aa3b0;text-align:center;margin-top:26px}}
</style></head><body><div class="wrap">
<div class="hero"><h1>花臂博士「5 张图」到底是什么，能不能用来炒股？</h1>
<div class="meta">口播溯源 · 形态量化近似回测 · 生成 {M['generated']} · 数据 {M['start']} ~ {M['end']}</div>
<div class="tag">来源：投资工作台「博主情报」· 花博（花臂博士）</div>
<div class="tag">全A 5812 只 · 后复权 · 含退市</div>
<div class="tag">随机安慰剂 / 样本外 / 成本敏感性</div></div>

<div class="card"><h2>一、先说清「5 张图」是怎么回事</h2>
<p class="lead">我在工作台「博主情报」里找到的是你关注的博主 <b>花博</b>（抖音名「花臂博士爆打财经」）。他 8 月～11 月的多条视频里反复讲一套「图形一～图形五」的 K 线模板：把股票按走势归入 5 类形态，每类配一种战法——这不是 5 张技术指标图，而是 <b>5 种形态阶段 + 对应操作</b>。核心主张是「不预测、只跟随」「抄底只抄图形五」「图形一出的是顶，别接飞刀」。</p>
<div class="warn"><b>边界说明：</b>五张示意图只出现在视频画面里，工作台保存的是 ASR 口播文字；视频直链已过可取窗口。下表定义是<b>按口播里能明确识别的文字特征做的量化近似</b>，不是课程原图的逐像素复刻。因此本回测回答的是「这些文字特征有没有统计优势」，不是「原图 100% 有效/无效」。</div>
{defs_table()}
</div>

<div class="card"><h2>二、怎么测的</h2>
<p class="lead">后复权价；t 日收盘满足形态条件 → t+1 收盘买入 → 持有 20 / 60 个交易日（对应 1 个月 / 1 个季度）；含退市股；可交易过滤为成交额 20 日均≥5000 万、上市≥120 日；同一只股票同一形态 60 日只记一次，避免事件重叠虚增。<b>edge</b> = 形态股随机 30 只的收益 − 同期全市场随机 30 只的收益（正=形态选股优于随机）；样本内 2018–2021、样本外 2022–2026；成本按双边 20bp / 50bp 扣除。</p>
</div>

<div class="card"><h2>三、结果</h2>
<div class="kpis">
<div class="kpi"><div class="n">{len(R)}</div><div class="t">测试形态数</div></div>
<div class="kpi"><div class="n" style="color:{col(1 if positive else -1)}">{len(positive)}/{len(R)}</div><div class="t">全期 edge 为正</div></div>
<div class="kpi"><div class="n" style="color:{col(1 if positive_oos else -1)}">{len(positive_oos)}/{len(R)}</div><div class="t">样本外 edge 为正</div></div>
<div class="kpi"><div class="n">{bp(max((v['H%d'%v['main_H']]['edge_bp'] or -99999) for v in R.values()))}</div><div class="t">最佳形态全期 edge</div></div>
</div>
{table_main()}
<h3>全期 vs 样本外 edge 对比</h3>
{bars_edge()}
<h3>逐年 edge（bp，红正绿负）</h3>
{heat_year()}
</div>

<div class="card"><h2>四、核心主张专项检验</h2>
<h3>「抄底只抄图形五」：图形五 vs 图形四</h3>
<p class="lead">博主反复强调图形四只是下跌反弹、底部不扎实，要快进快出；图形五踩实了才能主仓抄底。用配对日差分检验（同一天两者的 edge 相减）：</p>
{gap_text()}
<h3>图形一「鱼尾顶」回避是否有效</h3>
<p class="lead">图形一的实操含义是卖出/回避，因此看的是它出现后收益<b>是否显著低于随机</b>：H=20 edge <b style="color:{col((R['G1_鱼尾顶_回避']['H20'] or {}).get('edge_bp'))}">{bp((R['G1_鱼尾顶_回避']['H20'] or {}).get('edge_bp'))}</b> bp，H=60 edge <b style="color:{col((R['G1_鱼尾顶_回避']['H60'] or {}).get('edge_bp'))}">{bp((R['G1_鱼尾顶_回避']['H60'] or {}).get('edge_bp'))}</b> bp；样本外 H=20 <b style="color:{col((R['G1_鱼尾顶_回避']['H20'] or {}).get('oos',{}).get('edge_bp'))}">{bp((R['G1_鱼尾顶_回避']['H20'] or {}).get('oos',{}).get('edge_bp'))}</b> bp。负值=回避规则有统计依据。</p>
</div>

<div class="card"><h2>五、结论与局限</h2>
<p class="lead">
<b>结论：这 5 张图可以理解成一套「形态阶段分类语言」，但不能当成靠它就能炒股的盈利系统。</b>
按口播文字还原的 6 个形态里，只有「图形二 · 高位平台回踩下沿」在全期和样本外都给出正 edge（H60 +134bp / +100bp，H20 +240bp / +250bp），但它的 95% 置信区间跨 0、有效样本日只有 35 天，扣 20bp 成本后 +94bp、扣 50bp 后只剩 +34bp——是线索，不是可靠策略。
</p>
<div class="bad"><b>核心主张「抄底只抄图形五」在本口径下不成立。</b>图形五 H60 edge <b>−189bp</b>（95%CI −329 ~ −39，显著为负），样本外 −231bp；与图形四的配对差 H60 <b>−84bp</b>、H20 仅 +92bp 且两个置信区间都跨 0、分年剧烈摆动（2025 年 −1016bp）。「踩实了再抄」这个直觉没有被数据兑现。</div>
<div class="ok"><b>部分风险判断有方向性依据：</b>「图形四 · 下跌反弹不扎实」H20 edge −247bp（CI −504 ~ −38）、H60 −555bp；「图形三 · 低位放量拐点」H60 −290bp（CI −512 ~ −55）。也就是说这些形态出现后，随机选股确实更容易跑输——但这是「避开」的价值，不是「买入」的价值；且图形四的负 edge 在样本外衰减到 −94bp。</div>
<p class="lead">
「图形一 · 鱼尾顶」证据不足：仅 219 个事件，H20 edge +139bp 但 CI −380 ~ +730、样本外转为 −103bp，无法据此确认顶部回避规则；「图形二 · 放量突破」H60 −484bp（仅 6 个样本外日、CI 跨 0）反而提示追突破不划算，与博主强调的「低成本赌突破」并不一致。
</p>
<ul>
<li>本回测只覆盖价格/成交量层面可识别的特征；口播里「资金共识」「大资金建仓」「情绪出一层层」等判断需要 Level-2 资金流或席位数据，面板里没有，无法验证。</li>
<li>图形三提到「价值」，但原视频的估值口径未给出；这里只用「低位放量站上 MA20」作近似，不等于低 PE/PB 价值策略。</li>
<li>事件研究的是<b>等权随机抽样</b>形态股，不含个人盘中的买点选择、止损执行与仓位管理；真实课程战法（小一小二、背靠底边滚动）的择时收益没有被完整检验。</li>
<li>样本区间 2018–2026，A 股制度与风格变化大；单一窗口的结论不可外推为长期规律。</li>
</ul>
</div>
<div class="foot">数据源：投资工作台博主情报 ASR 口播稿 · panel_v3.pkl 全A后复权面板 · 本页由 huabo_report.py 生成</div>
</div></body></html>'''

out = BASE + r'\花臂博士5张图_溯源与回测_2026-11-16.html'
open(out, 'w', encoding='utf-8').write(HTML)
print('SAVED', out, 'chars', len(HTML))
