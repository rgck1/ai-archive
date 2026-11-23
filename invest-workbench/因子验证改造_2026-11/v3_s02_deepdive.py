# -*- coding: utf-8 -*-
"""S02 深挖：参数敏感性 + 分年度稳定性 + 对抗式审查（11.2万真实佣金 / 新手仅主板口径）。

S02 = 市值与股价「双低」：rank_sum 合成 mv(偏好小) 与 c(偏好低) 的横截面百分位等权，
topn=10、hold=20（月频）、T+1 收盘成交、仅买沪深主板（300/301 创业板、688 科创、
可转债、ST 一律剔除）。真实成本与 v3_perm.py 完全一致：股票万2.5、最低5元、
卖出印花税0.05%、+0.2bp滑点，另叠加平方根冲击(ETA=0.5)。基准锚点 standard
应复现全期 2.1254 / 样本外(2023起独立重跑) 2.0794。

三块：
 A) 基准锚定 + 分年度分解 + 剔除最好/最差年 + 滚动12月胜率 + 最大回撤区间
    + 逐年 vs 主板小盘/主板等权/沪深300。
 B) 六维参数扫描：双因子权重 / topn / hold / 流动性门槛 / 真实价上限 / 股票池，
    统一评估起点，区分「稳健平台」还是「单参数孤岛」。成本随 topn 动态重算
    （最低5元佣金对小资金分散化是硬约束）。
 C) 安慰剂200次(全期+分年分位) + 单因子归因 + 容量曲线 + ST/退市尾部风险交叉。

不伪造数据，不改动既有引擎，权限掩码与成本回调只在本地注入。凭证不回显。
"""
import os, sys, json, time, math, traceback
from copy import deepcopy
import numpy as np
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

BASE = r'D:\我的工作台\02.输出区'
sys.path.insert(0, BASE)
import xbx_engine as xe
from xbx_engine import Panel, signal, metrics
from v3_perm import board_of, tradeable_mask, roundtrip_bp, impact_bp, FEE, CAP, ETA, MAX_PART

SPEC_FILE = os.path.join(BASE, 'xbx_specs.json')
OUT = os.path.join(BASE, 'v3_s02_deepdive.json')
OOS_DT = pd.Timestamp('2023-01-01')
COMMON_START = '2018-01-02'
I0 = 60
ADV_SMALL = 36200039.5688159      # 与 v3_perm.liquidity.adv_small_median 一致
SIG_SMALL = 0.02840171623504359   # 与 v3_perm.liquidity.sigma_small_median 一致


def load_s02():
    sp = json.load(open(SPEC_FILE, encoding='utf-8'))['strategies']
    return next(s for s in sp if s['id'] == 'S02')


def cost_of(spec, fee='standard'):
    """动态真实成本：最低佣金随每只金额变化 + 平方根冲击随分散度变化。"""
    topn = int(spec['params']['topn'])
    per = CAP / max(topn, 1)
    real_bp = roundtrip_bp(per, 'stock', FEE[fee])
    imp = impact_bp(CAP, ADV_SMALL, SIG_SMALL, topn)
    return round(real_bp + imp, 3), round(real_bp, 3), round(imp, 3)


