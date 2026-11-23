# -*- coding: utf-8 -*-
"""持股集中度(topn)敏感性重跑：新口径版。
与旧版 topn_sensitivity_latest.py 的差异：
1. mask 改双口径：main 纯板块过滤无静态前视（主口径）、pit 叠加 exclude_st_pit（对照）。
2. 安慰剂候选域修正：逐信号独立，rand_signal 在对应真实信号 finite 集合内随机打分。
3. NPL 从 60 提升到 200，分辨率 0.01→0.005，缓解多重比较。
4. 门槛补 drop_worst，新增 strict 门槛（0.983 Bonferroni）。
5. 落盘安慰剂分布基线（min/p25/中位/p75/max），让分位可被正确解读。
6. 成本标注：cost_of 返回值本身即 bp，不再乘 10000。
输出：topn_sensitivity_result_newcal_20261122.json，不覆盖任何旧文件。
"""
import os, sys, json, pickle, time, warnings
import numpy as np
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore'); np.seterr(all='ignore')
BASE = r'D:\我的工作台\02.输出区'
sys.path.insert(0, BASE)
from xbx_engine import Panel, metrics
from v3_s02_deepdive import cs_flex, cost_of, yearly, rand_signal
from v3_perm import tradeable_mask

START = '2018-01-02'; OOS = '2023-01-01'; NPL = 200
TOPNS = [5, 10, 15, 20, 30]
t0 = time.time()

p = Panel(os.path.join(BASE, 'panel_v3.pkl'))
mask_main = tradeable_mask(p.codes)
mask_pit = mask_main.copy()
_ep = os.path.join(BASE, 'exclude_st_pit.json')
n_excl = 0
if os.path.exists(_ep):
    _ex = set(json.load(open(_ep, encoding='utf-8')))
    for _i, _c in enumerate(p.codes):
        if str(_c).zfill(6) in _ex:
            mask_pit[_i] = False; n_excl += 1
print('mask main=%d pit=%d excluded=%d' % (mask_main.sum(), mask_pit.sum(), n_excl), flush=True)

fp = pickle.load(open(os.path.join(BASE, 'fin_panel.pkl'), 'rb'))
F = fp['fields']; fdi = {ds: i for i, ds in enumerate(fp['dates'])}
fcodes = {c: i for i, c in enumerate(fp['codes'])}
cmap = np.array([fcodes.get(str(c).strip().split('.')[-1].zfill(6), -1) for c in p.codes])

def fld(key, t):
    if key in ('mv', 'c', 'cn', 'a', 'tr', 'v'): return np.asarray(p.d[key][t], float)
    ds = str(p.dates[t])[:10]; fi = fdi.get(ds)
    if fi is None:
        _av = [k for k in fdi if k <= ds]; fi = fdi[max(_av)] if _av else None
    if fi is None: return np.full(p.N, np.nan)
    v = np.full(p.N, np.nan); ok = cmap >= 0; v[ok] = F[key][fi][cmap[ok]]; return v

def rank_col(v, asc):
    r = np.full(p.N, np.nan); ok = np.isfinite(v); vals = v[ok]
    if len(vals) < 30: return r
    order = np.argsort(vals, kind='stable'); den = max(len(vals) - 1, 1); rk = np.empty(len(vals))
    if asc: rk[order] = np.arange(len(vals) - 1, -1, -1) / den
    else: rk[order] = np.arange(len(vals)) / den
    r[ok] = rk; return r

def sig_magic(pp, sp, t, rng=None):
    roe = fld('roe', t); pb = fld('pb', t); ok = (roe > 0) & (pb > 0)
    return np.where(ok, (rank_col(roe, False) + rank_col(1 / np.where(pb > 0, pb, np.nan), False)) / 2, np.nan)

def sig_cash(pp, sp, t, rng=None):
    ocf = fld('ocf_ttm', t); ps = fld('ps', t); cn = fld('cn', t)
    with np.errstate(all='ignore'): cm = ocf / (cn / ps)
    return rank_col(cm, False)

def sig_combo(pp, sp, t, rng=None):
    sm = sig_magic(pp, sp, t); sc = sig_cash(pp, sp, t)
    ok = np.isfinite(sm) & np.isfinite(sc)
    return np.where(ok, (sm + sc) / 2, np.nan)

CAND = {'A_神奇公式': sig_magic, 'B_现金净余率': sig_cash, 'C_价值现金合成': sig_combo}

def spec(tn): return {'params': {'topn': tn, 'hold': 20, 'ascending': False}, 'filters': {'min_avg_amount': 5e7}}

def make_fair_placebo(real_fn):
    """候选域修正：安慰剂在对应真实信号的 finite 集合内随机打分。"""
    def _f(pp, sp, t, rng=None):
        r = rng or np.random.default_rng()
        real = real_fn(pp, sp, t)
        s = np.full(pp.N, np.nan)
        idx = np.where(np.isfinite(real))[0]
        if len(idx): s[idx] = r.random(len(idx))
        return s
    return _f

