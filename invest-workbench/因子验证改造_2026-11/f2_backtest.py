# -*- coding: utf-8 -*-
"""F2 红利 90 周均线偏离率回测（P1-A3）
口径：逐日 mark-to-market，年化 √252，禁用平摊。
数据源：etf_hfq_*.csv（39 个腾讯 qfq 前复权 + 9 个东财真 hfq，偏离率数学等价）。
用法："C:/Users/RG/miniconda3/python.exe" f2_backtest.py
"""
import os, sys, json, time
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

BASE = r'D:\我的工作台\02.输出区'
DATA = os.path.join(BASE, '补充数据', 'index_etf')
OUT_JSON = os.path.join(BASE, 'F2_实跑结果_2026-11-22.json')

# ---- 口径常数 ----
TRADING_DAYS = 252
WARM_TRADING_DAYS = 694          # 90 周(450) + 1 年缓冲(244)
SIGNAL_CUTOFF = '2022-12-31'
OOS_START = '2023-01-01'
BUY_TH_GRID = [-0.05, -0.04, -0.03, -0.02, -0.01]
SELL_TH_GRID = [0.06, 0.07, 0.08, 0.09, 0.10]
MA_WINDOW_GRID = [60, 90, 120]
BASE_PARAMS = {'buy_th': -0.03, 'sell_th': 0.08, 'ma_window': 90}
BATCH_FRAC = 0.20
MAX_BATCHES = 5
COOLDOWN_WEEKS = 1
FEE_RATE = 0.00025
MIN_FEE = 5.0
SLIPPAGE_BP = 5.0
PLACEBO_N = 100
PRIMARY_SYMBOLS = ['510880', '512890']
BENCHMARK_SYMBOLS = ['510300', '510500', '510050', '159915', '159907']


def load_etf_daily(code, adj='hfq'):
    """读取单只 ETF 复权 CSV。自动处理 BOM。起点取 CSV 首行。"""
    prefix = 'etf_hfq_' if adj == 'hfq' else 'etf_'
    path = os.path.join(DATA, f'{prefix}{code}.csv')
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, encoding='utf-8-sig')
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    return df


def resample_weekly(daily):
    """日线聚合为周线，取每周最后交易日收盘价。只纳入已完成周。"""
    d = daily.set_index('date')
    w = d['close'].resample('W-FRI').last().dropna()
    return w


def compute_dev(weekly_close, ma_window):
    """dev = (close - MA(ma_window)) / MA(ma_window)，min_periods 严格预热。"""
    ma = weekly_close.rolling(window=ma_window, min_periods=ma_window).mean()
    dev = (weekly_close - ma) / ma
    return dev


def gen_weekly_target(dev, buy_th, sell_th):
    """周频目标仓位 [0,1]。cross 穿越触发 + 冷却期。
    买入：dev 下穿 buy_th 且未达最大批次 -> +BATCH_FRAC。
    卖出：dev 上穿 sell_th 且有持仓 -> -BATCH_FRAC。
    """
    target = np.zeros(len(dev))
    pos = 0.0
    batches = 0
    last_trigger_idx = -999
    vals = dev.values
    for i in range(len(vals)):
        if i > 0 and (i - last_trigger_idx) >= COOLDOWN_WEEKS:
            prev, cur = vals[i-1], vals[i]
            if np.isfinite(prev) and np.isfinite(cur):
                if prev > buy_th and cur <= buy_th and batches < MAX_BATCHES:
                    pos = min(1.0, pos + BATCH_FRAC)
                    batches += 1
                    last_trigger_idx = i
                elif prev < sell_th and cur >= sell_th and pos > 0:
                    pos = max(0.0, pos - BATCH_FRAC)
                    batches = max(0, batches - 1)
                    last_trigger_idx = i
        target[i] = pos
    return pd.Series(target, index=dev.index)


