# -*- coding: utf-8 -*-
"""
花臂博士「5 张图」形态体系 · ETF 池量化近似回测（2026-11-16）

与股票版 huabo_five_shapes_backtest.py 同口径、同形态定义，仅把标的换成
48 只 ETF（补充数据/index_etf/etf_hfq_*.csv，后复权/前复权各自内部一致，
只用比例型信号，不跨 ETF 拼绝对价）。

差异说明（写入 meta）：
- 流动性门槛 5000万 -> 500万（ETF 成交额中位数仅 156 万）
- 安慰剂基准改为「当日全部可交易 ETF 等权」（池子仅 48 只，抽样噪声过大）
- 事件样本天然稀疏，min_cells=1；IS/OOS 分界仍为 2022
"""
import glob, os, json, datetime, warnings
import numpy as np
import pandas as pd
warnings.filterwarnings('ignore'); np.seterr(all='ignore')

DIR = r'D:\我的工作台\02.输出区'
CSVDIR = os.path.join(DIR, '补充数据', 'index_etf')
OUT = os.path.join(DIR, 'huabo_five_shapes_etf_result.json')
def log(*a): print('[HUABO-ETF]', *a, flush=True)

# ---------- 组装 ETF 面板 ----------
files = sorted(glob.glob(os.path.join(CSVDIR, 'etf_hfq_*.csv')))
series = {}
for f in files:
    code = os.path.basename(f)[8:-4]
    d = pd.read_csv(f)
    c0 = str(d.columns[0]).lstrip('\ufeff')
    d = d.rename(columns={c0: 'date'})
    d['date'] = pd.to_datetime(d['date'])
    for col in ('open', 'high', 'low', 'close', 'volume', 'amount'):
        d[col] = pd.to_numeric(d[col], errors='coerce')
    d = d.dropna(subset=['date', 'close']).set_index('date').sort_index()
    d = d[~d.index.duplicated(keep='last')]
    series[code] = d
alldates = sorted(set().union(*[set(x.index) for x in series.values()]))
codes = sorted(series)
dates = pd.DatetimeIndex(alldates)
T, N = len(dates), len(codes)
def mat(col):
    out = np.full((T, N), np.nan)
    for j, c in enumerate(codes):
        s = series[c][col].reindex(dates)
        out[:, j] = s.values
    return out
C = mat('close'); Hh = mat('high'); Ll = mat('low'); V = mat('volume'); A = mat('amount')
OK = np.isfinite(C) & np.isfinite(Hh) & np.isfinite(Ll) & np.isfinite(V) & np.isfinite(A) & (C > 0) & (A > 0)
years = dates.year
log('panel T,N', T, N, str(dates[0].date()), str(dates[-1].date()), 'cells', int(OK.sum()))

# ---------- 基准：当日全部可交易 ETF 等权 ----------
with np.errstate(all='ignore'):
    DAILY = C[1:] / C[:-1] - 1.0
DAILY[~OK[1:]] = np.nan
bd = np.nanmean(DAILY, axis=1)
bd = np.where(np.isfinite(bd), bd, 0.0)
BENCH = np.concatenate([[1.0], np.cumprod(1.0 + bd)])

def roll(x, w, fn, minp):
    return getattr(pd.DataFrame(x).rolling(w, min_periods=minp), fn)().values

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
EX20, AB20 = forward(20); EX60, AB60 = forward(60)
log('forward built')

