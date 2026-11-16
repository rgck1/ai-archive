# -*- coding: utf-8 -*-
"""
花臂博士「5 张图」形态体系 · 量化近似回测（2026-11-16）

来源：投资工作台「博主情报」→ 花博（花臂博士）ASR 口播稿，视频：
  7708707422357032207 / 7707237226137734434 / 7703516159081041171 /
  7704246730937634102 / 7706118663316753706 / 7699461634275691830
口播里给出了五类图形的文字特征与战法，但原图画在视频画面里、直链已不可取，
因此本脚本检验的是【口播文字可识别特征】的量化近似，不是课程原图的逐像素复刻。

口径铁律：后复权价 / t 日收盘信号 → t+1 买入 → 持有 20、60 交易日 /
          含退市股 / 数组强制 copy / 全A等权基准 / 同期全市场随机30只安慰剂 /
          样本内(2018-2021) + 样本外(2022-2026) / 同股 60 日冷却 /
          双边成本 20bp、50bp 敏感性。
"""
import pickle, json, warnings, datetime
import numpy as np
import pandas as pd
warnings.filterwarnings('ignore'); np.seterr(all='ignore')

PANEL = r'D:\我的工作台\02.输出区\panel_v3.pkl'
OUT = r'D:\我的工作台\02.输出区\huabo_five_shapes_result.json'
def log(*a): print('[HUABO]', *a, flush=True)

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

# ---------- 基准 ----------
with np.errstate(all='ignore'):
    DAILY = C[1:] / C[:-1] - 1.0
DAILY[~OK[1:]] = np.nan
bd = np.nanmean(DAILY, axis=1)
bd = np.where(np.isfinite(bd), bd, 0.0)
BENCH = np.concatenate([[1.0], np.cumprod(1.0 + bd)])

def roll(x, w, fn, minp):
    return getattr(pd.DataFrame(x).rolling(w, min_periods=minp), fn)().values

def forward(H):
    """t 日信号 -> t+1 买入 -> 持有 H 日，返回 (超额, 绝对收益)"""
    F = np.full((T, N), np.nan)
    BF = np.full(T, np.nan)
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

EX20, AB20 = forward(20)
EX60, AB60 = forward(60)
log('forward built H=20/60')

# ---------- 特征（全部 t 日收盘可见）----------
log('features')
ma20 = roll(C, 20, 'mean', 15)
ma60 = roll(C, 60, 'mean', 40)
ma120 = roll(C, 120, 'mean', 80)
hi20, lo20 = roll(Hh, 20, 'max', 15), roll(Ll, 20, 'min', 15)
hi120, lo120 = roll(Hh, 120, 'max', 80), roll(Ll, 120, 'min', 80)
minlow60 = roll(Ll, 60, 'min', 40)
vma5 = pd.DataFrame(V).rolling(5, min_periods=3).mean().values
vma20 = pd.DataFrame(V).rolling(20, min_periods=10).mean().values
vma120 = pd.DataFrame(V).rolling(120, min_periods=60).mean().values
amt20 = pd.DataFrame(A).rolling(20, min_periods=10).mean().values
ret5  = C / np.roll(C, 5, axis=0) - 1
ret10 = C / np.roll(C, 10, axis=0) - 1
ret60 = C / np.roll(C, 60, axis=0) - 1
ret120 = C / np.roll(C, 120, axis=0) - 1
for x in (ret5, ret10, ret60, ret120):
    x[:5] = np.nan
pos120 = (C - lo120) / np.maximum(hi120 - lo120, 1e-9)
width20 = hi20 / np.maximum(lo20, 1e-9) - 1.0
# 120 日低点附近的“踩脚”天数（近 60 日）
near_low = (Ll <= lo120 * 1.05).astype(float)
near_low[:120] = 0
touches = pd.DataFrame(near_low).rolling(60, min_periods=60).sum().values
vr = vma5 / np.maximum(vma20, 1e-9)
vr_long = vma20 / np.maximum(vma120, 1e-9)

listed_age = pd.DataFrame(LISTED.astype(float)).rolling(120, min_periods=120).sum().values
TRADABLE = (amt20 >= 5e7) & (listed_age >= 119) & OK
log('tradable cells', int(TRADABLE.sum()))

# ---------- 五张图的量化近似 ----------
B = {}
# 图形一 · 鱼尾顶：大涨后贴近高点、放量滞涨、从高点回落 → 回避/卖出
B['G1_鱼尾顶_回避'] = ((ret120 >= 0.30) & (pos120 >= 0.90) & (vr >= 1.30) &
                       (ret5 <= 0.02) & (C <= roll(C, 5, 'max', 5) * 0.98))
