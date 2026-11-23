# -*- coding: utf-8 -*-
"""安慰剂候选域修正版重跑：让 rand_signal 在真实 signal 的有限集合内随机打分。

[E 独立审查第十节指出] 原 rand_signal 施加了 has_bad 等额外筛选，候选池小于真实信号：
2023 年首个调仓日 rand_signal 候选 2911 只，magic 信号候选 4096 只。
随机信号面对更小的池，安慰剂偏严，真实策略分位被高估。

修法：不改生产引擎，在本脚本内包装 signal_fn，让安慰剂先算真实信号，
再在真实信号的 finite 集合内随机打分，保证零假设与真实策略候选域严格一致。

输出：champion_verify_result_fairplacebo_20261122.json
"""
import os, sys, json, pickle, time
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding='utf-8')
BASE = r'D:\我的工作台\02.输出区'
sys.path.insert(0, BASE)
from xbx_engine import Panel, metrics
from v3_s02_deepdive import cs_flex, cost_of, yearly, max_dd_span, rand_signal
from v3_perm import tradeable_mask

START = '2018-01-02'; OOS = '2023-01-01'; NPL = 100
YEARS = ['2018-01-02', '2019-01-02', '2020-01-02', '2021-01-02', '2022-01-02', '2023-01-02']
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
print('mask main=%d  pit=%d  excluded=%d' % (mask_main.sum(), mask_pit.sum(), n_excl), flush=True)

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

def spec(topn=20, hold=20, liq=5e7):
    return {'params': {'topn': topn, 'hold': hold, 'ascending': False}, 'filters': {'min_avg_amount': liq}}

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

CAND = {'冠军A_神奇公式': sig_magic, '冠军B_经营现金净余率': sig_cash, '冠军C_价值现金合成': sig_combo}
sp0 = spec(); cb0 = cost_of(sp0)[0]
print('cost cb0=%.3fbp' % cb0, flush=True)

def make_fair_placebo(real_fn):
    """[核心修正] 安慰剂在真实信号的 finite 集合内随机打分。
    真实信号为 nan 的位置保持 nan，候选域与真实策略严格一致。"""
    def _f(pp, sp, t, rng=None):
        r = rng or np.random.default_rng()
        real = real_fn(pp, sp, t)
        s = np.full(pp.N, np.nan)
        idx = np.where(np.isfinite(real))[0]
        if len(idx):
            s[idx] = r.random(len(idx))
        return s
    return _f