# ---------- 特征（与股票版完全同构）----------
ma20 = roll(C, 20, 'mean', 15); ma60 = roll(C, 60, 'mean', 40); ma120 = roll(C, 120, 'mean', 80)
hi20, lo20 = roll(Hh, 20, 'max', 15), roll(Ll, 20, 'min', 15)
hi120, lo120 = roll(Hh, 120, 'max', 80), roll(Ll, 120, 'min', 80)
minlow60 = roll(Ll, 60, 'min', 40)
vma5 = pd.DataFrame(V).rolling(5, min_periods=3).mean().values
vma20 = pd.DataFrame(V).rolling(20, min_periods=10).mean().values
vma120 = pd.DataFrame(V).rolling(120, min_periods=60).mean().values
amt20 = pd.DataFrame(A).rolling(20, min_periods=10).mean().values
ret5 = C / np.roll(C, 5, axis=0) - 1
ret10 = C / np.roll(C, 10, axis=0) - 1
ret60 = C / np.roll(C, 60, axis=0) - 1
ret120 = C / np.roll(C, 120, axis=0) - 1
for x in (ret5, ret10, ret60, ret120): x[:5] = np.nan
pos120 = (C - lo120) / np.maximum(hi120 - lo120, 1e-9)
width20 = hi20 / np.maximum(lo20, 1e-9) - 1.0
near_low = (Ll <= lo120 * 1.05).astype(float); near_low[:120] = 0
touches = pd.DataFrame(near_low).rolling(60, min_periods=60).sum().values
vr = vma5 / np.maximum(vma20, 1e-9); vr_long = vma20 / np.maximum(vma120, 1e-9)
listed_age = pd.DataFrame(OK.astype(float)).rolling(120, min_periods=120).sum().values
TRADABLE = (amt20 >= 5e6) & (listed_age >= 119) & OK
log('tradable cells', int(TRADABLE.sum()))

# ---------- 五张图（与股票版同定义）----------
B = {}
B['G1_鱼尾顶_回避'] = ((ret120 >= 0.30) & (pos120 >= 0.90) & (vr >= 1.30) &
                       (ret5 <= 0.02) & (C <= roll(C, 5, 'max', 5) * 0.98))
platform = (ret120 >= 0.20) & (width20 <= 0.12)
B['G2a_平台回踩下沿'] = platform & (C <= lo20 * 1.02)
B['G2b_平台放量突破'] = platform & (C >= hi20 * 0.995) & (vr >= 1.20)
B['G3_低位放量拐点'] = ((pos120 <= 0.20) & (C >= ma20) & (ret5 >= 0.03) &
                        (vr >= 1.30) & (vr_long <= 2.0))
B['G4_下跌反弹_不扎实'] = ((ret60 <= -0.25) & (ret10 >= 0.10) & (C < ma60) & (C < ma120))
B['G5_扎实底_V反转'] = ((ret120 >= 0.10) & (ret120 <= 0.60) & (touches >= 3) &
                        (minlow60 >= lo120 * 0.97) & (C > ma60) & (vr_long <= 2.0))

def cooldown(mat, gap=60):
    out = np.zeros_like(mat, dtype=bool)
    for j in range(N):
        idx = np.flatnonzero(mat[:, j])
        if idx.size == 0: continue
        keep = [idx[0]]; last = idx[0]
        for t in idx[1:]:
            if t - last >= gap: keep.append(t); last = t
        out[keep, j] = True
    return out
for k in B:
    B[k] = cooldown(np.nan_to_num(B[k], nan=0.0).astype(bool) & TRADABLE)
    B[k][:150] = False
    log('shape', k, 'events', int(B[k].sum()))

# ---------- 评价 ----------
SAMPLE = list(range(150, T - 61, 5))
IS_END = int(np.where(years == 2022)[0][0])
def bootstrap_ci(vals, nboot=1000, seed=7):
    a = np.asarray(vals, float)
    if a.size < 5: return [None, None]
    rng = np.random.default_rng(seed)
    means = np.array([a[rng.integers(0, a.size, a.size)].mean() for _ in range(nboot)])
    return [round(float(x), 5) for x in np.percentile(means, [2.5, 97.5])]

