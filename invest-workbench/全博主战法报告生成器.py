# -*- coding: utf-8 -*-
"""生成《全博主战法大摸底与回测》HTML 报告"""
import json, datetime
BASE=r'D:\我的工作台\02.输出区'
RES=json.load(open(BASE+r'\全博主战法_统一回测结果.json',encoding='utf-8'))
LST=json.load(open(BASE+r'\全博主战法_清单与定义.json',encoding='utf-8'))
R=RES['results']; M=RES['meta']
DEF={x['key']:x for x in LST['tactics']}

def bp(x): return ('%+d')%round(x) if x is not None else '—'
def col(x): return '#c0392b' if (x is not None and x>0) else ('#1e8449' if x is not None else '#8a93a0')
def esc(s): return str(s).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')

def main_table():
    rows=''
    for k,v in R.items():
        a=v['no_pre']['H10']['recent']; b=v['with_pre']['H10']['recent']
        if not a or not b: continue
        d=DEF[k]
        ci=lambda r: (f"{bp(r['ci95_bp'][0])}~{bp(r['ci95_bp'][1])}" if r['ci95_bp'][0] is not None else '—')
        improved = b['edge_bp']>a['edge_bp']
        rows+=(f'<tr><td style="text-align:left"><b>{esc(d["blogger"])}</b><br><span class="sub">{esc(d["name"])}</span></td>'
               f'<td style="color:{col(a["edge_bp"])}">{bp(a["edge_bp"])}<br><span class="sub">{ci(a)}</span></td>'
               f'<td style="color:{col(b["edge_bp"])};font-weight:700">{bp(b["edge_bp"])}<br><span class="sub">{ci(b)}</span></td>'
               f'<td>{"↑" if improved else "↓"} {bp(b["edge_bp"]-a["edge_bp"])}</td>'
               f'<td class="sub">{b["n_days"]}</td>'
               f'<td style="color:{col(b["edge_50bp"])}">{bp(b["edge_50bp"])}</td></tr>')
    return ('<table><tr><th style="text-align:left">博主·战法</th><th>无前提 edge<br><span class="sub">近三年 H10</span></th>'
            '<th>带前提 edge<br><span class="sub">近三年 H10</span></th><th>前提增益</th><th>有效日</th><th>扣50bp</th></tr>'+rows+'</table>')

def full_vs_recent():
    rows=''
    for k,v in R.items():
        f=v['no_pre']['H10']['full']; r=v['no_pre']['H10']['recent']
        if not f or not r: continue
        d=DEF[k]
        rows+=(f'<tr><td style="text-align:left"><b>{esc(d["blogger"])}</b>·{esc(d["name"])}</td>'
               f'<td style="color:{col(f["edge_bp"])}">{bp(f["edge_bp"])}</td>'
               f'<td style="color:{col(r["edge_bp"])}">{bp(r["edge_bp"])}</td>'
               f'<td style="color:{col(r["edge_bp"]-f["edge_bp"])}">{bp(r["edge_bp"]-f["edge_bp"])}</td></tr>')
    return '<table><tr><th style="text-align:left">战法</th><th>全窗口 2018-26</th><th>近三年 2022-26</th><th>衰减</th></tr>'+rows+'</table>'

def pre_table():
    rows=''
    for k,desc in RES['pre_defs'].items():
        rows+=f'<tr><td style="text-align:left"><code>{esc(k)}</code></td><td style="text-align:left">{esc(desc)}</td></tr>'
    return '<table><tr><th style="text-align:left">前提代号</th><th style="text-align:left">定义（日频可观测近似）</th></tr>'+rows+'</table>'

