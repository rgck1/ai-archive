# -*- coding: utf-8 -*-
"""综合报告：① 花博5张图在ETF上的补测 ② 凯心N字战法溯源与回测"""
import json
BASE = r'D:\我的工作台\02.输出区'
ETF = json.load(open(BASE + r'\huabo_five_shapes_etf_result.json', encoding='utf-8'))
STK = json.load(open(BASE + r'\huabo_five_shapes_result.json', encoding='utf-8'))
NX  = json.load(open(BASE + r'\kaixin_nshape_result.json', encoding='utf-8'))
ETR, EDEF = ETF['results'], ETF['definitions']
NR, NDEF, NVAR = NX['results'], NX['definition'], NX['variants']

def esc(s): return str(s).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
def bp(x): return ('%+d') % round(x) if x is not None else '—'
def pct(x): return ('%.1f%%') % (x*100) if x is not None else '—'
def col(x): return '#c0392b' if (x is not None and x>0) else ('#1e8449' if x is not None else '#8a93a0')

LABEL = {
 'G1_鱼尾顶_回避':'图形一 · 鱼尾顶（回避）','G2a_平台回踩下沿':'图形二a · 平台回踩下沿',
 'G2b_平台放量突破':'图形二b · 平台放量突破','G3_低位放量拐点':'图形三 · 价值拐点',
 'G4_下跌反弹_不扎实':'图形四 · 下跌反弹（不扎实）','G5_扎实底_V反转':'图形五 · 扎实底（V反转）'}

# ---------- ETF 补测表 ----------
def etf_table():
    rows=''
    for k,v in ETR.items():
        h=v['main_H']; r=v['H%d'%h]
        sr=STK['results'][k]['H%d'%STK['results'][k]['main_H']]
        if not r:
            rows+=(f'<tr><td style="text-align:left"><b>{esc(LABEL[k])}</b></td><td>0</td>'
                   f'<td colspan="6" class="sub" style="text-align:center">ETF池无有效形态样本，无法评价</td>'
                   f'<td style="color:{col(sr["edge_bp"])}">{bp(sr["edge_bp"])}</td></tr>')
            continue
        ci=r['ci95_bp']
        ci_s=f'{bp(ci[0])} ~ {bp(ci[1])}' if ci[0] is not None else '样本不足'
        rows+=(f'<tr><td style="text-align:left"><b>{esc(LABEL[k])}</b><br><span class="sub">H={h}</span></td>'
               f'<td>{r["events"]}</td><td class="sub">{r["all"]["n_days"]}</td>'
               f'<td style="color:{col(r["edge_bp"])};font-weight:700">{bp(r["edge_bp"])}</td>'
               f'<td class="sub">{ci_s}</td>'
               f'<td style="color:{col(r["is"]["edge_bp"])}">{bp(r["is"]["edge_bp"])}</td>'
               f'<td style="color:{col(r["oos"]["edge_bp"])}">{bp(r["oos"]["edge_bp"])}</td>'
               f'<td style="color:{col(r["edge_after_50bp"])}">{bp(r["edge_after_50bp"])}</td>'
               f'<td style="color:{col(sr["edge_bp"])}">{bp(sr["edge_bp"])}</td></tr>')
    return ('<table><tr><th style="text-align:left">图形</th><th>ETF事件</th><th>有效日</th><th>ETF edge</th>'
            '<th>95%CI</th><th>样本内</th><th>样本外</th><th>扣50bp</th><th>股票版edge<br><span class="sub">(对照)</span></th></tr>'
            +rows+'</table>')

# ---------- N字主表 ----------
NH = ['H5','H10','H20']
def nx_table(h):
    rows=''
    for k,v in NR.items():
        r=v[h]
        ci=r['ci95_bp']; ci_s=f'{bp(ci[0])} ~ {bp(ci[1])}' if ci[0] is not None else '样本不足'
        rows+=(f'<tr><td style="text-align:left"><b>{esc(k)}</b><br><span class="sub">{esc(NVAR[k])}</span></td>'
               f'<td>{r["events"]}</td>'
               f'<td style="color:{col(r["edge_bp"])};font-weight:700">{bp(r["edge_bp"])}</td>'
               f'<td class="sub">{ci_s}</td>'
               f'<td style="color:{col(r["is"]["edge_bp"])}">{bp(r["is"]["edge_bp"])}</td>'
               f'<td style="color:{col(r["oos"]["edge_bp"])}">{bp(r["oos"]["edge_bp"])}</td>'
               f'<td>{pct(r["win_rate"])}</td>'
               f'<td style="color:{col(r["edge_after_50bp"])}">{bp(r["edge_after_50bp"])}</td></tr>')
    return ('<table><tr><th style="text-align:left">变体</th><th>信号数</th><th>edge vs 随机</th><th>95%CI</th>'
            '<th>样本内</th><th>样本外</th><th>胜率</th><th>扣50bp</th></tr>'+rows+'</table>')

