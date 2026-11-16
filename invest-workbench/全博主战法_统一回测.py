# -*- coding: utf-8 -*-
"""
全博主战法 · 统一回测框架（2026-11-16）

来源：投资工作台博主情报全量导出（382条，7位博主，266条ASR口播稿）→
      全博主战法_口播全量导出_2026-11-16.json

覆盖博主与战法（按口播可量化程度提炼）：
  邢不行（量化打假，自带结论）：五一三 / 2560突破+回踩 / 跌停板(含上升趋势版) /
      量比(2.5-5) / 换手率+量比 / K线形态(启明星·黄昏星·流星·倒锤子) /
      烂板(炸板次日) / 小市值 / 小市值+低价 / 低换手率 / 大跌次日反抽
  凯心：假破位抄底 / 放量跌不动抄底 / 放量止跌+次日缩量
  人性论：拉高出货日(三头羊·回避) / 反扑日(低开冲高回落)
  房子：散户割肉区域抄底
  野人：情绪冰点后修复 / 只做最强(涨停)龙头
  花博：5张图(上轮已单独测，此处不重复)

前提/过滤条件（用户要求重点）：
  每个战法先按博主口播强调的适用前提做成过滤；再对比【无前提 / 带前提】两种口径。
  前提维度：大盘环境(全A等权指数20日趋势)、情绪周期(近期全市场涨跌家数/跌幅)、
            个股位置(120日区间分位)、量能背景、趋势状态(MA60上下)。

口径铁律：后复权 / t日收盘信号→t+1买入 / 持有 5、10、20 交易日 /
          含退市 / 全A等权基准 / 同期全市场随机30只安慰剂 /
          主窗口 2022-01-01~2026（最近几年），全窗口 2018~2026 对照 /
          双边成本 20bp、50bp / 数组强制 copy 防别名污染。
"""
import pickle, json, datetime, warnings
import numpy as np
import pandas as pd
warnings.filterwarnings('ignore'); np.seterr(all='ignore')

DIR = r'D:\我的工作台\02.输出区'
PANEL = DIR + r'\panel_v3.pkl'
OUT = DIR + r'\全博主战法_统一回测结果.json'
def log(*a): print('[ALL]', *a, flush=True)

d, meta = pickle.load(open(PANEL, 'rb'))
dates, codes = meta['dates'], meta['codes']
T, N = len(dates), len(codes)
def M(k): return np.array(d[k].values, dtype=float, copy=True)
O, Hh, Ll, C, CN = M('o'), M('h'), M('l'), M('c'), M('cn')
V, A, TR, MV = M('v'), M('a'), M('tr'), M('mv')
VALID = np.array(d['valid'].values, dtype=bool, copy=True)
LISTED = np.array(d['listed'].values, dtype=bool, copy=True)
OK = np.isfinite(C) & VALID & LISTED & np.isfinite(A) & (A > 0)
years = dates.year
log('panel', T, N, str(dates[0].date()), str(dates[-1].date()))

# ---------- 基准与前提维度 ----------
with np.errstate(all='ignore'):
    DAILY = C[1:] / C[:-1] - 1.0
DAILY[~OK[1:]] = np.nan
bd = np.nanmean(DAILY, axis=1); bd = np.where(np.isfinite(bd), bd, 0.0)
BENCH = np.concatenate([[1.0], np.cumprod(1.0 + bd)])
idx_ma20 = pd.Series(BENCH).rolling(20, min_periods=15).mean().values
MKT_UP = BENCH > idx_ma20                      # 大盘在20日均线上方
# 市场情绪：当日上涨个股占比
UP_RATIO = np.nanmean(DAILY > 0, axis=1)
UP_RATIO = np.concatenate([[0.5], UP_RATIO]); UP_RATIO = np.where(np.isfinite(UP_RATIO), UP_RATIO, 0.5)