def tactics_cards():
    out=[]
    for blog in ['邢不行','凯心','人性论','房子','野人']:
        ts=[x for x in LST['tactics'] if x['blogger']==blog]
        if not ts: continue
        items=''
        for t in ts:
            items+=(f'<tr><td style="text-align:left"><b>{esc(t["name"])}</b></td>'
                    f'<td style="text-align:left" class="quote">{esc(t["quote"])}</td>'
                    f'<td style="text-align:left" class="sub">{esc(t["definition"])}</td>'
                    f'<td style="text-align:left" class="sub">{esc(t["precondition"])}</td></tr>')
        out.append(f'<h3>{esc(blog)}（{len(ts)} 个可量化战法）</h3>'
                   '<table><tr><th style="text-align:left">战法</th><th style="text-align:left">口播核心</th>'
                   '<th style="text-align:left">日频量化定义</th><th style="text-align:left">博主强调的前提</th></tr>'
                   +items+'</table>')
    return ''.join(out)

# 统计：带前提改善数、正edge数
n_improve=sum(1 for v in R.values() if v['with_pre']['H10']['recent']['edge_bp']>v['no_pre']['H10']['recent']['edge_bp'])
n_pos_nopre=sum(1 for v in R.values() if v['no_pre']['H10']['recent']['edge_bp']>0)
n_pos_pre=sum(1 for v in R.values() if v['with_pre']['H10']['recent']['edge_bp']>0)
n_strict=sum(1 for v in R.values() if (v['with_pre']['H10']['recent']['ci95_bp'][0] or -1)>0)

