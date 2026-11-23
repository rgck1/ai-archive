# -*- coding: utf-8 -*-
"""
DSR（Deflated Sharpe Ratio, Bailey & López de Prado 2014）+ PBO/CSCV（Bailey et al.）
零 scipy：正态 CDF / 逆 CDF 用标准库 statistics.NormalDist。
输入：D:/我的工作台/02.输出区/daily_sequences_2026-11-23.npz
输出：控制台打印 + JSON 结果落盘（供报告引用）
"""
import json
import math
import numpy as np
import pandas as pd
from statistics import NormalDist
from itertools import combinations

NPZ = r'D:/我的工作台/02.输出区/daily_sequences_2026-11-23.npz'
OUT_JSON = r'D:/我的工作台/02.输出区/_dsr_pbo_result_2026-11-23.json'

ND = NormalDist()

# ---------------- 数据载入 ----------------
d = np.load(NPZ)
dates_all = d['_dates']            # (2124,) 字符串
n_dates = len(dates_all)

CHAMPS = ['magic', 'cash', 'combo']
CALIBERS = ['main', 'pit', 'timestamppit']

def load_series(key):
    """返回 (date_index int array, rets float array)"""
    arr = d[key]
    return arr[:, 0].astype(int), arr[:, 1].astype(float)

def to_aligned(key):
    """对齐到全局 _dates，缺失日填 0，返回长度 2124 的日收益数组"""
    idx, rets = load_series(key)
    out = np.zeros(n_dates)
    out[idx] = rets
    return out

# ---------------- 任务一：DSR ----------------
def ann_sharpe(rets):
    """年化夏普：日均值/日std × sqrt(252)，与 metrics_mtm 口径一致"""
    mu = rets.mean()
    sd = rets.std(ddof=1)
    return mu / sd * math.sqrt(252)

def skew_kurt(rets):
    """偏度与峰度（非超额，正态=3，与 DSR 公式一致）。手工矩计算。"""
    mu, n = rets.mean(), len(rets)
    x = rets - mu
    m2 = np.mean(x ** 2)
    m3 = np.mean(x ** 3)
    m4 = np.mean(x ** 4)
    skew = m3 / m2 ** 1.5
    kurt = m4 / m2 ** 2          # 非超额峰度，正态=3
    return skew, kurt

def psr(sr, sr0, n, skew, kurt):
    """PSR = Φ( (SR-SR0)*sqrt(n-1) / sqrt(1 - skew*SR + (kurt-1)/4*SR^2) )"""
    denom = 1 - skew * sr + (kurt - 1) / 4 * sr ** 2
    if denom <= 0:
        return 1.0   # 分母非正时 PSR 饱和（实际未出现），记录口径
    z = (sr - sr0) * math.sqrt(n - 1) / math.sqrt(denom)
    return ND.cdf(z)

def sr0_expected_max(v_sr, n_trials):
    """SR0 = sqrt(V[SR]) × [(1-γ)Φ⁻¹(1-1/N) + γΦ⁻¹(1-1/(N·e))]，γ≈0.5772"""
    if n_trials <= 1:
        return 0.0
    g = 0.5772156649
    e = math.e
    part = (1 - g) * ND.inv_cdf(1 - 1.0 / n_trials) + g * ND.inv_cdf(1 - 1.0 / (n_trials * e))
    return math.sqrt(v_sr) * part

# 9 条冠军 full 序列统计
rows = []
sr_list = []
for sig in CHAMPS:
    for cal in CALIBERS:
        key = f'{sig}__{cal}'
        idx, rets = load_series(key)
        r = pd.Series(rets)
        n = len(rets)
        sr = ann_sharpe(rets)
        # DSR 公式里的 SR 需是「每期（日）频率」的 SR。年化 SR / sqrt(252) 折回日频。
        sr_daily = sr / math.sqrt(252)
        skew, kurt = skew_kurt(rets)
        sr_list.append(sr)
        rows.append(dict(key=key, n_days=n, sr_ann=sr, sr_daily=sr_daily,
                         skew=skew, kurt=kurt))

sr_arr = np.array(sr_list)
v_sr_daily = np.var(sr_arr / math.sqrt(252), ddof=1)   # 9 条主序列日频 SR 的方差（ddof=1）
v_sr_ann = np.var(sr_arr, ddof=1)

N_TRIALS = [115, 106, 90]
dsr_table = []
for row in rows:
    rec = dict(key=row['key'], n_days=row['n_days'],
               sr_ann=row['sr_ann'], skew=row['skew'], kurt=row['kurt'])
    for N in N_TRIALS:
        sr0_daily = sr0_expected_max(v_sr_daily, N)
        rec[f'psr_N{N}'] = psr(row['sr_daily'], sr0_daily, row['n_days'],
                               row['skew'], row['kurt'])
        rec[f'sr0_daily_N{N}'] = sr0_daily
    dsr_table.append(rec)