def roll(x, w, fn, minp):
    return getattr(pd.DataFrame(x).rolling(w, min_periods=minp), fn)().values
ma5, ma20, ma25, ma60, ma120 = (roll(C,w,'mean',int(w*0.7)) for w in (5,20,25,60,120))
vma5, vma25, vma60 = (roll(V,w,'mean',int(w*0.7)) for w in (5,25,60))
hi120, lo120 = roll(Hh,120,'max',80), roll(Ll,120,'min',80)
pos120 = (C - lo120) / np.maximum(hi120 - lo120, 1e-9)   # 个股位置 0=底 1=顶
ret1 = np.full((T,N), np.nan); ret1[1:] = DAILY
mkt = np.concatenate([[0.0], bd]); EXCESS = ret1 - mkt[:,None]
listed_age = pd.DataFrame(LISTED.astype(float)).rolling(120,min_periods=120).sum().values
TRADABLE = (pd.DataFrame(A).rolling(20,min_periods=10).mean().values >= 5e7) & (listed_age>=119) & OK

# 前提过滤器
PRE = {
 'mkt_up': MKT_UP[:,None],                    # 大盘在20日线上
 'mkt_down': ~MKT_UP[:,None],                 # 大盘在20日线下
 'low_pos': pos120 <= 0.35,                   # 个股低位
 'high_pos': pos120 >= 0.65,                  # 个股高位
 'above_ma60': C > ma60,                      # 趋势向上
 'below_ma60': C < ma60,                      # 趋势向下
 'panic': UP_RATIO[:,None] <= 0.35,           # 市场恐慌(普跌)
 'euphoria': UP_RATIO[:,None] >= 0.65,        # 市场亢奋(普涨)
}

def forward(H):
    F = np.full((T,N), np.nan); BF = np.full(T, np.nan)
    for t in range(0, T-H-1):
        b,s = t+1, t+1+H
        if s>=T: break
        F[t] = C[s]/C[b]-1.0; BF[t] = BENCH[s]/BENCH[b]-1.0
    F[~OK] = np.nan
    for t in range(0,T-H-1):
        s=t+1+H
        if s<T: F[t][~OK[s]]=np.nan
    return F - BF[:,None], F
FWD = {h: forward(h) for h in (5,10,20)}
log('forward built')

# =====================================================================
# 战法信号定义（t 日收盘可见；均乘以 TRADABLE 与冷却）
# =====================================================================
SIG = {}   # name -> bool matrix
def add(name, mat, gap=60, warm=150):
    s = np.nan_to_num(mat, nan=0.0).astype(bool) & TRADABLE
    # 冷却
    out = np.zeros_like(s)
    for j in range(N):
        idx=np.flatnonzero(s[:,j])
        if idx.size==0: continue
        keep=[idx[0]]; last=idx[0]
        for t in idx[1:]:
            if t-last>=gap: keep.append(t); last=t
        out[keep,j]=True
    out[:warm]=False
    SIG[name]=out
    return out

# --- 邢不行系列 ---
# 五一三：5连阳+异动线(上影>实体,量≥前日2倍)+后3日涨幅<5%不破异动开盘价且缩量（简化：异动次日买）
yang5 = (C>O) & (C>np.roll(C,1,axis=0))
y5 = pd.DataFrame(yang5.astype(float)).rolling(5,min_periods=5).sum().values>=4
upper = Hh - np.maximum(O,C); body = np.maximum(np.abs(C-O),1e-9)
yday_vol = np.roll(V,1,axis=0)
yidong = y5 & (upper>=body) & (V>=2*yday_vol)
add('邢_五一三', np.roll(yidong,1,axis=0) & (ret1<=0.05) & (C>np.roll(O,2,axis=0)))