def run_variant(tag, mask):
    out = {}
    print('[%s] placebo (候选域与各真实信号一致)...' % tag, flush=True)
    # [对抗式审查修正] 逐信号建立安慰剂分布：每个信号的安慰剂在自己的候选域内随机打分，
    # 与该信号真实值比较。共用单一参照域会让 cash/combo 的分位失真
    # （magic 域含 roe/pb 有效但 cash 信号无效的票，域偏大，零假设偏松）。
    # 代价是三次安慰剂循环，成本约为共用版的 3 倍，可接受。
    plF_by = {}; plO_by = {}
    for sname, sfn in CAND.items():
        fl = []; ol = []
        for k in range(NPL):
            pf = cs_flex(p, sp0, mask, cb0, start=START, signal_fn=make_fair_placebo(sfn),
                         rng=np.random.default_rng(99000 + k))
            po = cs_flex(p, sp0, mask, cb0, start=OOS, signal_fn=make_fair_placebo(sfn),
                         rng=np.random.default_rng(99000 + k))
            if pf: fl.append((pf['dates'], np.asarray(pf['rets'])))
            if po: ol.append(metrics(rets=po['rets'])['total_multiple'])
        plF_by[sname] = fl; plO_by[sname] = np.array(ol)
        print('  [%s] placebo %s: full med %.3f oos med %.3f' % (
            tag, sname, np.median([np.prod(1 + rt) for _, rt in fl]), np.median(plO_by[sname])), flush=True)
    for name, sfn in CAND.items():
        plF = plF_by[name]; plO_arr = plO_by[name]
        plF_mult = np.array([np.prod(1 + rt) for _, rt in plF])
        placebo_baseline = {
            'full': {'min': round(float(plF_mult.min()), 4), 'p25': round(float(np.percentile(plF_mult, 25)), 4),
                     'median': round(float(np.median(plF_mult)), 4), 'p75': round(float(np.percentile(plF_mult, 75)), 4),
                     'max': round(float(plF_mult.max()), 4)},
            'oos': {'min': round(float(plO_arr.min()), 4), 'p25': round(float(np.percentile(plO_arr, 25)), 4),
                    'median': round(float(np.median(plO_arr)), 4), 'p75': round(float(np.percentile(plO_arr, 75)), 4),
                    'max': round(float(plO_arr.max()), 4)},
        }
        print('[%s] === %s' % (tag, name), flush=True)
        r = cs_flex(p, sp0, mask, cb0, start=START, signal_fn=sfn)
        ro = cs_flex(p, sp0, mask, cb0, start=OOS, signal_fn=sfn)
        full = metrics(rets=r['rets']); oos = metrics(rets=ro['rets'])
        yr = yearly(r['rets'], r['dates'])
        dates = pd.DatetimeIndex(r['dates']); rets = np.asarray(r['rets'])
        pl_year = {}
        for y in range(2018, 2027):
            kp = dates.year == y
            if kp.sum() < 20: continue
            real = float(np.prod(1 + rets[kp]))
            rv = []
            for pdates, pr in plF:
                kk = pd.DatetimeIndex(pdates).year == y
                if kk.sum() >= 20: rv.append(float(np.prod(1 + pr[kk])))
            pl_year[str(y)] = {'real': round(real, 4),
                               'pct': round(float((np.array(rv) < real).mean()), 3) if rv else None}
        yret = {y: yr[y]['ret'] for y in yr}
        best = max(yret, key=yret.get); worst = min(yret, key=yret.get)
        drop_best = float(np.prod(1 + rets[dates.year != int(best)]))
        drop_worst = float(np.prod(1 + rets[dates.year != int(worst)]))
        starts = {}
        for s in YEARS:
            rr = cs_flex(p, sp0, mask, cb0, start=s, signal_fn=sfn)
            starts[s] = round(metrics(rets=rr['rets'])['total_multiple'], 4) if rr else None
        cost = {}
        for fee in ['budget', 'standard']:
            rr = cs_flex(p, sp0, mask, cost_of(sp0, fee=fee)[0], start=START, signal_fn=sfn)
            cost[fee] = round(metrics(rets=rr['rets'])['total_multiple'], 4)
        for bp in [20., 50.]:
            rr = cs_flex(p, sp0, mask, bp, start=START, signal_fn=sfn)
            cost['bp%d' % int(bp)] = round(metrics(rets=rr['rets'])['total_multiple'], 4)
        liq = {}
        for L in [0, 5e7, 1e8, 2e8]:
            spL = spec(liq=L)
            rr = cs_flex(p, spL, mask, cost_of(spL)[0], start=START, signal_fn=sfn)
            liq[str(int(L))] = round(metrics(rets=rr['rets'])['total_multiple'], 4)
        d = {'full': full, 'oos': oos,
             'yearly': {y: round(yr[y]['ret'], 4) for y in sorted(yr)},
             'placebo_full_pct': round(float((plF_mult < full['total_multiple']).mean()), 3),
             'placebo_oos_pct': round(float((plO_arr < oos['total_multiple']).mean()), 3),
             'placebo_yearly_all': pl_year,
             'drop_best_year': {'year': best, 'mult': round(drop_best, 4)},
             'drop_worst_year': {'year': worst, 'mult': round(drop_worst, 4)},
             'start_robust': starts, 'cost': cost, 'liquidity': liq,
             'placebo_baseline': placebo_baseline,
             'mdd_span': max_dd_span(r['rets'], r['dates'])}
        out[name] = d
        gate = (d['placebo_full_pct'] >= 0.90 and d['placebo_oos_pct'] >= 0.90
                and cost['bp50'] > 1.0 and drop_best > 1.0 and drop_worst > 1.0)
        gate_strict = (d['placebo_full_pct'] >= 0.983 and d['placebo_oos_pct'] >= 0.983
                       and cost['bp50'] > 1.0 and drop_best > 1.0 and drop_worst > 1.0)
        d['gate'] = {'result': 'PASS' if gate else 'FAIL',
                     'strict_result': 'PASS' if gate_strict else 'FAIL',
                     'detail': {'placebo_full_pct': d['placebo_full_pct'], 'placebo_oos_pct': d['placebo_oos_pct'],
                                'placebo_full_pct_ge_0983': d['placebo_full_pct'] >= 0.983,
                                'placebo_oos_pct_ge_0983': d['placebo_oos_pct'] >= 0.983,
                                'cost_bp50': cost['bp50'], 'drop_best': round(drop_best, 4),
                                'drop_worst': round(drop_worst, 4)}}
        print('  full %.3f oos %.3f pctF %.3f pctO %.3f mdd %.3f' % (
            full['total_multiple'], oos['total_multiple'],
            d['placebo_full_pct'], d['placebo_oos_pct'], full['mdd']), flush=True)
        print('  >>> 常规 %s  严格 %s' % (d['gate']['result'], d['gate']['strict_result']), flush=True)
    return out

res_main = run_variant('main', mask_main)
res_pit = run_variant('pit', mask_pit)

out = {'meta': {
    'start': START, 'oos': OOS, 'placebo_n': NPL, 'topn': 20, 'hold': 20, 'cap': 102000,
    'engine': 'mark_to_market_20261122',
    'placebo_fix': '候选域修正版：安慰剂在对应真实信号的 finite 集合内随机打分，逐信号独立分布，与真实策略候选域严格一致（E 第十节）',
    'placebo_domain': '逐信号独立：每个信号的安慰剂用自己信号域，三者分位互不可比但各自与自身真实值可比',
    'annualization_note': 'metrics 用 xbx_engine.TRADING_DAYS=244（引擎常量，属策略定义口径），展示口径 √252 由前端换算',
    'mask_main': {'desc': 'tradeable_mask 纯板块过滤，不叠加任何静态 exclude，无静态前视', 'n': int(mask_main.sum())},
    'mask_pit': {'desc': 'main 叠加 exclude_st_pit.json 曾用名剔除（含未来信息，仅敏感性对照，不作真值）',
                 'n': int(mask_pit.sum()), 'excluded': n_excl},
    'five_factors': ['signal:magic/cash/combo', 'topn=20', 'mask:main|pit 双口径', 'cost:cost_of(topn=20)=%.3fbp' % cb0,
                     'exclude:main 无静态排除 / pit 曾用名剔除（含未来信息）'],
}}
for k in res_main: out[k] = {'main': res_main[k], 'pit': res_pit[k]}

P = os.path.join(BASE, 'champion_verify_result_fairplacebo_20261122.json')
json.dump(out, open(P, 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=str)
print('SAVED', P, 'elapsed %.1fs' % (time.time() - t0), flush=True)