def nx_bars():
    items=[]
    for k,v in NR.items():
        for h in NH:
            items.append((k.replace('N_','').split('_')[0]+'·'+h, v[h]['edge_bp'], v[h]['oos']['edge_bp']))
    row=25; W=680; H=len(items)*row+58; L=118; Rp=70
    pw=W-L-Rp; zero=L+pw/2
    mx=max(max(abs(a or 0),abs(b or 0)) for _,a,b in items)*1.15 or 1
    s=[f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:680px">',
       f'<line x1="{zero}" y1="10" x2="{zero}" y2="{H-34}" stroke="#c9d0d8" stroke-dasharray="3 3"/>']
    for i,(name,allv,oosv) in enumerate(items):
        y=14+i*row
        s.append(f'<text x="{L-8}" y="{y+11}" font-size="10" fill="#444" text-anchor="end">{esc(name)}</text>')
        for j,(val,off,alpha) in enumerate([(allv,2,'1'),(oosv,13,'.5')]):
            if val is None: continue
            w=abs(val)/mx*(pw/2); x=zero if val>0 else zero-w
            s.append(f'<rect x="{x:.1f}" y="{y+off}" width="{w:.1f}" height="8" rx="2" fill="{col(val)}" opacity="{alpha}"/>')
            tx=zero+w+3 if val>0 else zero-w-3
            s.append(f'<text x="{tx:.1f}" y="{y+off+8}" font-size="9" fill="{col(val)}" text-anchor="{"start" if val>0 else "end"}">{bp(val)}</text>')
    s.append(f'<rect x="{L}" y="{H-27}" width="11" height="8" rx="2" fill="#7b8794"/><text x="{L+15}" y="{H-20}" font-size="10" fill="#6b7480">全期</text>')
    s.append(f'<rect x="{L+56}" y="{H-27}" width="11" height="8" rx="2" fill="#7b8794" opacity=".5"/><text x="{L+71}" y="{H-20}" font-size="10" fill="#6b7480">样本外</text>')
    s.append(f'<text x="{L+125}" y="{H-20}" font-size="10" fill="#8a93a0">edge（bp），红正绿负</text></svg>')
    return ''.join(s)

def nx_quote():
    return [
      ('第一笔 · 强度日','「我们要把N拆成一个可以被验证也可以被否决的什么东西……资金证据量，这个是整个贯穿N的一个核心」「第一笔证明它的真实强度……可辨识、可归因、相对独立，三项必须同时成立」「分为长阳、短阳和一字，它们有不同的操作方式」'),
      ('第二笔 · 回踩承接','「释放分歧之中的过程中有承接」「良性回踩：成交量整体递减、下杀之后快速出现承接、全天低点不破、下影线逐步收敛、回踩节奏平缓」「负面信号：成交量持续放大、价格长期受分时均线压制、反弹一出现就被卖回去」'),
      ('第三笔 · 六七八买点','「取最高的成交价H、最低的L，H减L等于D……六的位置十三块五二、七十三块三九、八十三块二六」「六七八这三个买点没有绝对的优劣，是机会和安全边际的取舍」「六七八只是观察区，并不等于自动到了买点，前提依然出现了止跌和承接的证据」'),
      ('一字/短阳的处理','「跳空高开、一字板要跟前一天合并……找到顶边和底边，合并成一条阳线去计算六七八」「二连板N也会把两个阳线作为合并做操作」'),
    ]