HTML=f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>全博主战法大摸底与回测 · 2026-11-16</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f4f6f9;color:#222b38;font-family:-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;line-height:1.66}}
.wrap{{max-width:1180px;margin:0 auto;padding:28px 22px 70px}}
.hero{{background:linear-gradient(135deg,#17263b,#2b4468);color:#fff;border-radius:14px;padding:30px 34px;box-shadow:0 8px 24px rgba(23,38,59,.18)}}
.hero h1{{margin:0 0 8px;font-size:25px}}.hero .meta{{font-size:12.5px;opacity:.85}}
.hero .tag{{display:inline-block;background:rgba(255,255,255,.14);border-radius:20px;padding:3px 12px;font-size:11.5px;margin:10px 6px 0 0}}
.card{{background:#fff;border-radius:12px;padding:22px 26px;margin:18px 0;box-shadow:0 2px 10px rgba(20,40,70,.06)}}
.card h2{{font-size:18px;margin:0 0 6px;color:#1b2a41;border-left:4px solid #c0392b;padding-left:11px}}
.card h3{{font-size:14px;margin:18px 0 8px;color:#2c3e50}}
.lead{{font-size:13px;color:#596273;margin:6px 0 12px}}
table{{border-collapse:collapse;width:100%;font-size:11.5px;margin:10px 0}}
th,td{{border-bottom:1px solid #e8ecf1;padding:7px 6px;text-align:center;vertical-align:top}}
th{{background:#f0f3f7;color:#3a4658;font-weight:600;font-size:11px}}
tr:hover td{{background:#fafbfd}}.sub{{color:#8a93a0;font-size:10px}}
.quote{{font-size:11px;color:#45505f;line-height:1.5}}
.warn{{background:#fff7e8;border-left:4px solid #d98922;padding:12px 16px;border-radius:6px;font-size:12.5px;color:#6b4b1b;margin:14px 0}}
.ok{{background:#f0f8f3;border-left:4px solid #1e8449;padding:12px 16px;border-radius:6px;font-size:13px;color:#1e5a37;margin:14px 0}}
.bad{{background:#fdf1f0;border-left:4px solid #c0392b;padding:12px 16px;border-radius:6px;font-size:13px;color:#7b2c22;margin:14px 0}}
.kpis{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin:16px 0}}
.kpi{{background:#f7f9fc;border:1px solid #e8edf3;border-radius:9px;padding:12px 13px}}
.kpi .n{{font-size:20px;font-weight:700;color:#1b2a41}}.kpi .t{{font-size:10.5px;color:#8a93a0;margin-top:3px}}
ul{{font-size:13px;padding-left:20px}}li{{margin:6px 0}}
code{{background:#f0f3f7;padding:1px 5px;border-radius:4px;font-size:11px}}
.foot{{font-size:11px;color:#9aa3b0;text-align:center;margin-top:26px}}
</style></head><body><div class="wrap">
<div class="hero"><h1>全博主战法大摸底与回测：他们讲的战法，加上前提能不能用？</h1>
<div class="meta">生成 {M['generated']} · 面板 {M['start']} ~ {M['end']} · 主窗口 {M['recent_start']} 起（最近几年）</div>
<div class="tag">来源：投资工作台「博主情报」全量导出 382 条 / 7 位博主 / 266 条 ASR 口播</div>
<div class="tag">23 个可量化战法</div>
<div class="tag">前提过滤对比 / 随机安慰剂 / 成本敏感性</div>
<div class="tag">红=正 edge，绿=负 edge</div></div>

<div class="card"><h2>〇、这次做了什么</h2>
<p class="lead">把工作台里 <b>7 位博主、382 条视频、266 条 ASR 口播稿</b> 全量导出，逐一读完，提炼出 <b>23 个能用日 K 量化复现的战法</b>。按你的要求做了两件事：①每个战法都先还原博主自己强调的<b>适用前提</b>（大盘环境、情绪周期、个股位置、趋势、量能等），回测时对比"无条件用"和"带前提用"；②主窗口放在 <b>2022 年起的最近几年</b>，另留 2018 年起全窗口做对照看衰减。</p>
<div class="warn"><b>边界先说清：</b>口播里的分时刻画（黄线承接、盘口、资金意图、龙头梯队）日 K 无法观测；这里测的是"能用日 K 明确识别的规则 + 前提"的量化近似。edge = 信号股随机 30 只的收益 − 同期全市场随机 30 只的收益。战法按 t 日收盘出信号、t+1 买入、持有 10 个交易日为主口径（另测 5/20 日）。</div>
</div>

<div class="card"><h2>一、结果速览（近三年 2022–2026，持有 10 日）</h2>
<div class="kpis">
<div class="kpi"><div class="n">{len(R)}</div><div class="t">回测战法数</div></div>
<div class="kpi"><div class="n" style="color:#c0392b">{n_improve}/{len(R)}</div><div class="t">加前提后 edge 改善</div></div>
<div class="kpi"><div class="n">{n_pos_nopre} → {n_pos_pre}</div><div class="t">正 edge 战法数<br>无前提 → 带前提</div></div>
<div class="kpi"><div class="n" style="color:#1e8449">{n_strict}</div><div class="t">置信区间下限<br>仍 &gt; 0 的战法</div></div>
<div class="kpi"><div class="n">{bp(max(v['with_pre']['H10']['recent']['edge_bp'] for v in R.values()))}</div><div class="t">带前提最佳 edge</div></div>
</div>
{main_table()}
<div class="ok"><b>前提是有价值的，但不足以造出稳定策略。</b>{n_improve}/{len(R)} 个战法加上博主强调的前提后 edge 改善，正 edge 战法从 {n_pos_nopre} 个增加到 {n_pos_pre} 个——方向印证了"这些战法确实有适用环境"。但<b>没有一条战法的 95% 置信区间下限大于 0</b>，扣 50bp 成本后更是全线转负。也就是说：前提能帮你少踩坑，仍不能保证稳定盈利。</div>
</div>

<div class="card"><h2>二、哪些前提最管用</h2>
<p class="lead">前提维度（日频可观测近似）：</p>
{pre_table()}
<p class="lead">改善最明显的几例（H10 近三年）：<b>五一三战法</b> 从 −83bp → <b>+28bp</b>（加大盘向上+低位）、<b>凯心假破位收回</b> 从 −28bp → <b>+60bp</b>（加低位）、<b>倒锤子长下影</b> 从 −26bp → <b>+17bp</b>（加低位）、<b>人·反扑日</b> 从 −82bp → −40bp（加低位）。共同点是<b>"低位"这个前提最有效</b>——同一个信号在高位追和大底部买，结果差别很大，这与 7 位博主反复强调"位置决定一切"一致。</p>
</div>

<div class="card"><h2>三、全窗口 vs 最近三年：多数战法在衰减</h2>
{full_vs_recent()}
<p class="lead">值得注意：<b>跌停板战法</b>全窗口 +90bp、近三年 −184bp（衰减 274bp），<b>大跌次日反抽</b>、<b>野人冰点涨停</b>、<b>人性论反扑日</b>也明显转差——短线博弈类策略在近年被套利得越来越干净。相对稳住的是<b>小市值+低价</b>（全窗口 +72 → 近三年 +140bp），但它的逐年波动极大（2023 +409bp、2022 −135bp），且我的事件研究口径无法复现邢不行本人按月调仓跑出的年化 55%，两者不可直接比较。</p>
</div>

<div class="card"><h2>四、逐博主战法清单（口播证据 + 定义 + 前提）</h2>
{tactics_cards()}
<div class="warn"><b>关于邢不行：</b>他本人就是"量化打假"博主，口播里已给出多数战法的回测结论（跌停板、量比、换手率、2560 等大多亏钱）。我复现的方向与他的结论基本一致——这反过来说明本回测框架可信。他少数测出正期望的（烂板 +0.72%、启明星 +2.49%、小市值+低价年化 55%、低换手率年化 28.6%）里，只有偏基本面/风格类的（小市值低价、低换手率）在本口径近三年仍为正，纯图形/打板类在近年明显衰减。</div>
</div>

<div class="card"><h2>五、结论与可用建议</h2>
<div class="bad"><b>没有一个战法能"学会就稳赚"。</b>23 个战法在最近三年、带前提、持有 10 日的口径下，没有一条的 95% 置信区间下限大于 0，扣 50bp 成本后全部为负。这与此前 5 张图、N 字战法、形态研究、行业 ETF 轮动的结论完全一致：单一图形/量价短线信号在 A 股近年没有可靠正超额。</div>
<div class="ok"><b>真正能提炼的、有方向性价值的是三条原则（不是买点）：</b>
<ul>
<li><b>位置优先</b>：几乎每个战法加"低位"前提后都改善。与其记形态，不如先确认处在 120 日区间的底部区域。</li>
<li><b>回避比买入更有据</b>：跌停板、量比追高、反扑日追涨、拉高出货日（三头羊）在近三年都是显著负 edge（−80 到 −213bp）——"别碰这些"比"买什么"更可靠。</li>
<li><b>风格类 &gt; 打板类</b>：小市值+低价、低换手率这类偏风格/基本面的选股，比涨停/跌停/分时博弈类更扛衰减（邢不行本人的长期跟踪也支持这一点）。</li>
</ul></div>
<ul>
<li><b>若一定要试</b>：优先级 小市值+低价（带低位前提）＞ 假破位收回（低位）＞ 五一三（大盘向上+低位），且必须小仓位、严格止损、按 10 日为观察周期，不要指望单次高胜率。</li>
<li>口径局限：事件研究是等权随机抽样信号股，不含盘中买点、涨停板制度、资金席位与仓位管理；邢不行的月频调仓净值口径与本文的"相对随机 edge"口径不同，不能混谈收益率。</li>
<li>本结论只覆盖日 K 可量化部分；博主强调的盘口/分时/情绪理解属于另一层能力，本数据无法裁决其对错。</li>
</ul>
</div>
<div class="foot">数据源：投资工作台博主情报（382 条 / 7 博主 / 266 条 ASR）· panel_v3.pkl 全A后复权面板 · 本页由 全博主战法报告生成器.py 生成</div>
</div></body></html>'''
out=BASE+r'\全博主战法大摸底与回测_2026-11-16.html'
open(out,'w',encoding='utf-8').write(HTML)
print('SAVED',out,'chars',len(HTML))
print('checks table',HTML.count('<table'),HTML.count('</table>'),'div',HTML.count('<div'),HTML.count('</div>'),'None',('>None<' in HTML))
