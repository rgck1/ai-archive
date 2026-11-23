# -*- coding: utf-8 -*-
"""第三口径：时点化 ST/退市排除（st_pit_intervals.json），无静态前视。

与 main（纯板块）、pit（静态 exclude，含未来信息）并列为第三比较口径。
ST 排除在 signal_fn 层注入：把 t 日处于 ST/退市状态的股票 signal 置 nan，
使其不进入候选域；静态 mask 仍为 tradeable_mask（纯板块）。
安慰剂在同一过滤后的 finite 集合内随机打分，候选域与真实策略严格一致。

区间语义（C 于 2026-11-22 明确确认）：
- intervals 左闭右开 [start, end)，end（摘帽日）当天不算 ST。
- end 为 None（end_missing）表示开放区间，从 start 起持续 active，保守处理。
- delist（摘牌日）当天即算退市，不可买从 delist 当日起生效。
- st_active = 任一 ST 区间命中 OR t_date >= delist，两者取或。

end_missing 局限：225 只中 47 只在 panel_v3 内，iFinD 漏最后一次摘帽事件，
按开放区间从最后一次戴帽日起持续剔除，结论需在报告中注明此保守偏向。

输出：champion_verify_result_timestamppit_20261122.json
"""
import os, sys, json, pickle, time
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding='utf-8')
BASE = r'D:\我的工作台\02.输出区'
sys.path.insert(0, BASE)
from xbx_engine import Panel, metrics
from v3_s02_deepdive import cs_flex, cost_of, yearly, max_dd_span
from v3_perm import tradeable_mask

START = '2018-01-02'; OOS = '2023-01-01'; NPL = 100
YEARS = ['2018-01-02', '2019-01-02', '2020-01-02', '2021-01-02', '2022-01-02', '2023-01-02']
t0 = time.time()

p = Panel(os.path.join(BASE, 'panel_v3.pkl'))
mask_main = tradeable_mask(p.codes)

# ---------- 构造逐交易日 ST/退市 grid ----------
st_data = json.load(open(os.path.join(BASE, 'st_pit_intervals.json'), encoding='utf-8'))
dates_str = [d.strftime('%Y%m%d') for d in p.dates]
T, N = p.T, p.N
st_grid = np.zeros((T, N), dtype=bool)
n_open = 0
for i, c in enumerate(p.codes):
    key = str(c).strip().split('.')[-1].zfill(6)
    rec = st_data.get(key)
    if not rec:
        continue
    for s, e in rec.get('intervals', []):
        si = int(np.searchsorted(dates_str, s, side='left'))
        if e is None:
            ei = T
            n_open += 1
        else:
            ei = int(np.searchsorted(dates_str, e, side='left'))  # 左闭右开，摘帽日不含
        if si < ei:
            st_grid[si:ei, i] = True
    dl = rec.get('delist')
    if dl:
        di = int(np.searchsorted(dates_str, dl, side='left'))  # 摘牌日当天起算退市
        st_grid[di:, i] = True
print('st_grid=%s active_cells=%d open_intervals=%d' % (str(st_grid.shape), int(st_grid.sum()), n_open), flush=True)
i_start = max(int(np.searchsorted(p.dates, pd.Timestamp(START))), 0)
affected = int(st_grid[i_start:, :].any(axis=0).sum())
print('panel N=%d affected_in_range=%d mask_main=%d' % (N, affected, int(mask_main.sum())), flush=True)

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

CAND_RAW = {'冠军A_神奇公式': sig_magic, '冠军B_经营现金净余率': sig_cash, '冠军C_价值现金合成': sig_combo}
sp0 = spec(); cb0 = cost_of(sp0)[0]
print('cost cb0=%.3fbp' % cb0, flush=True)

# ---------- 第三口径核心：signal 层注入时点化 ST 排除 ----------
def apply_st(s, t):
    return np.where(st_grid[t], np.nan, s)

def make_st_signal(real_fn):
    """真实信号：原始 finite 且 t 日未处于 ST/退市。"""
    def _f(pp, sp, t, rng=None):
        return apply_st(real_fn(pp, sp, t, rng=rng), t)
    return _f

def make_st_placebo(real_fn):
    """安慰剂：在第三口径真实信号的 finite 集合内随机打分，候选域严格一致。"""
    def _f(pp, sp, t, rng=None):
        r = rng or np.random.default_rng()
        s = apply_st(real_fn(pp, sp, t, rng=r), t)
        out = np.full(pp.N, np.nan)
        idx = np.where(np.isfinite(s))[0]
        if len(idx):
            out[idx] = r.random(len(idx))
        return out
    return _f

CAND_REAL = {k: make_st_signal(v) for k, v in CAND_RAW.items()}
CAND_PLACEBO = {k: make_st_placebo(v) for k, v in CAND_RAW.items()}