def safe_signal(p, spec, t):
    """隔离版 signal：修复 xe.signal 中部分分支把 p.d 列视图就地写坏的别名 bug。
    仅对会返回原始列视图的分支(mv/price/turnover/amount/volatility/limitup...等
    直接 s=p.d[k][t] 或 s=p.roll(k)[t]) 做快照还原；rank_sum(S02)/random/新建数组
    类分支本身安全，直接调用零拷贝。"""
    st = spec.get('signal_type', '')
    # 直接引用 p.d 列或 roll 缓存行、会被 s[...]=nan 就地写坏的分支
    ALIAS_TYPES = {'mv', 'price', 'turnover', 'amount', 'volatility',
                   'ma_ratio', 'new_high', 'limitup_recent', 'limitdown_recent',
                   'amplitude', 'gap', 'intraday', 'lucky_number', 'rsi', 'kdj_j'}
    if st not in ALIAS_TYPES:
        return signal(p, spec, t)          # rank_sum / random / momentum 等安全分支
    keys = ('mv', 'c', 'cn', 'o', 'h', 'l', 'a', 'tr', 'v')
    snap = {k: p.d[k].copy() for k in keys if k in p.d}
    roll_snap = {k: v.copy() for k, v in p._roll.items()}
    try:
        return signal(p, spec, t)
    finally:
        for k, v in snap.items():
            p.d[k] = v
        for k, v in roll_snap.items():
            p._roll[k] = v


def rand_signal(p, spec, t, rng=None):
    """随机选股打分：与真实 signal 的候选域(板块外由 mask 控/流动性/年龄/异常跳变)完全一致。"""
    rng = rng or np.random.default_rng()
    s = np.full(p.N, np.nan)
    adv = p.roll('a', 20, 'mean')[t]
    min_liq = float(spec.get('filters', {}).get('min_avg_amount', 5e7))
    ok = p.valid[t] & p.enough_age[t] & (~p.mv_bad[t]) & np.isfinite(adv)
    if min_liq > 0:
        ok &= (adv >= min_liq) & (p.d['a'][t] >= min_liq * 0.5)
    w = max(int(spec.get('params', {}).get('win', 20)), 20)
    ok &= ~p.has_bad(max(0, t - w), t + 1)
    # 真实价上限（与 apply_filters 的 cn 口径一致）
    mp = spec.get('filters', {}).get('max_price')
    if mp is not None:
        ok &= np.isfinite(p.d['cn'][t]) & (p.d['cn'][t] <= float(mp))
    idx = np.where(ok)[0]
    if len(idx):
        s[idx] = rng.random(len(idx))
    return s


def cs_flex(p, spec, mask, cost_bp, start=COMMON_START, end_i1=None,
            signal_fn=None, rng=None, log_picks=False):
    """截面选股：t 收盘算信号 -> mask 屏蔽无权标的 -> t+1 收盘成交 -> 持有 hold 日。
    signal_fn=None 用真实 xe.signal；传入 rand_signal 则做安慰剂。"""
    hold = int(spec['params'].get('hold', 20))
    topn = int(spec['params'].get('topn', 10))
    asc = bool(spec['params'].get('ascending', False))
    i0 = max(int(np.searchsorted(p.dates, pd.Timestamp(start))), I0) if start else I0
    i1 = end_i1 if end_i1 is not None else p.T - hold - 2
    if i1 <= i0:
        return None
    cost = cost_bp / 10000.0
    c = p.d['c']
    rets = np.zeros(i1 - i0 + 1)
    n_trades = 0
    picks_sum = 0
    picks_log = []
    min_liq = float(spec.get('filters', {}).get('min_avg_amount', 5e7))
    t = i0
    while t + hold + 1 <= i1:
        s = signal_fn(p, spec, t, rng=rng) if signal_fn is not None else safe_signal(p, spec, t)
        ok = np.isfinite(s) & mask
        if ok.sum() < topn:
            t += 1
            continue
        order = (np.argsort(np.where(ok, s, np.inf), kind='stable') if asc
                 else np.argsort(-np.where(ok, s, -np.inf), kind='stable'))
        sel = np.asarray(order[:topn])
        buy_i, sell_i = t + 1, t + 1 + hold
        bp, sp = c[buy_i, sel], c[sell_i, sel]
        good = np.isfinite(bp) & np.isfinite(sp) & (bp > 0)
        good &= p.enough_age[buy_i, sel] & (~p.mv_bad[buy_i, sel])
        if min_liq > 0:
            good &= p.d['a'][buy_i, sel] >= min_liq * 0.5
        good &= ~p.has_bad(buy_i, sell_i + 1)[sel]
        good &= ~p.oneword_limit(buy_i, up=True)[sel]
        good &= ~p.oneword_limit(sell_i, up=False)[sel]
        if log_picks:
            picks_log.append({'date': str(p.dates[t].date()),
                              'raw': [p.codes[int(x)] for x in sel],
                              'good': [p.codes[int(x)] for x in sel[good]],
                              'cn': [round(float(v), 3) if np.isfinite(v) else None
                                     for v in p.d['cn'][buy_i, sel]]})
        if good.sum() == 0:
            t += hold
            continue
        n_trades += 1
        picks_sum += int(good.sum())
        # [MTM 修复 2026-11-22] 逐日盯市替代平摊收益，详见 xbx_engine.cross_section
        held = sel[good]
        seg0, seg1 = t - i0, sell_i - i0
        rc = np.asarray(p.ret_clean, dtype=float)
        for pos in range(seg0 + 2, min(seg1 + 1, len(rets))):
            rr_day = rc[pos + i0, held]
            rr_day = np.where(np.isfinite(rr_day), rr_day, 0.0)
            rr_day = np.clip(rr_day, -0.11, 0.11)
            rets[pos] = float(np.mean(rr_day))
        cost_pos = seg0 + 1
        if 0 <= cost_pos < len(rets):
            rets[cost_pos] -= cost
        t += hold
    return {'rets': rets, 'dates': p.dates[i0:i0 + len(rets)], 'n_trades': n_trades,
            'avg_picks': round(picks_sum / max(n_trades, 1), 2), 'picks_log': picks_log}