def evaluate(name, mask, H, EX, AB):
    per_day = []; yr_top = {}; yr_n = {}; day_of = {}
    for t in SAMPLE:
        mkt = TRADABLE[t] & np.isfinite(EX[t])
        if mkt.sum() < 5: continue
        idx = np.flatnonzero(mask[t] & mkt)
        if idx.size < 1: continue
        # 安慰剂：全 ETF 等权（= EX 的当日均值，噪声低于小池抽样）
        allidx = np.flatnonzero(mkt)
        tv_ex = float(EX[t, idx].mean()); rv_ex = float(EX[t, allidx].mean())
        day_of[t] = (tv_ex, rv_ex)
        per_day.append((t, tv_ex - rv_ex, float(AB[t, idx].mean()),
                        float((AB[t, idx] > 0).mean()), int(idx.size), int(allidx.size)))
        yr = int(years[t])
        yr_top[yr] = yr_top.get(yr, 0.0) + tv_ex; yr_rnd = None
        yr_n[yr] = yr_n.get(yr, 0) + 1
        _rnd = yr_rnd  # 占位，下方用独立字典
    if not per_day: return None
    # 重算逐年（上循环内未保存 rnd，这里补）
    yr_rnd = {}
    for t in SAMPLE:
        if t not in day_of: continue
        y = int(years[t]); yr_rnd[y] = yr_rnd.get(y, 0.0) + day_of[t][1]
    edges = np.array([x[1] for x in per_day])
    def seg(fn):
        v = np.array([x[1] for x in per_day if fn(x[0])])
        return {'edge_bp': round(float(v.mean()) * 10000, 1) if v.size else None,
                'win_day_rate': round(float((v > 0).mean()), 3) if v.size else None,
                'n_days': int(v.size)}
    return {
        'H': H, 'events': int(mask.sum()),
        'avg_cells_per_day': round(float(np.mean([x[4] for x in per_day])), 2),
        'avg_universe_per_day': round(float(np.mean([x[5] for x in per_day])), 2),
        'mean_ret': round(float(np.mean([x[2] for x in per_day])), 4),
        'win_rate': round(float(np.mean([x[3] for x in per_day])), 4),
        'edge_bp': round(float(edges.mean()) * 10000, 1),
        'ci95_bp': [None if x is None else round(x * 10000, 1) for x in bootstrap_ci(edges)],
        'all': seg(lambda t: True), 'is': seg(lambda t: t < IS_END), 'oos': seg(lambda t: t >= IS_END),
        'by_year_edge_bp': {str(y): round((yr_top[y] / yr_n[y] - yr_rnd[y] / yr_n[y]) * 10000, 1)
                            for y in sorted(yr_n)},
        'edge_after_20bp': round((edges.mean() - 0.004) * 10000, 1),
        'edge_after_50bp': round((edges.mean() - 0.010) * 10000, 1),
        '_day': day_of,
    }

results = {}
for name, mask in B.items():
    mainH = 20 if ('G1' in name or 'G4' in name) else 60
    r20 = evaluate(name, mask, 20, EX20, AB20)
    r60 = evaluate(name, mask, 60, EX60, AB60)
    results[name] = {'main_H': mainH, 'H20': r20, 'H60': r60}
    log(name, 'mainH', mainH,
        'edge20', r20['edge_bp'] if r20 else None, 'edge60', r60['edge_bp'] if r60 else None,
        'OOS20', r20['oos']['edge_bp'] if r20 else None, 'OOS60', r60['oos']['edge_bp'] if r60 else None)

def paired_gap(h):
    ra = results['G5_扎实底_V反转']['H%d' % h]
    rb = results['G4_下跌反弹_不扎实']['H%d' % h]
    if not ra or not rb: return None
    a = ra['_day']; b = rb['_day']
    common = sorted(set(a) & set(b))
    if not common: return None
    gaps = np.array([(a[t][0] - a[t][1]) - (b[t][0] - b[t][1]) for t in common])
    return {'n_days': len(common), 'gap_bp': round(float(gaps.mean()) * 10000, 1),
            'ci95_bp': [round(x * 10000, 1) for x in bootstrap_ci(gaps, seed=17)]}
gap = {'H20': paired_gap(20), 'H60': paired_gap(60)}
for v in results.values():
    for h in ('H20', 'H60'):
        if v[h]: v[h].pop('_day', None)

out = {
    'meta': {
        'generated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'start': str(dates[0].date()), 'end': str(dates[-1].date()),
        'T': T, 'N': N, 'is_end': str(dates[IS_END].date()), 'sample_step': 5,
        'universe': '48 只 ETF（index_etf/etf_hfq_*.csv，后复权/各自内部一致）',
        'note': '与股票版同形态定义、同 t+1/H=20,60/冷却60日/IS-OOS 2022 分界；'
                '流动性门槛降至 500 万（ETF 成交额中位数 156 万）；'
                '安慰剂为「当日全部可交易 ETF 等权」（池子仅 48 只，抽样噪声过大）。',
    },
    'definitions': json.load(open(os.path.join(DIR, 'huabo_five_shapes_result.json'), encoding='utf-8'))['definitions'],
    'results': results, 'g5_vs_g4': gap,
}
json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
log('SAVED', OUT)