# 诊断：START 日各信号过滤前后候选数
diag = {}
for name, sfn in CAND_RAW.items():
    raw = sfn(p, sp0, i_start)
    before = int(np.isfinite(raw).sum())
    after = int(np.isfinite(apply_st(raw, i_start)).sum())
    diag[name] = {'before': before, 'after': after, 'excluded': before - after}
print('diag@START %s' % json.dumps(diag, ensure_ascii=False), flush=True)

def run_timestamppit():
    out = {}
    print('[timestamppit] placebo (候选域与各真实信号一致)...', flush=True)
    plF_by = {}; plO_by = {}
    for sname in CAND_RAW:
        fl = []; ol = []
        pfn = CAND_PLACEBO[sname]
        for k in range(NPL):
            pf = cs_flex(p, sp0, mask_main, cb0, start=START, signal_fn=pfn,
                         rng=np.random.default_rng(99000 + k))
            po = cs_flex(p, sp0, mask_main, cb0, start=OOS, signal_fn=pfn,
                         rng=np.random.default_rng(99000 + k))
            if pf: fl.append((pf['dates'], np.asarray(pf['rets'])))
            if po: ol.append(metrics(rets=po['rets'])['total_multiple'])
        plF_by[sname] = fl; plO_by[sname] = np.array(ol)
        print('  [%s] placebo full med %.3f oos med %.3f' % (
            sname, np.median([np.prod(1 + rt) for _, rt in fl]), np.median(plO_by[sname])), flush=True)
    for name in CAND_RAW:
        sfn = CAND_REAL[name]
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
        print('[timestamppit] === %s' % name, flush=True)
        r = cs_flex(p, sp0, mask_main, cb0, start=START, signal_fn=sfn)
        ro = cs_flex(p, sp0, mask_main, cb0, start=OOS, signal_fn=sfn)
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
            rr = cs_flex(p, sp0, mask_main, cb0, start=s, signal_fn=sfn)
            starts[s] = round(metrics(rets=rr['rets'])['total_multiple'], 4) if rr else None
        cost = {}
        for fee in ['budget', 'standard']:
            rr = cs_flex(p, sp0, mask_main, cost_of(sp0, fee=fee)[0], start=START, signal_fn=sfn)
            cost[fee] = round(metrics(rets=rr['rets'])['total_multiple'], 4)
        for bp in [20., 50.]:
            rr = cs_flex(p, sp0, mask_main, bp, start=START, signal_fn=sfn)
            cost['bp%d' % int(bp)] = round(metrics(rets=rr['rets'])['total_multiple'], 4)
        liq = {}
        for L in [0, 5e7, 1e8, 2e8]:
            spL = spec(liq=L)
            rr = cs_flex(p, spL, mask_main, cost_of(spL)[0], start=START, signal_fn=sfn)
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

res = run_timestamppit()

out = {'meta': {
    'start': START, 'oos': OOS, 'placebo_n': NPL, 'topn': 20, 'hold': 20, 'cap': 102000,
    'engine': 'mark_to_market_20261122',
    'mask': {'desc': 'tradeable_mask 纯板块过滤；ST/退市排除在 signal 层按 t 日时点化注入，无静态前视',
             'n': int(mask_main.sum()), 'st_grid_active_cells': int(st_grid.sum()),
             'panel_affected_in_range': affected, 'open_intervals': n_open,
             'diag_at_start': diag},
    'st_data': {'file': 'st_pit_intervals.json',
                'total_codes': sum(1 for k in st_data if k != '_meta'),
                'json_top_level_keys': len(st_data),
                'with_intervals': sum(1 for v in st_data.values() if v.get('intervals')),
                'with_delist': sum(1 for v in st_data.values() if v.get('delist')),
                'end_missing': sum(1 for v in st_data.values() if v.get('end_missing')),
                'semantics': 'intervals 左闭右开[start,end)，end 当天不算ST；end=None 开放区间持续剔除；delist 当天起算退市；st_active 取或',
                'limitation': '225只end_missing中47只在panel_v3内，iFinD漏最后一次摘帽，按开放区间保守持续剔除'},
    'placebo_fix': '候选域修正版：安慰剂在对应真实信号经时点化ST过滤后的 finite 集合内随机打分，逐信号独立分布',
    'placebo_domain': '逐信号独立：三者分位互不可比，各自与自身真实值可比',
    'annualization_note': 'metrics 用 xbx_engine.TRADING_DAYS=244（引擎常量，属策略定义口径），展示口径 √252 由前端换算',
    'five_factors': ['signal:magic/cash/combo', 'topn=20', 'mask:main 板块+时点化ST排除',
                     'cost:cost_of(topn=20)=%.3fbp' % cb0, 'exclude:st_pit_intervals.json 逐日时点化，无静态前视'],
}}
for k in res: out[k] = {'timestamppit': res[k]}

P = os.path.join(BASE, 'champion_verify_result_timestamppit_20261122.json')
json.dump(out, open(P, 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=str)
print('SAVED', P, 'elapsed %.1fs' % (time.time() - t0), flush=True)