def yearly(rets, dates):
    s = pd.Series(np.asarray(rets), index=pd.DatetimeIndex(dates))
    out = {}
    for y, g in s.groupby(s.index.year):
        out[str(y)] = {'ret': round(float((1 + g).prod() - 1), 4), 'days': int(len(g))}
    return out


def oos_slice(rets, dates):
    idx = np.where(pd.DatetimeIndex(dates) >= OOS_DT)[0]
    return metrics(rets=np.asarray(rets)[idx]) if idx.size else {}


def drop_year(rets, dates, year):
    keep = pd.DatetimeIndex(dates).year != int(year)
    return metrics(rets=np.asarray(rets)[keep])


def max_dd_span(rets, dates):
    nav = np.cumprod(1.0 + np.asarray(rets))
    peak = np.maximum.accumulate(nav)
    dd = nav / np.where(peak > 0, peak, np.nan) - 1.0
    tr = int(np.nanargmin(dd))
    pk = int(np.argmax(nav[:tr + 1]))
    idx = pd.DatetimeIndex(dates)
    after = nav[tr + 1:]
    rec = int(np.argmax(after >= nav[pk])) if after.size and np.any(after >= nav[pk]) else None
    return {'peak': str(idx[pk].date()), 'trough': str(idx[tr].date()),
            'mdd': round(float(dd[tr]), 4),
            'recover': str(idx[tr + 1 + rec].date()) if rec is not None else None,
            'drawdown_days': int(tr - pk),
            'underwater_months': round((tr - pk) / 21.0, 1)}


def rolling_winrate(rets, dates, win=244, minp=200):
    s = pd.Series(np.asarray(rets), index=pd.DatetimeIndex(dates))
    r = s.rolling(win, min_periods=minp).apply(lambda x: (1 + x).prod() - 1, raw=True).dropna()
    return {'n_windows': int(len(r)), 'win_months': int((r > 0).sum()),
            'winrate': round(float((r > 0).mean()), 4),
            'median_12m': round(float(r.median()), 4),
            'worst_12m': round(float(r.min()), 4), 'best_12m': round(float(r.max()), 4)}


