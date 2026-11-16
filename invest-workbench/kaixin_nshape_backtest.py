# -*- coding: utf-8 -*-
"""
凯心「N字战法」· 日频量化近似回测（2026-11-16）

来源：投资工作台博主情报 → 凯心（登记名，用户称"凯鑫"）N字系统第四/五/八/九集
及"非常符合现在""假破位，别被骗了""一招确认真底部"口播稿（14条已存本地素材）。

战法还原（口播核心）：
  N = 三笔结构
  ① 第一笔「强度日」：资金主动进攻的大阳/涨停，三条件须同时成立——
     可辨识(比普通波动更主动醒目)、可归因(事件/题材/板块/个股逻辑)、相对独立(非指数带上来)
     三种起手：水下长阳(成本低但分散)、水上短阳(成本集中)、一字板(最集中)
  ② 第二笔「回踩/洗盘」：释放分歧中有承接；良性证据=量能递减、下杀快速承接、
     低点不破、下影线收敛、节奏平缓；负面=放量、长期受均线压制、反弹被卖回
  ③ 第三笔「回流买点」：H=强度日最高成交价、L=最低(含上下影线)、D=H-L；
     六=L+0.4D、七=L+0.3D、八=L+0.2D（即回吐当日涨幅60%~80%）；
     六七八只是"观察区"，必须有止跌+承接证据才下单；一字/短阳须与前一交易日合并算H/L。

日频近似（无法看分时零轴/黄线，故只用日K可观测项）：
  强度日 = 日涨幅≥7% & 量/20日均量≥1.5 & 相对全A等权超额≥5%
  回踩   = 强度日次日至信号日最低价不破 L×0.98（允许微破）
  买点区 = 收盘落在 [L+0.2D, L+0.4D]（六七八）
  止跌   = 当日收盘 > 前一日收盘
  强度日起 10 个交易日内首次满足即记信号；同股 60 日冷却。

口径铁律：后复权 / t日收盘信号→t+1买入 / 持有 5、10、20 日 / 全A等权基准 /
          同期全市场随机30只安慰剂 / IS(2018-2021)+OOS(2022-2026) / 双边成本20、50bp。
变体拆解：core / limitup(涨停起手) / deep(只取七八) / nostop(去掉止跌证据) /
          shrink(加强制缩量) / merged(一字短阳合并前一日H/L)。
"""
import pickle, json, datetime, warnings
import numpy as np
import pandas as pd
warnings.filterwarnings('ignore'); np.seterr(all='ignore')

DIR = r'D:\我的工作台\02.输出区'
PANEL = DIR + r'\panel_v3.pkl'
OUT = DIR + r'\kaixin_nshape_result.json'
def log(*a): print('[NX]', *a, flush=True)

d, meta = pickle.load(open(PANEL, 'rb'))
dates, codes = meta['dates'], meta['codes']
T, N = len(dates), len(codes)
C  = np.array(d['c'].values,  dtype=float, copy=True)
Hh = np.array(d['h'].values,  dtype=float, copy=True)
Ll = np.array(d['l'].values,  dtype=float, copy=True)
V  = np.array(d['v'].values,  dtype=float, copy=True)
A  = np.array(d['a'].values,  dtype=float, copy=True)
VALID  = np.array(d['valid'].values, dtype=bool, copy=True)
LISTED = np.array(d['listed'].values, dtype=bool, copy=True)
OK = np.isfinite(C) & VALID & LISTED & np.isfinite(A) & (A > 0)
years = dates.year
log('panel', T, N, str(dates[0].date()), str(dates[-1].date()))

# 基准 & 个股相对超额
with np.errstate(all='ignore'):
    DAILY = C[1:] / C[:-1] - 1.0
DAILY[~OK[1:]] = np.nan
bd = np.nanmean(DAILY, axis=1); bd = np.where(np.isfinite(bd), bd, 0.0)
BENCH = np.concatenate([[1.0], np.cumprod(1.0 + bd)])
ret1 = np.full((T, N), np.nan)
ret1[1:] = DAILY
mkt = np.concatenate([[0.0], bd])
EXCESS = ret1 - mkt[:, None]

def roll(x, w, fn, minp):
    return getattr(pd.DataFrame(x).rolling(w, min_periods=minp), fn)().values
vma20 = pd.DataFrame(V).rolling(20, min_periods=10).mean().values
amt20 = pd.DataFrame(A).rolling(20, min_periods=10).mean().values
listed_age = pd.DataFrame(LISTED.astype(float)).rolling(120, min_periods=120).sum().values
TRADABLE = (amt20 >= 5e7) & (listed_age >= 119) & OK