# 2560突破：前日收在MA25下、今收在MA25上，且5日均量上穿60日均量
vr5, vr60 = V/np.maximum(vma5,1e-9), V/np.maximum(vma60,1e-9)
cross25 = (np.roll(C,1,axis=0)<np.roll(ma25,1,axis=0)) & (C>ma25)
volcross = (np.roll(vma5,1,axis=0)<=np.roll(vma60,1,axis=0)) & (vma5>vma60)
add('邢_2560突破', cross25 & volcross)
# 2560回踩：曾站上MA25后缩量回踩MA25上方
add('邢_2560回踩', (C>ma25)&(C<ma25*1.03)&(vma5<vma60)&(np.roll(C,20,axis=0)>np.roll(ma25,20,axis=0)))

# 跌停板：当日跌停(≤-9.5%)；上升趋势版=此前在MA60上
dt = ret1<=-0.095
add('邢_跌停板', dt)
add('邢_跌停板_上升趋势', dt & (np.roll(C,1,axis=0)>np.roll(ma60,1,axis=0)))

# 量比：今日量/5日均量 2.5~5
liangbi = V/np.maximum(vma5,1e-9)
add('邢_量比2.5到5', (liangbi>=2.5)&(liangbi<=5))
# 换手率>5 & 量比2~3  （换手率用 tr 字段，已是百分比）
turn = TR
add('邢_换手5_量比2到3', (turn>=5)&(liangbi>=2)&(liangbi<=3))

# K线形态（简化日频）：启明星=先阴后小阳/十字再阳且重心抬升；黄昏星反向；流星=长上影小实体；倒锤子=长下影小实体
prevC=np.roll(C,1,axis=0); prevO=np.roll(O,1,axis=0)
star_small = (np.abs(C-O) <= 0.3*np.abs(prevC-prevO))
add('邢_启明星', (prevC<prevO)&star_small&(C>O)&(C>prevO+0.3*np.abs(prevC-prevO)))
add('邢_黄昏星', (prevC>prevO)&star_small&(C<O)&(C<prevO-0.3*np.abs(prevC-prevO)))
add('邢_流星长上影', (upper>=2*body)&(Hh>np.maximum(O,C))&(ret1>0)&(C>O))
add('邢_倒锤子长下影', ((np.maximum(O,C)-Ll)>=2*body)&(C>np.roll(C,1,axis=0)))

# 烂板：盘中触及涨停但收盘未涨停
limit_up_price = np.round(np.roll(C,1,axis=0)*1.1,2)
zhaban = (Hh>=limit_up_price*0.999)&(C<limit_up_price*0.98)
add('邢_烂板炸板', zhaban)

# 小市值 / 小市值+低价（横截面按市值分位，取最小的10%）
def cross_pct(x, asc=True):
    out=np.full_like(x, np.nan)
    for t in range(T):
        v=x[t]; ok=np.isfinite(v)&OK[t]
        if ok.sum()<50: continue
        r=pd.Series(v[ok]).rank(pct=True).values
        out[t,ok]=r if asc else 1-r
    return out
mv_rank = cross_pct(MV, asc=True)   # 市值越小rank越小
price_rank = cross_pct(CN, asc=True)
add('邢_小市值', mv_rank<=0.1)
add('邢_小市值低价', (mv_rank<=0.2)&(price_rank<=0.2))
add('邢_低换手率', cross_pct(turn,asc=True)<=0.1, gap=20)

# 大跌次日反抽：今日跌幅>5%
add('邢_大跌次日', ret1<=-0.05)