def run_topn(tag, mask, tn):
    sp = spec(tn); cb = cost_of(sp)[0]
    print('--- [%s] topn=%d cost=%.3fbp placebo(NPL=%d)...' % (tag, tn, cb, NPL), flush=True)
    out = {'real_cost_bp': cb, 'placebo_n': NPL, 'strats': {}}
    for name, sfn in CAND.items():
        plF = []; plO = []
        for k in range(NPL):
            pf = cs_flex(p, sp, mask, cb, start=START, signal_fn=make_fair_placebo(sfn),
                         rng=np.random.default_rng(99000 + k))
            po = cs_flex(p, sp, mask, cb, start=OOS, signal_fn=make_fair_placebo(sfn),
                         rng=np.random.default_rng(99000 + k))
            if pf: plF.append(float(np.prod(1 + np.asarray(pf['rets']))))
            if po: plO.append(metrics(rets=po['rets'])['total_multiple'])
        plF = np.array(plF); plO = np.array(plO)
        r = cs_flex(p, sp, mask, cb, start=START, signal_fn=sfn)
        ro = cs_flex(p, sp, mask, cb, start=OOS, signal_fn=sfn)
        f = metrics(rets=r['rets']); o = metrics(rets=ro['rets'])
        dates = pd.DatetimeIndex(r['dates']); rets = np.asarray(r['rets'])
        yr = yearly(rets, dates); yret = {y: yr[y]['ret'] for y in yr}
        best = max(yret, key=yret.get); worst = min(yret, key=yret.get)
        drop_best = float(np.prod(1 + rets[dates.year != int(best)]))
        drop_worst = float(np.prod(1 + rets[dates.year != int(worst)]))
        r50 = cs_flex(p, sp, mask, 50.0, start=START, signal_fn=sfn)
        pctF = float((plF < f['total_multiple']).mean()); pctO = float((plO < o['total_multiple']).mean())
        gate = (pctF >= 0.90 and pctO >= 0.90 and metrics(rets=r50['rets'])['total_multiple'] > 1.0
                and drop_best > 1.0 and drop_worst > 1.0)
        gate_strict = (pctF >= 0.983 and pctO >= 0.983 and metrics(rets=r50['rets'])['total_multiple'] > 1.0
                       and drop_best > 1.0 and drop_worst > 1.0)
        d = {'full_mult': round(f['total_multiple'], 4), 'full_cagr': round(f.get('cagr', 0), 4),
             'full_mdd': round(f['mdd'], 4), 'full_sharpe': round(f.get('sharpe', 0), 4),
             'full_winrate': round(f.get('daily_winrate', 0), 4),
             'oos_mult': round(o['total_multiple'], 4), 'oos_mdd': round(o['mdd'], 4),
             'oos_sharpe': round(o.get('sharpe', 0), 4), 'oos_winrate': round(o.get('daily_winrate', 0), 4),
             'pctF': round(pctF, 3), 'pctO': round(pctO, 3),
             'placebo_baseline': {
                 'full': {'min': round(float(plF.min()), 4), 'p25': round(float(np.percentile(plF, 25)), 4),
                          'median': round(float(np.median(plF)), 4), 'p75': round(float(np.percentile(plF, 75)), 4),
                          'max': round(float(plF.max()), 4)},
                 'oos': {'min': round(float(plO.min()), 4), 'p25': round(round(float(np.percentile(plO, 25)), 4), 4),
                         'median': round(float(np.median(plO)), 4), 'p75': round(float(np.percentile(plO, 75)), 4),
                         'max': round(float(plO.max()), 4)}},
             'real_over_placebo_median_oos': round(o['total_multiple'] / float(np.median(plO)), 4),
             'bp50': round(metrics(rets=r50['rets'])['total_multiple'], 4),
             'drop_best': round(drop_best, 4), 'drop_best_year': best,
             'drop_worst': round(drop_worst, 4), 'drop_worst_year': worst,
             'n_trades': r['n_trades'], 'avg_picks': r['avg_picks'],
             'gate': {'result': 'PASS' if gate else 'FAIL', 'strict_result': 'PASS' if gate_strict else 'FAIL'},
             'yearly': {y: round(yr[y]['ret'], 4) for y in sorted(yr)}}
        out['strats'][name] = d
        print('   %-14s full %.3f oos %.3f sharpe %.3f mdd %.3f pct %.3f/%.3f (真实/安慰剂中位 %.2f) gate %s strict %s' % (
            name, d['full_mult'], d['oos_mult'], d['oos_sharpe'], d['full_mdd'], d['pctF'], d['pctO'],
            d['real_over_placebo_median_oos'], d['gate']['result'], d['gate']['strict_result']), flush=True)
    return out

res = {'main': {}, 'pit': {}}
for tn in TOPNS:
    res['main'][str(tn)] = run_topn('main', mask_main, tn)
    res['pit'][str(tn)] = run_topn('pit', mask_pit, tn)

out = {'meta': {
    'start': START, 'oos': OOS, 'topns': TOPNS, 'placebo_n': NPL, 'cap': 102000, 'hold': 20,
    'engine': 'mark_to_market_20261122',
    'placebo_fix': '候选域修正：逐信号独立，rand_signal 在对应真实信号 finite 集合内随机打分',
    'mask_main': {'desc': 'tradeable_mask 纯板块过滤，无静态 exclude，无静态前视', 'n': int(mask_main.sum())},
    'mask_pit': {'desc': 'main 叠加 exclude_st_pit.json（含未来信息，仅敏感性对照）',
                 'n': int(mask_pit.sum()), 'excluded': n_excl},
    'five_factors': ['signal:magic/cash/combo', 'topn=5/10/15/20/30', 'mask:main|pit 双口径',
                     'cost:cost_of(topn) 逐档', 'exclude:main 无静态排除 / pit 曾用名剔除（含未来信息）'],
    'note': '与旧版 topn_sensitivity_result_latest.json 的差异见脚本头部说明；旧文件保留不覆盖',
}, 'data': res}

P = os.path.join(BASE, 'topn_sensitivity_result_newcal_20261122.json')
json.dump(out, open(P, 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=str)
print('SAVED', P, 'elapsed %.1fs' % (time.time() - t0), flush=True)