def nx_defs_table():
    rows=''
    for k,v in NDEF.items():
        rows+=f'<tr><td style="text-align:left"><b>{esc(k)}</b></td><td style="text-align:left" class="quote">{esc(v)}</td></tr>'
    return '<table><tr><th style="text-align:left">要素</th><th style="text-align:left">口播还原 + 日频量化近似</th></tr>'+rows+'</table>'

def nx_quote_table():
    rows=''
    for k,q in nx_quote():
        rows+=f'<tr><td style="text-align:left"><b>{esc(k)}</b></td><td style="text-align:left" class="quote">{esc(q)}</td></tr>'
    return '<table><tr><th style="text-align:left">结构</th><th style="text-align:left">口播原话（ASR）</th></tr>'+rows+'</table>'

positive_all=sum(1 for v in NR.values() for h in NH if v[h]['edge_bp']>0)
positive_oos=sum(1 for v in NR.values() for h in NH if v[h]['oos']['edge_bp']>0)
total=len(NR)*3

HTML=f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>博主战法补充研究：ETF上的5张图 + 凯心N字战法 · 2026-11-16</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f4f6f9;color:#222b38;font-family:-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;line-height:1.68}}
.wrap{{max-width:1080px;margin:0 auto;padding:28px 22px 70px}}
.hero{{background:linear-gradient(135deg,#17263b,#2b4468);color:#fff;border-radius:14px;padding:30px 34px;box-shadow:0 8px 24px rgba(23,38,59,.18)}}
.hero h1{{margin:0 0 8px;font-size:24px;letter-spacing:.4px}}.hero .meta{{font-size:12.5px;opacity:.85}}
.hero .tag{{display:inline-block;background:rgba(255,255,255,.14);border-radius:20px;padding:3px 12px;font-size:11.5px;margin:10px 6px 0 0}}
.card{{background:#fff;border-radius:12px;padding:22px 26px;margin:18px 0;box-shadow:0 2px 10px rgba(20,40,70,.06)}}
.card h2{{font-size:18px;margin:0 0 6px;color:#1b2a41;border-left:4px solid #c0392b;padding-left:11px}}
.card h3{{font-size:14px;margin:20px 0 8px;color:#2c3e50}}
.lead{{font-size:13px;color:#596273;margin:6px 0 14px}}
table{{border-collapse:collapse;width:100%;font-size:12px;margin:10px 0}}
th,td{{border-bottom:1px solid #e8ecf1;padding:8px 7px;text-align:center;vertical-align:top}}
th{{background:#f0f3f7;color:#3a4658;font-weight:600;font-size:11px}}
tr:hover td{{background:#fafbfd}}.sub{{color:#8a93a0;font-size:10.5px}}
.quote{{font-size:11.5px;color:#45505f;line-height:1.6}}
.warn{{background:#fff7e8;border-left:4px solid #d98922;padding:12px 16px;border-radius:6px;font-size:12.5px;color:#6b4b1b;margin:14px 0}}
.ok{{background:#f0f8f3;border-left:4px solid #1e8449;padding:12px 16px;border-radius:6px;font-size:13px;color:#1e5a37;margin:14px 0}}
.bad{{background:#fdf1f0;border-left:4px solid #c0392b;padding:12px 16px;border-radius:6px;font-size:13px;color:#7b2c22;margin:14px 0}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0}}
.kpi{{background:#f7f9fc;border:1px solid #e8edf3;border-radius:9px;padding:13px 15px}}
.kpi .n{{font-size:21px;font-weight:700;color:#1b2a41}}.kpi .t{{font-size:11px;color:#8a93a0;margin-top:3px}}
ul{{font-size:13px;padding-left:20px}}li{{margin:6px 0}}
code{{background:#f0f3f7;padding:1px 5px;border-radius:4px;font-size:11.5px}}
.foot{{font-size:11px;color:#9aa3b0;text-align:center;margin-top:26px}}
.sec{{font-size:12px;color:#c0392b;font-weight:700;letter-spacing:1px;margin-top:4px}}
</style></head><body><div class="wrap">
<div class="hero"><h1>博主战法补充研究：ETF 上的 5 张图 + 凯心 N 字战法</h1>
<div class="meta">生成 {NX['meta']['generated']} · 股票面板 {STK['meta']['start']}~{STK['meta']['end']} · ETF面板 {ETF['meta']['start']}~{ETF['meta']['end']}</div>
<div class="tag">来源：投资工作台「博主情报」ASR 口播稿</div>
<div class="tag">后复权 / t+1 买入 / 随机安慰剂 / 样本外 / 成本敏感性</div>
<div class="tag">红=正 edge，绿=负 edge</div></div>

<div class="card"><h2>上半场 · 花博「5 张图」换成 ETF 是什么结果</h2>
<p class="lead">上一份报告测的是全 A 股票。这次把同样的 5 类形态、同样的定义原样搬到 48 只 ETF 池（后复权，2016–2026）。ETF 波动更小、没有个股那种急涨急跌与"游资接力"，预期形态事件会大幅减少；流动性门槛从股票的 5000 万降到 500 万（ETF 成交额中位数仅 156 万），对照组改为「当日全部可交易 ETF 等权」。</p>
<div class="warn"><b>先说结论：5 张图在 ETF 上基本不适用。</b>六类形态里 <b>图形一、图形四在 ETF 池里一次都没出现</b>（ETF 极少出现个股那种高位鱼尾顶 / 深跌急反弹），图形三只有 8 个事件、图形二 b 只有 23 个。剩下能评价的形态，有效样本日只有 5～11 天，置信区间全部跨 0——统计上什么也说不了。</div>
{etf_table()}
<div class="bad"><b>唯一"看起来"有信号的是图形五（扎实底）在 ETF 上 60 日 edge −983bp（95%CI −1734 ~ −64）</b>——但这是<b>显著为负</b>：ETF 里"踩实了再抄"反而大幅跑输随机。这与股票版方向一致（股票版图形五 H60 −189bp），等于再次否定了"抄底只抄图形五"。图形二 a（平台回踩下沿）H60 −67bp、样本外 +104bp 但样本日内只有 11 天、CI 跨 0，无法采信。</div>
<p class="lead">对照最后两列可以看到：股票版里唯一全期+样本外都为正的「图形二 a · 平台回踩下沿 +134bp」，到 ETF 上就变成 −67bp 且样本外翻正但全期为负。<b>同一套形态换一个池子结论就翻转</b>，本身就是"这不是稳定规律"的证据。</p>
</div>

<div class="card"><h2>下半场 · 凯心「N 字战法」是什么，能不能用</h2>
<p class="sec">博主身份核对</p>
<p class="lead">工作台登记的博主名是 <b>凯心</b>（你称"凯鑫"），抖音口播标签为「#N字战法 #妖N战法」。他的账号里有完整的《N 字系统》第一～十一集系列课。我拉取了 14 条相关视频的 ASR 口播稿（第四/五/八/九/十/十一集 +  buyer's guide 类短视频），还原如下。</p>
<p class="sec">一、战法到底是什么：一个"三笔"结构</p>
<p class="lead">N 字战法不是某个技术指标，而是把一段行情拆成三笔资金行为，逐笔用证据验证。核心口诀是「资金证据量」——看懂背后资金在干嘛，图形长得像不算数。</p>
{nx_quote_table()}
{nx_defs_table()}
<div class="warn"><b>还原边界：</b>教学图只画在视频画面里，工作台保存的是 ASR 口播文字，视频直链已过可取窗口。尤其"分时零轴 / 黄线 / 下影线收敛 / 承接快慢"这类盘中细节，日 K 面板无法观测。因此回测测的是<b>口播里能用日 K 明确识别的规则的量化近似</b>，不是分时逐笔复刻。我在下方专门拆了「无止跌证据」变体，就是看口播反复强调的"必须有止跌承接才下单"到底值多少钱。</div>

<p class="sec">二、怎么测的</p>
<p class="lead">后复权价；t 日收盘满足买点 → t+1 收盘买入 → 持有 5 / 10 / 20 交易日；全 A 5812 只（含退市）；成交≥5000 万、上市≥120 日；同股 60 日冷却。<b>强度日</b>=日涨幅≥7% 且量/20 日均量≥1.5 且相对全 A 超额≥5%（对应口播"可辨识/可归因/相对独立"）；<b>六七八买点</b>=收盘回到 L+0.2D ~ L+0.4D（回吐第一笔涨幅的 60~80%）；<b>止跌证据</b>=当日收盘>前收。edge = 信号股随机 30 只 − 同期全市场随机 30 只。样本内 2018–2021、样本外 2022–2026。</p>

<p class="sec">三、结果（持有 20 日为主表）</p>
<div class="kpis">
<div class="kpi"><div class="n">{total}</div><div class="t">变体 × 持有期组合</div></div>
<div class="kpi"><div class="n" style="color:{col(1 if positive_all else -1)}">{positive_all}/{total}</div><div class="t">全期 edge 为正</div></div>
<div class="kpi"><div class="n" style="color:{col(1 if positive_oos else -1)}">{positive_oos}/{total}</div><div class="t">样本外 edge 为正</div></div>
<div class="kpi"><div class="n" style="color:#1e8449">{bp(min(v[h]['edge_bp'] for v in NR.values() for h in NH))}</div><div class="t">最差组合 edge</div></div>
</div>
<h3>持有 5 日</h3>{nx_table('H5')}
<h3>持有 10 日</h3>{nx_table('H10')}
<h3>持有 20 日</h3>{nx_table('H20')}
<h3>全期 vs 样本外 edge 对比</h3>
{nx_bars()}
</div>

<div class="card"><h2>结论</h2>
<div class="bad"><b>N 字战法在日频量化近似下不能用作盈利系统。</b>{total} 个「变体 × 持有期」组合里，全期 edge 为正 <b>{positive_all}</b> 个、样本外为正 <b>{positive_oos}</b> 个（几乎全军覆没）。最标准的 N_core：持有 10 日 edge <b>−95bp</b>（95%CI −149 ~ −42，显著为负）、持有 20 日 −91bp（CI −165 ~ −17），样本外进一步恶化到 −124bp / −141bp，胜率只有 42%。扣 50bp 双边成本后全部跌到 −190bp 附近。</div>
<div class="ok"><b>口播里最有价值的提醒反而是"负面清单"。</b>「无止跌证据」变体（纯价格到位就买）edge 最差：持有 20 日 −155bp（CI −220 ~ −91），明显差于要求止跌的 N_core −91bp；"更强缩量""合并 K 线"等加码条件也都没能翻正。这说明口播里"六七八只是观察区，必须有止跌承接才下单""排除烂板/尾盘偷袭/业绩雷"这类<b>风险控制条款是有方向性依据的</b>——它们帮你少亏，但不构成稳定盈利的买入系统。</div>
<p class="lead">另一个值得注意的现象：多数变体在<b>样本内（2018–2021）接近 0 甚至小幅为正</b>（如 N_limitup H20 样本内 +42bp、N_deep H20 +72bp），但<b>样本外一律大幅转负</b>（−147bp / −172bp）。这是典型的"早期有效、近年失效"，与先前形态研究、行业 ETF 轮动研究里看到的规律一致——这类基于图形/量价的短线模式，在近年市场里被套利得越来越干净。</p>
<ul>
<li>战法的盘中核心（分时可辨识度、黄线承接、下影线收敛、大资金自救逻辑）在日 K 面板不可观测，本次只测了日 K 可识别部分；课程完整版是否更有效，无法用本数据裁决。</li>
<li>N 字战法是<b>超短线接力</b>体系，真实执行依赖盘中买点、涨停板制度与严格止损；日频"持有 N 日"的检验口径与真实交易差异较大，结论更应理解为"这个图形信号本身有没有统计优势"。</li>
<li>edge 相对的是同期全市场随机选股；若与"题材/龙头/板块强度"等条件组合，可能改善，但那已超出本次可量化范围。</li>
<li>样本区间 2018–2026，单一窗口结论不可外推；A 股 2024 年后量化与监管环境变化进一步削弱短线图形有效性。</li>
</ul>
</div>
<div class="foot">数据源：投资工作台博主情报 ASR 口播稿（花博 8 条 / 凯心 14 条）· panel_v3.pkl 全A后复权面板 · 48 只 ETF 后复权序列 · 本页由 博主战法补充研究_报告.py 生成</div>
</div></body></html>'''

out=BASE + r'\博主战法补充研究_ETF与N字战法_2026-11-16.html'
open(out,'w',encoding='utf-8').write(HTML)
print('SAVED',out,'chars',len(HTML))
print('checks: 占位符',('{' in HTML.replace('{{','').replace('}}','')),'edge正数',positive_all,'OOS正',positive_oos)