# --- 凯心系列 ---
# 假破位抄底：低位箱体(振幅小)放量破位后快速收回
box = (hi120/lo120-1)<=0.25
breakdown = (Ll<np.roll(Ll,1,axis=0)) & (C<np.roll(Ll,20,axis=0)*1.02) & (V>1.3*roll(V,20,'mean',10))
recover = (C>np.roll(C,1,axis=0)) & (np.roll(C,1,axis=0)<np.roll(Ll,20,axis=0)*1.02)
add('凯_假破位收回', box & np.roll(recover,1,axis=0) & np.roll(breakdown,2,axis=0))
# 放量跌不动：低位+放量+跌幅小+次日确认
vma20x=roll(V,20,'mean',10)
add('凯_放量跌不动', (pos120<=0.3)&(V>1.5*vma20x)&(ret1>=-0.01)&(ret1<=0.01))
# 放量止跌次日缩量保持
add('凯_放量止跌缩量确认', np.roll((V>1.5*vma20x)&(ret1>=-0.02)&(pos120<=0.4),1,axis=0) & (V<np.roll(V,1,axis=0)*0.8) & (C>=np.roll(C,1,axis=0)*0.99))

# --- 人性论系列 ---
# 拉高出货日：高开+冲高回落+次日低开（次日买=回避信号，此处测"次日买入"看是否该回避）
highopen = O>np.roll(C,1,axis=0)*1.01
chase_back = (Hh>C*1.02) & (C>O)   # 冲高回落收阳
add('人_拉高出货日', highopen & chase_back)  # 当日形态：高开+冲高回落
add('人_反扑日低开冲高', (O<np.roll(C,1,axis=0)*0.99) & (Hh>C*1.02) & (C>O))

# --- 房子/野人 ---
# 散户割肉区域抄底：深跌+恐慌+长下影
add('房_割肉区域抄底', (ret1<=-0.04)&(UP_RATIO[:,None]<=0.35)&((np.maximum(O,C)-Ll)>=body))
# 情绪冰点后首个涨停龙头：市场普跌日的涨停股
add('野_冰点涨停龙头', (UP_RATIO[:,None]<=0.35)&(ret1>=0.095))

log('signals built', len(SIG))
for k,v in SIG.items(): log(' ',k,int(v.sum()))

# =====================================================================
# 评价：无前提 vs 带前提
# =====================================================================
W_START = int(np.where(years==2022)[0][0])
SAMPLE = list(range(150, T-21, 3))
def boot_ci(vals, nboot=500, seed=7):
    a=np.asarray(vals,float)
    if a.size<5: return [None,None]
    rng=np.random.default_rng(seed)
    m=np.array([a[rng.integers(0,a.size,a.size)].mean() for _ in range(nboot)])
    return [round(float(x),5) for x in np.percentile(m,[2.5,97.5])]

def evaluate(mask, h, subset='all'):
    EX,AB=FWD[h]
    per=[]; yr_s={}; yr_r={}; yr_n={}
    sample = [t for t in SAMPLE if (subset!='recent' or t>=W_START)]
    for t in sample:
        mkt_ok = TRADABLE[t] & np.isfinite(EX[t])
        if mkt_ok.sum()<100: continue
        idx=np.flatnonzero(mask[t]&mkt_ok)
        if idx.size<1: continue
        rng=np.random.default_rng(7+t)
        pick=idx[rng.choice(idx.size,min(30,idx.size),replace=False)]
        allidx=np.flatnonzero(mkt_ok); rnd=allidx[rng.choice(allidx.size,30,replace=False)]
        tv=float(EX[t,pick].mean()); rv=float(EX[t,rnd].mean())
        per.append((t,tv-rv,float(AB[t,pick].mean()),float((AB[t,pick]>0).mean())))
        y=int(years[t]); yr_s[y]=yr_s.get(y,0)+tv; yr_r[y]=yr_r.get(y,0)+rv; yr_n[y]=yr_n.get(y,0)+1
    if not per: return None
    e=np.array([x[1] for x in per])
    return {'n_days':len(per),'events':int(mask[[x[0] for x in per]].sum()),
            'edge_bp':round(float(e.mean())*1e4,1),
            'ci95_bp':[None if x is None else round(x*1e4,1) for x in boot_ci(e)],
            'win_rate':round(float(np.mean([x[3] for x in per])),4),
            'mean_ret':round(float(np.mean([x[2] for x in per])),4),
            'edge_20bp':round((e.mean()-0.004)*1e4,1),
            'edge_50bp':round((e.mean()-0.010)*1e4,1),
            'by_year':{str(y):round((yr_s[y]/yr_n[y]-yr_r[y]/yr_n[y])*1e4,1) for y in sorted(yr_n)}}