# 图形二 · 高位平台：大涨后 20 日振幅≤12%，资金扎实在高位横盘
platform = (ret120 >= 0.20) & (width20 <= 0.12)
B['G2a_平台回踩下沿'] = platform & (C <= lo20 * 1.02)               # “小一”：低成本赌突破
B['G2b_平台放量突破'] = platform & (C >= hi20 * 0.995) & (vr >= 1.20) # “小二”：确认突破
# 图形三 · 价值拐点：长期低位 + 放量站上MA20（口播称“大价值战法全是拐点”）
B['G3_低位放量拐点'] = ((pos120 <= 0.20) & (C >= ma20) & (ret5 >= 0.03) &
                        (vr >= 1.30) & (vr_long <= 2.0))
# 图形四 · 下跌反弹（底部不扎实）：深跌后急反弹但仍在长期均线下方 → 快进快出
B['G4_下跌反弹_不扎实'] = ((ret60 <= -0.25) & (ret10 >= 0.10) &
                            (C < ma60) & (C < ma120))
# 图形五 · 扎实底：从低点反弹、多次回踩不破、站上MA60（市场已验证）
B['G5_扎实底_V反转'] = ((ret120 >= 0.10) & (ret120 <= 0.60) &
                        (touches >= 3) & (minlow60 >= lo120 * 0.97) &
                        (C > ma60) & (vr_long <= 2.0))

# 冷却：同一只股票同一形态 60 交易日只记首次，避免事件重叠虚增
def cooldown(mat, gap=60):
    out = np.zeros_like(mat, dtype=bool)
    for j in range(N):
        idx = np.flatnonzero(mat[:, j])
        if idx.size == 0:
            continue
        keep = [idx[0]]; last = idx[0]
        for t in idx[1:]:
            if t - last >= gap:
                keep.append(t); last = t
        out[keep, j] = True
    return out

for k in B:
    raw = np.nan_to_num(B[k], nan=0.0).astype(bool)
    B[k] = cooldown(raw & TRADABLE)
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

def evaluate(name, mask, H, EX, AB, min_cells=5):
    ex = EX if H == 60 else EX20 if H == 20 else EX
    ab = AB if H == 60 else AB20 if H == 20 else AB
    per_day = []; yr_top = {}; yr_n = {}; yr_rnd = {}
    day_of = {}
    for t in SAMPLE:
        mkt = np.isfinite(ex[t])
        if mkt.sum() < 100: continue
        idx = np.flatnonzero(mask[t] & mkt)
        if idx.size < min_cells: continue
        rng = np.random.default_rng(7 + t)
        pick = idx[rng.choice(idx.size, min(30, idx.size), replace=False)]
        allidx = np.flatnonzero(mkt)
        rndpick = allidx[rng.choice(allidx.size, 30, replace=False)]
        tv_ex = float(ex[t, pick].mean()); rv_ex = float(ex[t, rndpick].mean())
        day_of[t] = (tv_ex, rv_ex)
        per_day.append((t, tv_ex - rv_ex, float(ab[t, pick].mean()),
                        float((ab[t, pick] > 0).mean()), int(idx.size)))
        yr = int(years[t])
        yr_top[yr] = yr_top.get(yr, 0.0) + tv_ex
        yr_rnd[yr] = yr_rnd.get(yr, 0.0) + rv_ex
        yr_n[yr] = yr_n.get(yr, 0) + 1
    if not per_day: return None
    edges = np.array([x[1] for x in per_day])
    def seg(tags):
        v = np.array([x[1] for x in per_day if tags(x[0])])
        return {'edge_bp': round(float(v.mean()) * 10000, 1) if v.size else None,
                'win_day_rate': round(float((v > 0).mean()), 3) if v.size else None,
                'n_days': int(v.size)}
    rets = np.array([x[2] for x in per_day])
    wins = np.array([x[3] for x in per_day])
    ncell = int(np.mean([x[4] for x in per_day]))
    return {
        'H': H, 'events': int(mask.sum()), 'avg_cells_per_day': round(float(ncell), 1),
        'mean_ret': round(float(rets.mean()), 4),
        'win_rate': round(float(wins.mean()), 4),
        'edge_bp': round(float(edges.mean()) * 10000, 1),
        'ci95_bp': [round(x * 10000, 1) for x in bootstrap_ci(edges)],
        'all': seg(lambda t: True),
        'is': seg(lambda t: t < IS_END),
        'oos': seg(lambda t: t >= IS_END),
        'by_year_edge_bp': {str(y): round((yr_top[y] / yr_n[y] - yr_rnd[y] / yr_n[y]) * 10000, 1)
                            for y in sorted(yr_n)},
        'edge_after_20bp': round((edges.mean() - 0.004) * 10000, 1),
        'edge_after_50bp': round((edges.mean() - 0.010) * 10000, 1),
        '_day': day_of,
    }