def build_daily_position(daily, weekly_target):
    """把周频目标仓位映射到日频。
    周 t 信号在其后首个交易日收盘成交，成交前持仓沿用上一目标。
    返回日频 position 数组（每日收盘后持仓）。
    """
    dates = daily['date'].values
    # 周目标按周结束日索引，映射到每个交易日：取该日所属周及之前最近一个已完成周的 target
    wt = weekly_target.copy()
    wt.index = pd.to_datetime(wt.index)
    # 对每个交易日，找到 <= 该日的最近一个周结束日的 target
    day_target = pd.Series(index=pd.DatetimeIndex(dates), dtype=float)
    idx = wt.index
    pos_vals = wt.values
    for j, dt in enumerate(pd.DatetimeIndex(dates)):
        loc = idx.searchsorted(dt, side='right') - 1
        day_target.iloc[j] = pos_vals[loc] if loc >= 0 else 0.0
    # 成交滞后一周：周线信号在周结束后下一周首日生效。
    # searchsorted 已保证 dt < 周结束日时取上一周 target，天然实现滞后。
    return day_target.values


def mark_to_market(daily, weekly_close, weekly_target, fee_rate=FEE_RATE,
                   min_fee=MIN_FEE, slippage_bp=SLIPPAGE_BP):
    """逐日盯市。信号周线、净值日线。成本按仓位变动在调仓日一次性扣除。
    返回 rets / nav / n_trades / turnover_sum。
    """
    d = daily.reset_index(drop=True)
    dates = d['date'].values
    close = d['close'].values.astype(float)
    volume = d['volume'].values.astype(float) if 'volume' in d else np.zeros(len(d))

    # 日收益率：用复权价逐日比值（qfq/hfq 全局因子约掉）
    daily_ret = np.zeros(len(d))
    daily_ret[1:] = close[1:] / close[:-1] - 1.0
    # 停牌（volume==0）当日收益置 0
    daily_ret[volume == 0] = 0.0

    pos = build_daily_position(d, weekly_target)  # 当日收盘后目标仓位
    rets = np.zeros(len(d))
    n_trades = 0
    turnover_sum = 0.0
    prev_pos = 0.0
    for j in range(len(d)):
        # 当日收益按昨日收盘后持仓（prev_pos）计算
        if j > 0:
            rets[j] = prev_pos * daily_ret[j]
        # 调仓在当日收盘，按 pos[j] 相对 prev_pos 变动扣成本
        delta = abs(pos[j] - prev_pos)
        if delta > 1e-12:
            turnover_sum += delta
            n_trades += 1
            cost = delta * (fee_rate + slippage_bp / 10000.0)
            # 最低 5 元佣金按名义仓位折算：这里按单位净值 1 近似，
            # 分母用初始资金 100000，单笔最低佣金影响见 meta 说明
            min_fee_impact = min_fee / 100000.0
            cost = max(cost, min_fee_impact)
            rets[j] -= cost
        prev_pos = pos[j]
    nav = np.cumprod(1.0 + rets)
    return {'rets': rets, 'nav': nav, 'dates': dates,
            'n_trades': n_trades, 'turnover': turnover_sum}


def metrics(rets):
    """统一 √252 年化。"""
    r = np.asarray(rets, dtype=float)
    r = np.nan_to_num(r, nan=0.0, posinf=0.0, neginf=0.0)
    total = float(np.prod(1.0 + r))
    years = len(r) / TRADING_DAYS
    annual = total ** (1.0 / years) - 1.0 if years > 0 and total > 0 else -1.0
    vol = float(np.std(r, ddof=1) * np.sqrt(TRADING_DAYS)) if len(r) > 1 else 0.0
    sharpe = float(np.mean(r) / np.std(r, ddof=1) * np.sqrt(TRADING_DAYS)) if len(r) > 1 and np.std(r, ddof=1) > 0 else 0.0
    neg = r[r < 0]
    dvol = float(np.std(neg, ddof=1) * np.sqrt(TRADING_DAYS)) if len(neg) > 1 else 0.0
    sortino = float(np.mean(r) / dvol * np.sqrt(TRADING_DAYS)) if dvol > 0 else 0.0
    nav = np.cumprod(1.0 + r)
    peak = np.maximum.accumulate(nav)
    dd = nav / peak - 1.0
    mdd = float(dd.min())
    calmar = float(annual / abs(mdd)) if mdd < 0 else 0.0
    return {'total_multiple': round(total, 4), 'annual': round(annual, 4),
            'mdd': round(mdd, 4), 'vol': round(vol, 4),
            'sharpe': round(sharpe, 4), 'sortino': round(sortino, 4),
            'calmar': round(calmar, 4)}