# 每个战法的前提映射（博主口播强调）
PREMAP = {
 '邢_五一三':['mkt_up','low_pos'],
 '邢_2560突破':['mkt_up','above_ma60'],
 '邢_2560回踩':['mkt_up','above_ma60'],
 '邢_跌停板':['low_pos'],
 '邢_跌停板_上升趋势':['mkt_up','above_ma60'],
 '邢_量比2.5到5':['mkt_up'],
 '邢_换手5_量比2到3':['mkt_up'],
 '邢_启明星':['low_pos','mkt_up'],
 '邢_黄昏星':['high_pos'],
 '邢_流星长上影':['high_pos'],
 '邢_倒锤子长下影':['low_pos'],
 '邢_烂板炸板':['mkt_up'],
 '邢_小市值':['mkt_up'],
 '邢_小市值低价':['low_pos'],
 '邢_低换手率':['mkt_up'],
 '邢_大跌次日':['low_pos','panic'],
 '凯_假破位收回':['low_pos'],
 '凯_放量跌不动':['low_pos','panic'],
 '凯_放量止跌缩量确认':['low_pos'],
 '人_拉高出货日':['high_pos','euphoria'],
 '人_反扑日低开冲高':['low_pos'],
 '房_割肉区域抄底':['low_pos','panic'],
 '野_冰点涨停龙头':['panic'],
}
results={}
for name,sig in SIG.items():
    entry={'no_pre':{},'with_pre':{}}
    filt=np.ones_like(sig)
    for p in PREMAP.get(name,[]): filt = filt & PRE[p]
    for h in (5,10,20):
        entry['no_pre']['H%d'%h]={'recent':evaluate(sig,h,'recent'),'full':evaluate(sig,h,'all')}
        entry['with_pre']['H%d'%h]={'recent':evaluate(sig&filt,h,'recent'),'full':evaluate(sig&filt,h,'all')}
    results[name]=entry
    r0=entry['no_pre']['H10']['recent']; r1=entry['with_pre']['H10']['recent']
    log(name,'H10 recent 无前提',r0['edge_bp'] if r0 else None,'带前提',r1['edge_bp'] if r1 else None)

out={'meta':{
    'generated':datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    'start':str(dates[0].date()),'end':str(dates[-1].date()),
    'recent_start':str(dates[W_START].date()),
    'T':T,'N':N,'sample_step':3,
    'source':'投资工作台博主情报全量导出 382条/7博主/266条ASR',
    'note':'日频量化近似；t日收盘信号→t+1买入→持有5/10/20日；后复权含退市；'
           '全A等权基准+随机30只安慰剂；recent=2022起(最近几年),full=2018起全窗口对照；'
           '无前提=仅战法信号+流动性过滤,带前提=叠加博主强调的大盘/位置/情绪/趋势条件；'
           '成本20/50bp。',
    },
    'pre_defs':{k:'大盘20日线上' if k=='mkt_up' else '大盘20日线下' if k=='mkt_down' else
                '个股120日分位≤0.35' if k=='low_pos' else '个股120日分位≥0.65' if k=='high_pos' else
                '个股价>MA60' if k=='above_ma60' else '个股价<MA60' if k=='below_ma60' else
                '全市场上涨占比≤0.35(普跌恐慌)' if k=='panic' else '全市场上涨占比≥0.65(普涨亢奋)'
                for k in PRE},
    'premap':PREMAP,
    'results':results,
}
json.dump(out,open(OUT,'w',encoding='utf-8'),ensure_ascii=False,indent=1)
log('SAVED',OUT)