results = {}
for name, mask in B.items():
    mainH = 20 if 'G1' in name or 'G4' in name else 60
    mc = 1 if 'G1' in name else 5   # 鱼尾顶事件稀疏（约200个），按事件级逐日对比
    r20 = evaluate(name, mask, 20, EX20, AB20, min_cells=mc)
    r60 = evaluate(name, mask, 60, EX60, AB60, min_cells=mc)
    results[name] = {'main_H': mainH, 'H20': r20, 'H60': r60}
    log(name, 'mainH', mainH,
        'edge20', r20['edge_bp'] if r20 else None,
        'edge60', r60['edge_bp'] if r60 else None,
        'OOS20', r20['oos']['edge_bp'] if r20 else None,
        'OOS60', r60['oos']['edge_bp'] if r60 else None)

# 核心主张检验：图形五是否真的优于图形四（抄底只抄图形五）
def paired_gap(h):
    a = results['G5_扎实底_V反转']['H%d' % h]['_day']
    b = results['G4_下跌反弹_不扎实']['H%d' % h]['_day']
    common = sorted(set(a) & set(b))
    gaps = np.array([(a[t][0] - a[t][1]) - (b[t][0] - b[t][1]) for t in common])
    return {'n_days': len(common), 'gap_bp': round(float(gaps.mean()) * 10000, 1),
            'ci95_bp': [round(x * 10000, 1) for x in bootstrap_ci(gaps, seed=17)],
            'win_rate': round(float((gaps > 0).mean()), 3),
            'by_year': {str(y): round(float(np.mean([
                (a[t][0] - a[t][1]) - (b[t][0] - b[t][1]) for t in common if years[t] == y])) * 10000, 1)
                for y in sorted(set(years[t] for t in common))}}

gap = {'H20': paired_gap(20), 'H60': paired_gap(60)}
log('G5-G4 gap H20', gap['H20'], 'H60', gap['H60'])

# 去掉内部调试字段
for v in results.values():
    for h in ('H20', 'H60'):
        if v[h]: v[h].pop('_day', None)

out = {
    'meta': {
        'generated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'start': str(dates[0].date()), 'end': str(dates[-1].date()),
        'T': T, 'N': N, 'is_end': str(dates[IS_END].date()), 'sample_step': 5,
        'source': '投资工作台博主情报·花博(花臂博士) ASR 口播稿',
        'note': '原图在视频画面里不可得；本回测检验口播文字可识别特征的量化近似，非原图逐像素复刻。'
                't日收盘信号→t+1买入→持有H日；后复权；含退市；全A等权基准；同期全市场随机30只安慰剂；'
                '同股同形态60日冷却；成交≥5000万、上市≥120日。',
        'main_H': {'G1': 20, 'G2': 60, 'G3': 60, 'G4': 20, 'G5': 60},
    },
    'definitions': {
        'G1_鱼尾顶_回避': '120日涨幅≥30% & 位于120日高点90%分位以上 & 5日量/20日量≥1.3 & 近5日涨幅≤2% & 跌破5日高点2%',
        'G2a_平台回踩下沿': '120日涨幅≥20% & 20日振幅≤12% & 收盘≤20日低点×1.02',
        'G2b_平台放量突破': '120日涨幅≥20% & 20日振幅≤12% & 收盘≥20日高点×0.995 & 5日量/20日量≥1.2',
        'G3_低位放量拐点': '120日区间位置≤0.2 & 收盘站上MA20 & 近5日涨幅≥3% & 5日量/20日量≥1.3 & 20日量/120日量≤2.0',
        'G4_下跌反弹_不扎实': '60日跌幅≤-25% & 近10日反弹≥10% & 收盘<MA60且<MA120',
        'G5_扎实底_V反转': '120日涨幅10%~60% & 近60日回踩120日低点附近≥3天 & 近60日最低≥120日低点×0.97 & 收盘>MA60 & 20日量/120日量≤2.0',
    },
    'results': results,
    'g5_vs_g4': gap,
}
json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
log('SAVED', OUT)