def buy_and_hold(daily):
    """同标的买入持有基准，逐日盯市，同一成本假设（首日买入一次）。"""
    d = daily.reset_index(drop=True)
    close = d['close'].values.astype(float)
    r = np.zeros(len(d))
    r[1:] = close[1:] / close[:-1] - 1.0
    volume = d['volume'].values.astype(float) if 'volume' in d else np.zeros(len(d))
    r[volume == 0] = 0.0
    r[0] -= max(FEE_RATE + SLIPPAGE_BP / 10000.0, MIN_FEE / 100000.0)
    return metrics(r)


def pct_rank(true_val, dist):
    """真实值在随机分布中的单侧百分位：P(random < true)。"""
    a = np.asarray(dist, dtype=float)
    return float((a < true_val).mean())


def placebo_random(daily, weekly_close, real_target, seed, n=PLACEBO_N):
    """循环移位安慰剂（circular shift）。零假设与真实策略严格匹配：
    真实仓位序列的形状、平均仓位、总暴露、交易次数完全不变，
    只把整条仓位序列相对价格时序循环平移 k 周。k 随机取 1..n_weeks-1。
    这样分位只反映"择时点位是否有信息"，不含仓位结构差异。
    统计量用 total_multiple。返回倍数分布。
    """
    mults = []
    n_weeks = len(weekly_close)
    real = np.asarray(real_target, dtype=float)
    if np.allclose(real, 0):
        res0 = mark_to_market(daily, weekly_close,
                              pd.Series(real, index=weekly_close.index))
        return np.array([np.prod(1.0 + res0['rets'])] * n)

    rng = np.random.default_rng(seed)
    shifts = rng.choice(np.arange(1, n_weeks), size=min(n, n_weeks - 1), replace=False)
    for k in shifts:
        shifted = np.roll(real, int(k))
        wt = pd.Series(shifted, index=weekly_close.index)
        res = mark_to_market(daily, weekly_close, wt)
        mults.append(float(np.prod(1.0 + res['rets'])))
    return np.array(mults)