# ---------------- 任务二：PBO / CSCV ----------------
TOPN_KEYS = [f'topn{t}__{m}__{s}' for t in (5, 10, 15, 20, 30)
             for m in ('main', 'pit') for s in CHAMPS]   # 30 条，档位外层

def cscv_pbo(matrix, S=16, block_strata=None):
    """
    matrix: (T, k) 日收益矩阵，已对齐填 0
    S: 块数；返回 (pbo, lambdas)
    块切分：前 T % S 个块各多一行（等宽近似）
    block_strata: 可选，行→块归属数组，用于分层子集 PBO（此处未用）
    """
    T, k = matrix.shape
    base = T // S
    rem = T % S
    bounds = []
    start = 0
    for i in range(S):
        w = base + (1 if i < rem else 0)
        bounds.append((start, start + w))
        start += w
    assert bounds[-1][1] == T

    lambdas = []
    for train_blocks in combinations(range(S), S // 2):
        train_mask = np.zeros(S, bool)
        train_mask[list(train_blocks)] = True
        train_rows = np.concatenate([np.arange(bounds[b][0], bounds[b][1])
                                     for b in range(S) if train_mask[b]])
        test_rows = np.concatenate([np.arange(bounds[b][0], bounds[b][1])
                                    for b in range(S) if not train_mask[b]])
        # 训练段内全期倍数（累计收益）排名，选样本内最优（最高倍数）
        train_mult = np.prod(1 + matrix[train_rows, :], axis=0)
        best = int(np.argmax(train_mult))
        # 该策略在测试段的倍数排名 → 相对排名 λ（Bailey et al. 标准方向）
        # λ = 测试段倍数严格高于该策略的列数 / (k-1)：
        #   λ = 0  表示 IS-best 样本外全场最高（最好）
        #   λ → 1  表示 IS-best 样本外全场最低（最差）
        #   λ > 0.5 ⇔ 样本外低于中位
        # PBO = P(λ > 0.5) = IS-best 样本外低于中位的比例（标准定义）
        test_mult = np.prod(1 + matrix[test_rows, :], axis=0)
        n_above = int((test_mult > test_mult[best]).sum())      # 严格好于 best 的列数
        lam = n_above / (k - 1)                                  # 0=样本外最高，1=样本外最低
        lambdas.append(lam)

    lambdas = np.array(lambdas)
    pbo = float(np.mean(lambdas > 0.5))
    return pbo, lambdas, bounds

# 30 列主口径
mat30 = np.column_stack([to_aligned(k) for k in TOPN_KEYS])
pbo30, lam30, bounds16 = cscv_pbo(mat30, S=16)

# 39 列敏感性
ALL39 = TOPN_KEYS + [f'{s}__{c}' for s in CHAMPS for c in CALIBERS]
mat39 = np.column_stack([to_aligned(k) for k in ALL39])
pbo39, lam39, _ = cscv_pbo(mat39, S=16)

# S=10 对照
pbo30_s10, lam30_s10, _ = cscv_pbo(mat30, S=10)
pbo39_s10, lam39_s10, _ = cscv_pbo(mat39, S=10)

# 3 组此前常规 PASS 的样本外排名分布（在 30 列 CSCV 中）
PASS3 = ['topn15__main__cash', 'topn30__main__combo', 'topn30__pit__combo']
pass3_idx = [TOPN_KEYS.index(k) for k in PASS3]

# 需要每列每测试段的 λ：记录每列在每次划分中的 λ 与是否被选为 IS-best
def cscv_lambda_per_col(matrix, S=16):
    """返回 (is_best_counts, lambda_records)
    is_best_counts: (k,) 每列被选为样本内最优的次数
    lambda_records: list of (best_col, lam_of_best) 每次划分一条
    λ 口径与 cscv_pbo 相同：λ = 低于该列测试段倍数的列数 / (k-1)，越大越差
    """
    T, k = matrix.shape
    base, rem = T // S, T % S
    bounds = []
    start = 0
    for i in range(S):
        w = base + (1 if i < rem else 0)
        bounds.append((start, start + w))
        start += w
    is_best_counts = np.zeros(k, dtype=int)
    lam_records = []          # 每次划分: (best_col, lam_best)
    lam_all = np.zeros((math.comb(S, S // 2), k))   # 每次划分每列的 λ
    for j, train_blocks in enumerate(combinations(range(S), S // 2)):
        train_mask = np.zeros(S, bool)
        train_mask[list(train_blocks)] = True
        train_rows = np.concatenate([np.arange(bounds[b][0], bounds[b][1])
                                     for b in range(S) if train_mask[b]])
        test_rows = np.concatenate([np.arange(bounds[b][0], bounds[b][1])
                                    for b in range(S) if not train_mask[b]])
        train_mult = np.prod(1 + matrix[train_rows, :], axis=0)
        best = int(np.argmax(train_mult))
        is_best_counts[best] += 1
        test_mult = np.prod(1 + matrix[test_rows, :], axis=0)
        # λ：测试段严格高于该列的列数占比，越大越差；与 cscv_pbo 同方向
        lam_all[j] = (test_mult[None, :] > test_mult[:, None]).sum(axis=0) / (k - 1)
        lam_records.append((best, lam_all[j, best]))
    return is_best_counts, lam_records, lam_all

# 3 组此前常规 PASS：在每次 CSCV 划分中的样本外 λ 分布（30 列）
is_best30, lam_rec30, lam_all30 = cscv_lambda_per_col(mat30, S=16)
PASS3 = ['topn15__main__cash', 'topn30__main__combo', 'topn30__pit__combo']
pass3_stats = {}
for name in PASS3:
    c = TOPN_KEYS.index(name)
    l = lam_all30[:, c]
    pass3_stats[name] = dict(
        mean=float(l.mean()), median=float(np.median(l)),
        p_above_median=float(np.mean(l > 0.5)),      # 样本外高于中位的比例
        p_lt01=float(np.mean(l < 0.1)),              # 样本外进入前 10% 的比例
        is_best_times=int(is_best30[c]),
    )

top_sel = sorted(range(len(TOPN_KEYS)), key=lambda i: -is_best30[i])[:5]
top_sel_list = [dict(key=TOPN_KEYS[i], times=int(is_best30[i])) for i in top_sel]

# ---------------- 打印与落盘 ----------------
print('=== DSR ===')
print(f'V[SR] 日频 = {v_sr_daily:.8f}（年频 {v_sr_ann:.6f}）')
hdr = f"{'key':28s} {'n':>5s} {'SR_ann':>7s} {'skew':>7s} {'kurt':>7s} {'DSR@115':>8s} {'DSR@106':>8s} {'DSR@90':>8s}"
print(hdr)
for rec in dsr_table:
    print(f"{rec['key']:28s} {rec['n_days']:5d} {rec['sr_ann']:7.4f} {rec['skew']:7.3f} {rec['kurt']:7.3f} "
          f"{rec['psr_N115']:8.4f} {rec['psr_N106']:8.4f} {rec['psr_N90']:8.4f}")

print()
print('=== PBO / CSCV（λ=样本外高于该列的占比，越大越差；PBO=P(λ>0.5)）===')
print(f'30列 S=16: PBO = {pbo30:.4f}  (组合数 {len(lam30)})')
print(f'39列 S=16: PBO = {pbo39:.4f}')
print(f'30列 S=10: PBO = {pbo30_s10:.4f}')
print(f'39列 S=10: PBO = {pbo39_s10:.4f}')

print(f'λ 分布 30列 S=16 (IS-best): mean={lam30.mean():.3f} median={np.median(lam30):.3f} '
      f'p25={np.percentile(lam30,25):.3f} p75={np.percentile(lam30,75):.3f}')

print()
print('=== 3 组常规 PASS 的 CSCV 样本外 λ 分布（30列 S=16，λ 越小越好）===')
for name, st in pass3_stats.items():
    print(f"{name}: λ均值={st['mean']:.3f} 中位={st['median']:.3f} "
          f"样本外高于中位比例={st['p_above_median']:.4f} 进入前10%比例={st['p_lt01']:.4f} "
          f"被选IS-best次数={st['is_best_times']}")
print('被选为 IS-best 最多的 5 列:', [(x['key'], x['times']) for x in top_sel_list])

result = dict(
    v_sr_daily=v_sr_daily, v_sr_ann=v_sr_ann,
    dsr_table=dsr_table,
    pbo=dict(col30_S16=pbo30, col39_S16=pbo39, col30_S10=pbo30_s10, col39_S10=pbo39_s10,
             n_combos=len(lam30)),
    lambda_stats_30_S16=dict(mean=float(lam30.mean()), median=float(np.median(lam30)),
                             p25=float(np.percentile(lam30, 25)),
                             p75=float(np.percentile(lam30, 75))),
    pass3_lambda_30_S16=pass3_stats,
    top_selected_cols_30_S16=top_sel_list,
    lambda_definition='lam = (# test columns strictly above the column) / (k-1); larger = worse OOS; PBO = P(lam>0.5 of IS-best)',
)
with open(OUT_JSON, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=1, default=float)
print('saved:', OUT_JSON)