def forward(H):
    F = np.full((T, N), np.nan); BF = np.full(T, np.nan)
    for t in range(0, T - H - 1):
        b, s = t + 1, t + 1 + H
        if s >= T: break
        F[t] = C[s] / C[b] - 1.0
        BF[t] = BENCH[s] / BENCH[b] - 1.0
    F[~OK] = np.nan
    for t in range(0, T - H - 1):
        s = t + 1 + H
        if s < T: F[t][~OK[s]] = np.nan
    return F - BF[:, None], F
FWD = {h: forward(h) for h in (5, 10, 20)}
log('forward built 5/10/20')

# ---------- 强度日事件 ----------
strong_base = (ret1 >= 0.07) & (V / np.maximum(vma20, 1e-9) >= 1.5) & (EXCESS >= 0.05) & TRADABLE
strong_lu   = (ret1 >= 0.095) & (V / np.maximum(vma20, 1e-9) >= 1.5) & TRADABLE
log('strong days base', int(np.nansum(strong_base)), 'limitup', int(np.nansum(strong_lu)))

# 逐强度日向后找买点（事件驱动，避免 T*N 全扫描）
def build_signal(strong, lo_frac, hi_frac, need_stop, need_shrink, merged, window=10, gap=60):
    sig = np.zeros((T, N), dtype=bool)
    ts, js = np.where(np.nan_to_num(strong, nan=0.0))
    for j, t0 in zip(js, ts):
        hh = Hh[t0, j]; ll = Ll[t0, j]
        if merged and t0 > 0:
            hh = max(hh, Hh[t0-1, j]); ll = min(ll, Ll[t0-1, j])
        D = hh - ll
        if not np.isfinite(D) or D <= 0: continue
        b_lo, b_hi = ll + lo_frac * D, ll + hi_frac * D
        v_strong = V[t0, j]
        placed = False
        for t in range(t0 + 1, min(t0 + window + 1, T)):
            if not (OK[t, j] and TRADABLE[t, j]): continue
            # 回踩不破强度日低点（允许 2% 微破）
            seg_lo = np.nanmin(Ll[t0+1:t+1, j])
            if seg_lo < ll * 0.98: break
            px = C[t, j]
            if not (b_lo <= px <= b_hi): continue
            if need_stop and not (np.isfinite(C[t-1, j]) and px > C[t-1, j]): continue
            if need_shrink and not (V[t, j] < v_strong * 0.8): continue
            # 60日冷却：该股此前 60 日内是否已有信号
            prior = np.flatnonzero(sig[max(0, t-gap):t, j])
            if prior.size: break
            sig[t, j] = True; placed = True; break
    return sig

CFG = {
    'N_core':          dict(strong=strong_base, lo=0.20, hi=0.40, stop=True,  shrink=False, merged=False),
    'N_limitup':       dict(strong=strong_lu,   lo=0.20, hi=0.40, stop=True,  shrink=False, merged=False),
    'N_deep_七八':      dict(strong=strong_base, lo=0.20, hi=0.30, stop=True,  shrink=False, merged=False),
    'N_nostop_无止跌':  dict(strong=strong_base, lo=0.20, hi=0.40, stop=False, shrink=False, merged=False),
    'N_shrink_强缩量':  dict(strong=strong_base, lo=0.20, hi=0.40, stop=True,  shrink=True,  merged=False),
    'N_merged_合并K':   dict(strong=strong_base, lo=0.20, hi=0.40, stop=True,  shrink=False, merged=True),
}
SIGS = {}
for name, c in CFG.items():
    s = build_signal(c['strong'], c['lo'], c['hi'], c['stop'], c['shrink'], c['merged'])
    s[:150] = False
    SIGS[name] = s
    log('signal', name, int(s.sum()))

# ---------- 评价 ----------
SAMPLE = list(range(150, T - 21, 3))
IS_END = int(np.where(years == 2022)[0][0])
def boot_ci(vals, nboot=600, seed=7):
    a = np.asarray(vals, float)
    if a.size < 5: return [None, None]
    rng = np.random.default_rng(seed)
    m = np.array([a[rng.integers(0, a.size, a.size)].mean() for _ in range(nboot)])
    return [round(float(x), 5) for x in np.percentile(m, [2.5, 97.5])]

