# -*- coding: utf-8 -*-
import json, os, html

BASE = os.path.dirname(os.path.abspath(__file__))
data = json.load(open(os.path.join(BASE, '索引数据.json'), encoding='utf-8'))

blog_color = {'邢不行':'#1d5fbf','花博':'#c0392b','凯心':'#7d3c98'}
order = {'花博':0,'凯心':1,'邢不行':2}
data.sort(key=lambda x:(order.get(x['blogger'],9), -x['vscore']))

def esc(s): return html.escape(str(s or ''))

cards=[]
for x in data:
    color=blog_color.get(x['blogger'],'#555')
    pts=''.join('<li>%s</li>'%esc(p) for p in x.get('points',[]))
    img=''
    if x['img'] and os.path.exists(os.path.join(BASE,x['img'])):
        img='<img src="%s" alt="抽帧" loading="lazy">'%esc(x['img'])
    cards.append('''<div class="card">
<div class="ch"><span class="blog" style="background:%(color)s">%(blogger)s</span>
<a href="%(url)s" target="_blank" class="vid">%(aid)s ↗</a><span class="vscore">画面依赖 %(vs)d</span></div>
<div class="desc">%(desc)s</div>
<div class="visual">画面：%(visual)s</div>
%(pts)s
%(img)s
</div>'''%{'color':color,'blogger':esc(x['blogger']),'url':esc(x['url']),
           'aid':x['aweme_id'],'vs':x['vscore'],'desc':esc(x['desc']),
           'visual':esc(x['visual']),'pts':'<ul class="pts">%s</ul>'%pts if pts else '',
           'img':img})

doc='''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>博主战法视频 · 全量抽帧解析</title><style>
:root{--bg:#f5f6f8;--card:#fff;--text:#1a1d24;--muted:#6b7280;--border:#e3e6eb}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;padding:22px}
.wrap{max-width:960px;margin:0 auto}h1{font-size:23px;margin:0 0 4px}.sub{color:var(--muted);font-size:13px;margin-bottom:18px}
.hero{background:linear-gradient(135deg,#1e3a5f,#2c5282);color:#fff;border-radius:10px;padding:16px 20px;margin-bottom:18px}
.hero b{color:#ffd166}
.card{background:var(--card);border:1px solid var(--border);border-radius:9px;padding:14px 16px;margin-bottom:13px}
.ch{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:6px}
.blog{color:#fff;font-size:12px;padding:2px 9px;border-radius:11px}
.vid{color:#1d5fbf;font-size:13px;font-family:monospace;text-decoration:none}
.vscore{font-size:11px;color:var(--muted);margin-left:auto}
.desc{font-weight:600;margin:3px 0;font-size:15px}
.visual{font-size:12px;color:#8a6d1f;background:#fff8e6;display:inline-block;padding:2px 8px;border-radius:4px;margin:3px 0}
.pts{margin:6px 0;padding-left:20px;color:#444;font-size:13px}.pts li{margin:2px 0}
img{width:100%;max-width:720px;border:1px solid var(--border);border-radius:5px;margin:9px 0;display:block}
.note{background:#eaf7ee;border-left:3px solid #2e9e5b;padding:10px 14px;border-radius:4px;font-size:13px;color:#1e6b3a;margin-bottom:16px}
</style></head><body><div class="wrap">
<h1>博主战法视频 · 全量抽帧解析</h1>
<div class="sub">2026-11-16 · 绕开"主页最近 30 条"限制，按视频 ID 从单条详情页取直链下载抽帧 · 覆盖主页范围外 34 条高画面依赖视频</div>
<div class="hero">
<b>跑量结果：</b>7 位博主主页各只能抓到 16~18 条；全量口播库 382 条里，筛出主页范围外 + 有战法画面依赖的 <b>34 条</b>（花博 6 / 凯心 10 / 邢不行 18），全部下载成功、抽帧完成（34/34，约 1.8GB 视频，mp4 下完即删只留抽帧图）。<br>
<b>关键发现：</b>凯心的 N 字战法白板图解（H−L=D、六七八买点、承接位博弈）与此前回测定义一致；邢不行的量化打假视频里是真实的回测图表/胜率数据，方向与其口播结论互证。画面均已看到，未产生新的可量化信号，原回测结论不变。
</div>
<div class="note">说明：每格图为视频按时间抽帧的网格；带图的条目是本地已拉回的高价值画面。点视频 ID 跳抖音原视频可看完整画面。</div>
__CARDS__
</div></body></html>'''.replace('__CARDS__','\n'.join(cards))

p=os.path.join(BASE,'全量抽帧解析索引.html')
open(p,'w',encoding='utf-8').write(doc)
print('SAVED',p,len(doc),'卡片',len(cards))