def daily_eq_bench(p, mask, min_liq=5e7, mode='all', q=0.10, i0=I0):
    """面板内零成本基准：主板流动性达标股每日等权 / 主板市值最小 q 分位等权。"""
    adv = p.roll('a', 20, 'mean')
    elig = mask & np.isfinite(p.d['mv']) & (p.d['mv'] > 0) & np.isfinite(adv)
    if min_liq > 0:
        elig &= adv >= min_liq
    r = p.ret_clean
    out = []
    for t in range(i0, p.T - 1):
        idx = np.where(elig[t] & np.isfinite(r[t]))[0]
        if mode == 'small' and len(idx) >= 10:
            mv = p.d['mv'][t, idx]
            idx = idx[mv <= np.quantile(mv, q)]
        if len(idx) == 0:
            out.append(0.0); continue
        v = np.clip(np.nan_to_num(r[t, idx], nan=0.0), -0.5, 0.5)
        out.append(float(v.mean()))
    return np.array(out)


def hs300_yearly():
    try:
        h = xe.load_hs()
        c = h['close'].dropna()
        return {str(y): round(float(g.iloc[-1] / g.iloc[0] - 1), 4)
                for y, g in c.groupby(c.index.year)}
    except Exception:
        return {}


def scan_dim(p, base_spec, mask, dim, values, i1_common):
    """单维度扫描：只变一个维度，其余固定；非 hold 维度用各自 hold 的自然终点。"""
    grid = {}
    for v in values:
        spec = deepcopy(base_spec)
        if dim == 'factor_weight':
            # 市值权重 w，价格权重 1-w；w=0.5 为基准双低
            w = float(v)
            spec['params']['factors'] = [
                {'key': 'mv', 'asc': True, 'weight': w},
                {'key': 'c', 'asc': True, 'weight': round(1 - w, 6)}]
            if spec['params']['factors'][0]['weight'] == 0:
                spec['params']['factors'] = [{'key': 'c', 'asc': True, 'weight': 1.0}]
            if spec['params']['factors'][-1]['weight'] == 0 or w == 1.0:
                spec['params']['factors'] = [{'key': 'mv', 'asc': True, 'weight': 1.0}]
            fixed_i1 = None
        elif dim == 'topn':
            spec['params']['topn'] = int(v); fixed_i1 = None
        elif dim == 'hold':
            spec['params']['hold'] = int(v); fixed_i1 = i1_common   # 统一终点
        elif dim == 'liquidity':
            spec.setdefault('filters', {})['min_avg_amount'] = float(v); fixed_i1 = None
        elif dim == 'max_price':
            spec.setdefault('filters', {})['max_price'] = None if v == 0 else float(v); fixed_i1 = None
        elif dim == 'pool':
            fixed_i1 = None
            m = v  # v 直接是 mask 数组
        cb, real, imp = cost_of(spec)
        use_mask = v[1] if dim == 'pool' else mask
        r = cs_flex(p, spec, use_mask, cb, start=COMMON_START, end_i1=fixed_i1)
        ro = cs_flex(p, spec, use_mask, cb, start='2023-01-01')
        if not r:
            continue
        key = str(v) if dim != 'pool' else v[0]
        grid[key] = {'value': (None if v == 0 else v) if dim == 'max_price' else (str(v) if dim == 'pool' else v),
                     'cost_bp': cb, 'commission_bp': real, 'impact_bp': imp,
                     'full': metrics(rets=r['rets']), 'oos': metrics(rets=ro['rets']) if ro else {},
                     'n_trades': r['n_trades'], 'avg_picks': r['avg_picks']}
    return grid