def evaluate(mask, h):
    EX, AB = FWD[h]
    per_day = []; yr_sum = {}; yr_rnd = {}; yr_n = {}
    for t in SAMPLE:
        mkt_ok = TRADABLE[t] & np.isfinite(EX[t])
        if mkt_ok.sum() < 100: continue
        idx = np.flatnonzero(mask[t] & mkt_ok)
        if idx.size < 1: continue
        rng = np.random.default_rng(7 + t)
        pick = idx[rng.choice(idx.size, min(30, idx.size), replace=False)]
        allidx = np.flatnonzero(mkt_ok)
        rnd = allidx[rng.choice(allidx.size, 30, replace=False)]
        tv = float(EX[t, pick].mean()); rv = float(EX[t, rnd].mean())
        per_day.append((t, tv - rv, float(AB[t, pick].mean()), float((AB[t, pick] > 0).mean()), idx.size))
        y = int(years[t])
        yr_sum[y] = yr_sum.get(y, 0)+tv; yr_rnd[y] = yr_rnd.get(y, 0)+rv; yr_n[y] = yr_n.get(y, 0)+1
    if not per_day: return None
    edges = np.array([x[1] for x in per_day])
    def seg(fn):
        v = np.array([x[1] for x in per_day if fn(x[0])])
        return {'edge_bp': round(float(v.mean())*1e4,1) if v.size else None,
                'win_day_rate': round(float((v>0).mean()),3) if v.size else None, 'n_days': int(v.size)}
    return {'H': h, 'events': int(mask.sum()),
            'avg_cells_per_day': round(float(np.mean([x[4] for x in per_day])),2),
            'mean_ret': round(float(np.mean([x[2] for x in per_day])),4),
            'win_rate': round(float(np.mean([x[3] for x in per_day])),4),
            'edge_bp': round(float(edges.mean())*1e4,1),
            'ci95_bp': [None if x is None else round(x*1e4,1) for x in boot_ci(edges)],
            'all': seg(lambda t: True), 'is': seg(lambda t: t<IS_END), 'oos': seg(lambda t: t>=IS_END),
            'by_year_edge_bp': {str(y): round((yr_sum[y]/yr_n[y]-yr_rnd[y]/yr_n[y])*1e4,1) for y in sorted(yr_n)},
            'edge_after_20bp': round((edges.mean()-0.004)*1e4,1),
            'edge_after_50bp': round((edges.mean()-0.010)*1e4,1)}

results = {}
for name, mask in SIGS.items():
    entry = {}
    for h in (5, 10, 20):
        r = evaluate(mask, h); entry['H%d'%h] = r
        log(name, 'H%d'%h, 'edge', r['edge_bp'] if r else None,
            'OOS', r['oos']['edge_bp'] if r else None, 'n_days', r['all']['n_days'] if r else 0)
    results[name] = entry

out = {
    'meta': {
        'generated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'start': str(dates[0].date()), 'end': str(dates[-1].date()),
        'T': T, 'N': N, 'is_end': str(dates[IS_END].date()), 'sample_step': 3,
        'source': '投资工作台博主情报·凯心(N字战法) 14条ASR口播稿',
        'note': '原图在视频画面不可得；本回测为口播文字可识别规则的日频量化近似，非分时逐tick复刻。'
                't日收盘信号→t+1买入→持有5/10/20日；后复权；全A等权基准；随机30只安慰剂；'
                '同股60日冷却；成交≥5000万、上市≥120日。',
    },
    'definition': {
        'N结构': '第一笔强度日(资金主动进攻的大阳/涨停) → 第二笔缩量回踩(低点不破、有承接) → 第三笔六七八买点回流',
        '强度日': '日涨幅≥7% & 量/20日均量≥1.5 & 相对全A超额≥5%（三条件对应口播"可辨识/可归因/相对独立"的日频近似）',
        '回踩': '强度日次日至买点日最低不破强度日低点L×0.98',
        '六七八买点': 'H=强度日最高、L=最低(含上下影线)、D=H-L；六=L+0.4D、七=L+0.3D、八=L+0.2D（回吐60~80%涨幅）',
        '止跌证据': '信号日收盘 > 前一日收盘（口播"六七八只是观察区，须有止跌承接才下单"的日频近似）',
        '起手分类': '水下长阳/水上短阳/一字板（口播称三种操作方法不同；日频用limitup与merged变体近似）',
    },
    'variants': {
        'N_core': '完整定义',
        'N_limitup': '强度日改为涨停起手（涨幅≥9.5%）',
        'N_deep_七八': '只取更深回踩的七、八位置（L+0.2~0.3D）',
        'N_nostop_无止跌': '去掉"收盘>前收"的止跌证据（纯价格到位就买）',
        'N_shrink_强缩量': '增加"信号日量<强度日量×0.8"的强制缩量',
        'N_merged_合并K': '一字/短阳起手按口播与前一交易日合并H/L',
    },
    'results': results,
}
json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
log('SAVED', OUT)