def run_symbol(code, verbose=False):
    """单标的：75 组参数 × 全样本/样本外 + 安慰剂。"""
    daily = load_etf_daily(code, 'hfq')
    if daily is None:
        return None
    n = len(daily)
    if n <= WARM_TRADING_DAYS:
        return None
    start = str(daily['date'].iloc[0].date())
    weekly_close = resample_weekly(daily)

    # 预热：90 周均线需按 ma_window 严格预热，统一从 WARM_TRADING_DAYS 起算信号
    # 生成全部 ma_window 的 dev
    dev_map = {mw: compute_dev(weekly_close, mw) for mw in MA_WINDOW_GRID}

    oos_mask_daily = daily['date'] >= pd.Timestamp(OOS_START)
    oos_start_idx = int(oos_mask_daily.argmax()) if oos_mask_daily.any() else n

    base_bh_full = buy_and_hold(daily)
    oos_daily = daily.iloc[oos_start_idx:].reset_index(drop=True)
    base_bh_oos = buy_and_hold(oos_daily) if len(oos_daily) > 30 else None

    param_grid = []
    for mw in MA_WINDOW_GRID:
        dev = dev_map[mw]
        for buy_th in BUY_TH_GRID:
            for sell_th in SELL_TH_GRID:
                wt = gen_weekly_target(dev, buy_th, sell_th)
                res = mark_to_market(daily, weekly_close, wt)
                # 截断预热期后再评估
                rets_full = res['rets'][WARM_TRADING_DAYS:]
                full = metrics(rets_full)
                rets_oos = res['rets'][max(WARM_TRADING_DAYS, oos_start_idx):]
                oos = metrics(rets_oos) if len(rets_oos) > 30 else None
                param_grid.append({
                    'buy_th': buy_th, 'sell_th': sell_th, 'ma_window': mw,
                    'full_mult': full['total_multiple'], 'full_sharpe': full['sharpe'],
                    'oos_mult': oos['total_multiple'] if oos else None,
                    'oos_sharpe': oos['sharpe'] if oos else None,
                    'mdd': full['mdd'], 'n_trades': res['n_trades'],
                })

    # 基准参数安慰剂：主统计量 total_multiple
    dev_base = dev_map[BASE_PARAMS['ma_window']]
    wt_base = gen_weekly_target(dev_base, BASE_PARAMS['buy_th'], BASE_PARAMS['sell_th'])
    res_base = mark_to_market(daily, weekly_close, wt_base)
    real_full_mult = float(np.prod(1.0 + res_base['rets'][WARM_TRADING_DAYS:]))
    real_oos_mult = float(np.prod(1.0 + res_base['rets'][max(WARM_TRADING_DAYS, oos_start_idx):]))
    real_full_sharpe = metrics(res_base['rets'][WARM_TRADING_DAYS:])['sharpe']

    pl_full = placebo_random(daily, weekly_close, wt_base,
                             seed=99000 + PLACEBO_N, n=PLACEBO_N)
    # 样本外安慰剂：在样本外周线上重跑，用样本外的真实 target 事件
    weekly_oos = weekly_close[weekly_close.index >= pd.Timestamp(OOS_START)]
    if len(weekly_oos) > 30:
        wt_base_oos = wt_base.reindex(weekly_oos.index).ffill().fillna(0.0)
        pl_oos = placebo_random(oos_daily, weekly_oos, wt_base_oos,
                                seed=99000 + 2 * PLACEBO_N, n=PLACEBO_N)
        oos_pct = pct_rank(real_oos_mult, pl_oos)
    else:
        pl_oos = np.array([])
        oos_pct = None

    full_pct = pct_rank(real_full_mult, pl_full)

    frac_better = sum(1 for p in param_grid
                      if p['oos_mult'] is not None and base_bh_oos is not None
                      and p['oos_mult'] > base_bh_oos['total_multiple']) / len(param_grid)
    frac_pos = sum(1 for p in param_grid
                   if p['oos_mult'] is not None and p['oos_mult'] > 1.0) / len(param_grid)

    return {
        'code': code, 'start': start, 'n_days': n,
        'signal_date': str(weekly_close.index[WARM_TRADING_DAYS].date()) if len(weekly_close) > WARM_TRADING_DAYS else None,
        'base_params': BASE_PARAMS,
        'base_full': metrics(res_base['rets'][WARM_TRADING_DAYS:]),
        'base_oos': metrics(res_base['rets'][max(WARM_TRADING_DAYS, oos_start_idx):]) if len(res_base['rets']) > max(WARM_TRADING_DAYS, oos_start_idx) else None,
        'buy_hold_full': base_bh_full, 'buy_hold_oos': base_bh_oos,
        'placebo': {
            'n': PLACEBO_N,
            'total_multiple_pct': round(full_pct, 4),
            'oos_multiple_pct': round(oos_pct, 4) if oos_pct is not None else None,
            'real_full_mult': round(real_full_mult, 4),
            'real_oos_mult': round(real_oos_mult, 4),
            'real_full_sharpe': round(real_full_sharpe, 4),
            'statistic': 'total_multiple',
        },
        'param_grid': param_grid,
        'param_robust': {
            'frac_better_than_bh': round(frac_better, 4),
            'frac_oos_positive': round(frac_pos, 4),
        },
    }