def main():
    t0 = time.time()
    sp = load_s02()
    print('LOAD panel_v3 ...', flush=True)
    p = Panel(os.path.join(BASE, 'panel_v3.pkl'))
    main_mask = tradeable_mask(p.codes)
    full_mask = np.ones(p.N, dtype=bool)
    gem_mask = np.array([board_of(c)[0] in ('沪主板', '深主板', '创业板') for c in p.codes])
    from collections import Counter
    print('BOARD', dict(Counter(board_of(c)[0] for c in p.codes)), flush=True)
    base_spec = deepcopy(sp)
    base_spec.setdefault('filters', {})['min_avg_amount'] = 5e7
    cb, real, imp = cost_of(base_spec)
    print('S02 base cost_bp=%s (佣金%s + 冲击%s)' % (cb, real, imp), flush=True)

    out = {'generated': time.strftime('%Y-%m-%d %H:%M:%S'),
           'strategy': {'id': 'S02', 'name': sp['name'], 'signal': sp['signal_type'],
                        'factors': sp['params']['factors'], 'topn': sp['params']['topn'],
                        'hold': sp['params']['hold'],
                        'filters': {'min_avg_amount': 5e7}},
           'capital': CAP, 'capital_label': '11.2万',
           'permission': '新手<2年/C1：仅沪深主板；创业板/科创/转债/ST 剔除',
           'cost': {'standard_total_bp': cb, 'commission_bp': real, 'impact_bp': imp,
                    'model': '股票万2.5+最低5元+卖出印花税0.05%+0.2bp滑点；平方根冲击ETA0.5；免5档=万1.2无最低'},
           'panel': {'T': p.T, 'N': p.N, 'start': str(p.dates[0].date()), 'end': str(p.dates[-1].date()),
                     'tradeable_stocks': int(main_mask.sum()), 'delisted_in_panel': int((~p.listed[-1]).sum())}}

    # ---------- A. 基准锚定 ----------
    print('\n=== A. 基准锚定 + 分年度 ===', flush=True)
    base = cs_flex(p, base_spec, main_mask, cb, start=COMMON_START, log_picks=True)
    bm = metrics(rets=base['rets'])
    bo_direct = metrics(rets=cs_flex(p, base_spec, main_mask, cb, start='2023-01-01')['rets'])
    # 20bp 旧口径（对齐 v3_perm.perm_filtered_20bp=2.0571）
    base20 = metrics(rets=cs_flex(p, base_spec, main_mask, 20.0, start=COMMON_START)['rets'])
    all20 = metrics(rets=cs_flex(p, base_spec, full_mask, 20.0, start=COMMON_START)['rets'])
    # budget 免5档
    cb_b, _, _ = cost_of(base_spec, 'budget')
    base_budget = metrics(rets=cs_flex(p, base_spec, main_mask, cb_b, start=COMMON_START)['rets'])
    print('BASE standard nav=%.4f cagr=%.4f mdd=%.4f | oos直接=%.4f | 20bp主板=%.4f 全A=%.4f | 免5档=%.4f' % (
        bm['total_multiple'], bm['cagr'], bm['mdd'], bo_direct['total_multiple'],
        base20['total_multiple'], all20['total_multiple'], base_budget['total_multiple']), flush=True)
    out['anchor'] = {'standard_full': bm, 'standard_oos_direct': bo_direct,
                     'standard_20bp_mainboard': base20, 'allA_20bp': all20,
                     'fee_free_5yuan_full': base_budget, 'fee_free_bp': cb_b,
                     'v3perm_reference': {'standard_full': 2.1254, 'standard_oos': 2.0794,
                                          'perm_20bp': 2.0571, 'allA_20bp': 1.8644},
                     'start': str(base['dates'][0].date()), 'end': str(base['dates'][-1].date()),
                     'n_trades': base['n_trades'], 'avg_picks': base['avg_picks'],
                     'oos_note': '样本外=2023-01-01独立重跑(与v3perm交付2.0794同口径)'}

    ys = yearly(base['rets'], base['dates'])
    out['yearly'] = ys
    best_y = max(ys, key=lambda k: ys[k]['ret'])
    worst_y = min(ys, key=lambda k: ys[k]['ret'])
    total_log = math.log(bm['total_multiple']) if bm['total_multiple'] > 0 else float('nan')
    best_contrib = math.log(1 + ys[best_y]['ret']) / total_log if np.isfinite(total_log) and total_log > 0 else None
    out['yearly_analysis'] = {
        'best_year': best_y, 'best_ret': ys[best_y]['ret'],
        'worst_year': worst_y, 'worst_ret': ys[worst_y]['ret'],
        'best_log_contribution': round(float(best_contrib), 4) if best_contrib is not None else None,
        'positive_years': sum(1 for v in ys.values() if v['ret'] > 0), 'total_years': len(ys),
        'drop_best_year': drop_year(base['rets'], base['dates'], best_y),
        'drop_worst_year': drop_year(base['rets'], base['dates'], worst_y),
        'drop_2024': drop_year(base['rets'], base['dates'], '2024') if '2024' in ys else None}
    out['max_drawdown'] = max_dd_span(base['rets'], base['dates'])
    out['rolling_12m'] = rolling_winrate(base['rets'], base['dates'])
    # 基准逐年对比
    beq = daily_eq_bench(p, main_mask, mode='all')
    bsmall = daily_eq_bench(p, main_mask, mode='small', q=0.10)
    idx0 = I0
    dts = p.dates[idx0:idx0 + len(beq)]
    yeq = {y: v['ret'] for y, v in yearly(beq, dts).items()}
    ysmall = {y: v['ret'] for y, v in yearly(bsmall, dts).items()}
    yhs = hs300_yearly()
    out['yearly_vs_bench'] = {
        y: {'s02': ys[y]['ret'], 'mainboard_eq': yeq.get(y),
            'mainboard_small10pct': ysmall.get(y), 'hs300': yhs.get(y)}
        for y in ys if y in yeq}
    def _beat(key):
        return sum(1 for d in out['yearly_vs_bench'].values()
                   if d[key] is not None and d['s02'] > d[key])
    out['beat_bench'] = {
        'vs_mainboard_eq': _beat('mainboard_eq'),
        'vs_small10pct': _beat('mainboard_small10pct'),
        'vs_hs300': _beat('hs300'),
        'total_years': len(out['yearly_vs_bench'])}
    print('YEARLY', {y: v['ret'] for y, v in ys.items()}, flush=True)
    print('best=%s(%s) worst=%s(%s) drop_best=%s drop_2024=%s' % (
        best_y, ys[best_y]['ret'], worst_y, ys[worst_y]['ret'],
        out['yearly_analysis']['drop_best_year']['total_multiple'],
        out['yearly_analysis']['drop_2024']['total_multiple'] if out['yearly_analysis']['drop_2024'] else '-'), flush=True)
    print('MDD', out['max_drawdown'], 'ROLL', out['rolling_12m'], 'BEAT', out['beat_bench'], flush=True)

    # ---------- B. 参数扫描 ----------
    print('\n=== B. 六维参数扫描 ===', flush=True)
    i1_common = p.T - 62   # hold 维度统一终点（容纳最大 hold=60）
    scan = {}
    scan['factor_weight'] = scan_dim(p, base_spec, main_mask, 'factor_weight',
                                     [0.0, 0.25, 0.5, 0.75, 1.0], i1_common)
    scan['topn'] = scan_dim(p, base_spec, main_mask, 'topn', [5, 10, 15, 20, 30, 50], i1_common)
    scan['hold'] = scan_dim(p, base_spec, main_mask, 'hold', [5, 10, 20, 40, 60], i1_common)
    scan['liquidity'] = scan_dim(p, base_spec, main_mask, 'liquidity',
                                 [0, 2e7, 5e7, 1e8, 2e8], i1_common)
    scan['max_price'] = scan_dim(p, base_spec, main_mask, 'max_price', [0, 3, 5, 10, 20], i1_common)
    scan['pool'] = scan_dim(p, base_spec, main_mask, 'pool',
                            [('主板', main_mask), ('主板+创业板', gem_mask), ('全A含退市', full_mask)], i1_common)
    out['scan'] = scan
    for dim, grid in scan.items():
        print('  [%s]' % dim, flush=True)
        for k, v in grid.items():
            print('    %-12s cost=%-6s nav=%-8s oos=%-8s trades=%s picks=%s' % (
                k, v['cost_bp'], v['full'].get('total_multiple'), v['oos'].get('total_multiple'),
                v['n_trades'], v['avg_picks']), flush=True)
    # 平台统计（权重/topn/hold 是否成片）
    def plat(grid):
        navs = [v['full']['total_multiple'] for v in grid.values() if v['full'].get('total_multiple') is not None]
        ooss = [v['oos']['total_multiple'] for v in grid.values() if v['oos'].get('total_multiple') is not None]
        return {'n': len(navs), 'full_gt1': sum(1 for x in navs if x > 1),
                'oos_gt1': sum(1 for x in ooss if x > 1),
                'median': round(float(np.median(navs)), 4) if navs else None,
                'best': round(float(max(navs)), 4) if navs else None,
                'worst': round(float(min(navs)), 4) if navs else None}
    out['scan_platform'] = {d: plat(g) for d, g in scan.items()}

    # ---------- C. 安慰剂 + 归因 + 容量 + 尾部 ----------
    print('\n=== C. 安慰剂200次 + 归因 + 容量 + 尾部风险 ===', flush=True)
    full_navs = []
    year_navs = {}
    for seed in range(200):
        rng = np.random.default_rng(seed + 1)
        rp = cs_flex(p, base_spec, main_mask, cb, start=COMMON_START,
                     signal_fn=rand_signal, rng=rng)
        full_navs.append(float(np.prod(1.0 + rp['rets'])))
        for y, g in pd.Series(rp['rets'], index=pd.DatetimeIndex(rp['dates'])).groupby(lambda d: d.year):
            year_navs.setdefault(str(y), []).append(float((1 + g).prod() - 1))
    full_navs = np.array(full_navs)
    def pct_rank(arr, real):
        arr = np.asarray(arr)
        return round(float(np.mean(arr < real)), 4)
    out['placebo'] = {
        'n': 200, 'mean': round(float(full_navs.mean()), 4),
        'p50': round(float(np.percentile(full_navs, 50)), 4),
        'p95': round(float(np.percentile(full_navs, 95)), 4),
        'min': round(float(full_navs.min()), 4), 'max': round(float(full_navs.max()), 4),
        'real': bm['total_multiple'], 'pct_rank': pct_rank(full_navs, bm['total_multiple']),
        'per_year': {y: {'real': ys[y]['ret'],
                         'p50': round(float(np.percentile(v, 50)), 4),
                         'p95': round(float(np.percentile(v, 95)), 4),
                         'pct_rank': pct_rank(v, ys[y]['ret'])}
                     for y, v in year_navs.items() if y in ys}}
    print('PLACEBO full pct=%.4f | 分年进前5%%: %s' % (
        out['placebo']['pct_rank'],
        [y for y, d in out['placebo']['per_year'].items() if d['pct_rank'] >= 0.95]), flush=True)

    # 单因子归因（统一终点）
    attr = {}
    for fid, fac in [('纯小市值mv', [{'key': 'mv', 'asc': True, 'weight': 1.0}]),
                     ('纯低价c(后复权)', [{'key': 'c', 'asc': True, 'weight': 1.0}]),
                     ('纯低价cn(真实价)', [{'key': 'cn', 'asc': True, 'weight': 1.0}]),
                     ('双低mv+c', [{'key': 'mv', 'asc': True, 'weight': 1.0},
                                   {'key': 'c', 'asc': True, 'weight': 1.0}])]:
        s2 = deepcopy(base_spec)
        s2['params']['factors'] = fac
        cb2, _, _ = cost_of(s2)
        r2 = cs_flex(p, s2, main_mask, cb2, start=COMMON_START, end_i1=i1_common)
        r2o = cs_flex(p, s2, main_mask, cb2, start='2023-01-01')
        attr[fid] = {'full': metrics(rets=r2['rets']), 'oos': metrics(rets=r2o['rets'])}
        print('  ATTR %-16s nav=%s oos=%s' % (fid, attr[fid]['full'].get('total_multiple'),
                                            attr[fid]['oos'].get('total_multiple')), flush=True)
    out['attribution'] = attr

    # 容量曲线
    cap_rows = []
    for cap in [CAP, 300000, 500000, 1000000, 3000000, 10000000]:
        per = cap / base_spec['params']['topn']
        real_bp = roundtrip_bp(per, 'stock', FEE['standard'])
        imp = impact_bp(cap, ADV_SMALL, SIG_SMALL, base_spec['params']['topn'])
        part = per / ADV_SMALL
        cap_rows.append({'capital': cap, 'per_stock': round(per, 0),
                         'participation': round(part, 6),
                         'commission_bp': round(real_bp, 2), 'impact_bp': round(imp, 2),
                         'total_bp': round(real_bp + imp, 2)})
    out['capacity'] = cap_rows
    print('CAPACITY', [(r['capital'], r['participation'], r['total_bp']) for r in cap_rows], flush=True)

    # 尾部风险：ST/退市/面值 交叉
    stt = pd.read_csv(os.path.join(BASE, '补充数据', 'st_status.csv'), dtype={'code': str}, encoding='utf-8-sig')
    stt['code'] = stt['code'].str.zfill(6)
    st_now = set(stt.loc[stt['is_st_now'] == True, 'code'])
    ever_st = set(stt.loc[stt['ever_st_name_hint'] == True, 'code'])
    dp = pd.read_csv(os.path.join(BASE, '补充数据', 'delist_price.csv'), dtype={'code': str}, encoding='utf-8-sig')
    dp['code'] = dp['code'].str.zfill(6)
    delisted = set(dp['code'])
    raw_cnt = good_cnt = 0
    hit_st = hit_ever = hit_delist = cn_lt2 = cn_lt1 = 0
    for rec in base['picks_log']:
        for cd, cn in zip(rec['raw'], rec['cn']):
            raw_cnt += 1
            if cd in st_now: hit_st += 1
            if cd in ever_st: hit_ever += 1
            if cd in delisted: hit_delist += 1
            if cn is not None and cn < 2: cn_lt2 += 1
            if cn is not None and cn < 1: cn_lt1 += 1
        good_cnt += len(rec['good'])
    out['tail_risk'] = {
        'periods': len(base['picks_log']), 'raw_picks': raw_cnt, 'executed_picks': good_cnt,
        'execution_rate': round(good_cnt / max(raw_cnt, 1), 4),
        'hit_current_ST': hit_st, 'hit_current_ST_pct': round(hit_st / max(raw_cnt, 1), 4),
        'hit_ever_ST_name': hit_ever, 'hit_ever_ST_pct': round(hit_ever / max(raw_cnt, 1), 4),
        'hit_delisted': hit_delist, 'hit_delisted_pct': round(hit_delist / max(raw_cnt, 1), 4),
        'buy_price_lt2': cn_lt2, 'buy_price_lt2_pct': round(cn_lt2 / max(raw_cnt, 1), 4),
        'buy_price_lt1': cn_lt1, 'buy_price_lt1_pct': round(cn_lt1 / max(raw_cnt, 1), 4),
        'note': '历史逐日ST不可得；当前ST/退市清单为事后标记，命中率仅作尾部风险量级参考，非逐日可交易过滤。'}

    json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\nSAVED', OUT, 'elapsed', round(time.time() - t0, 1), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('FATAL', traceback.format_exc(), flush=True)