def gate_check(r):
    """单标的硬门槛。主统计量 total_multiple_pct，Bonferroni 校正后门槛 0.983。"""
    if r is None:
        return None
    bo = r['buy_hold_oos']
    ro = r['base_oos']
    cond_oos = bool(ro and bo and ro['total_multiple'] >= bo['total_multiple'])
    cond_mdd = bool(ro and bo and ro['mdd'] > bo['mdd'])  # mdd 为负，越大越好
    cond_pl = r['placebo']['total_multiple_pct'] >= 0.90
    cond_pl_strict = r['placebo']['total_multiple_pct'] >= 0.983  # Bonferroni
    cond_robust = r['param_robust']['frac_better_than_bh'] >= 0.60
    return {
        'oos_not_worse_than_bh': cond_oos,
        'mdd_smaller_than_bh': cond_mdd,
        'placebo_pct_ge_090': cond_pl,
        'placebo_pct_ge_0983_bonferroni': cond_pl_strict,
        'param_robust_ge_060': cond_robust,
        'result': 'PASS' if (cond_oos and cond_mdd and cond_pl and cond_robust) else 'FAIL',
    }


def main():
    t0 = time.time()
    # 过筛 27 只
    passed = []
    for f in sorted(__import__('glob').glob(os.path.join(DATA, 'etf_hfq_*.csv'))):
        code = os.path.basename(f).replace('etf_hfq_', '').replace('.csv', '')
        d = pd.read_csv(f, encoding='utf-8-sig', usecols=['date'])
        if len(d) > WARM_TRADING_DAYS:
            sig = str(d['date'].iloc[WARM_TRADING_DAYS])[:10]
            if sig <= SIGNAL_CUTOFF:
                passed.append(code)
    print('过筛标的数:', len(passed), flush=True)
    print('过筛名单:', ','.join(passed), flush=True)

    symbols = passed  # 全部 27 只都跑
    results = {}
    for code in symbols:
        r = run_symbol(code)
        if r is None:
            continue
        r['gate'] = gate_check(r)
        results[code] = r
        print(f"{code} base_full={r['base_full']['total_multiple']} "
              f"base_oos={r['base_oos']['total_multiple'] if r['base_oos'] else None} "
              f"pct={r['placebo']['total_multiple_pct']} gate={r['gate']['result']}",
              flush=True)

    n_pass = sum(1 for r in results.values() if r['gate']['result'] == 'PASS')
    out = {
        'meta': {
            'script': 'f2_backtest',
            'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'oos_start': OOS_START,
            'signal_date_cutoff': SIGNAL_CUTOFF,
            'warm_trading_days': WARM_TRADING_DAYS,
            'start_per_symbol': True,
            'adj': 'mixed_qfq_hfq',
            'adj_note': '39 个腾讯 qfq 前复权（文件名误标 hfq）+ 9 个东财真 hfq；偏离率同序列比值，全局因子约掉，数学等价',
            'data_source': 'etf_hfq_*.csv（独立 CSV 通道）',
            'annualization': TRADING_DAYS,
            'nav_method': 'daily_mark_to_market',
            'fee': {'rate': FEE_RATE, 'min_fee': MIN_FEE, 'stamp_sell': 0.0},
            'slippage_bp': SLIPPAGE_BP,
            'statistic': 'total_multiple',
            'placebo_n': PLACEBO_N,
            'multiple_test_correction': 'Bonferroni 主检验族门槛 pct>=0.983；硬门槛 pct>=0.90',
            'survivorship_bias': '48 只均为当前在交易标的，无退市清盘清单，存在幸存者偏差',
            'min_fee_note': '最低 5 元佣金按初始资金 10 万折算为日收益影响，散户实际资金不同会有偏差',
        },
        'screen': {
            'total_symbols': 48, 'passed_count': len(passed), 'passed_symbols': passed,
            'primary': [c for c in PRIMARY_SYMBOLS if c in results],
            'benchmark': [c for c in BENCHMARK_SYMBOLS if c in results],
        },
        'summary': {'symbols_run': len(results), 'symbols_gate_pass': n_pass},
        'symbols': results,
    }
    json.dump(out, open(OUT_JSON, 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=str)
    print(f'PASS {n_pass}/{len(results)}  elapsed {time.time()-t0:.1f}s', flush=True)
    print('SAVED', OUT_JSON, flush=True)


if __name__ == '__main__':
    main()
