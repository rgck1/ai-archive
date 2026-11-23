# -*- coding: utf-8 -*-
"""Walk-forward 滚动验证（2026-11-23）

安排：3 年训练 / 1 年测试滚动。测试年 2022-2026，测试年 Y 的训练段为 Y 前推
3 个日历年（如测试 2024 训练 2021-2023）。训练段锁参数只做信号三选一，
测试段绝不回头调整。

实现要点：
- 训练段与测试段都用 v3_s02_deepdive.cs_flex 的 end_i1 参数限定区间，不改引擎。
- 训练段选择规则（写死）：训练段内三个信号分别跑 cs_flex，取全期倍数
  （metrics.total_multiple）最高者；倍数并列（容差 1e-9）时选夏普高者。
- 口径：main 掩码（tradeable_mask 纯板块过滤、无静态前视）、spec() topn=20
  hold=20、成本 cost_of(sp0)[0]，与 champion_verify_fairplacebo_20261122.py 一致。
- 指标用 xbx_engine.metrics（TRADING_DAYS=244 口径），与权威 JSON 同口径。
- 每个测试年独立起跑（start=Y-01-01），各测试段按日期拼接；段间若有空档填 0 收益日。
- 自检：各测试年固定信号版年段倍数与 daily_sequences_2026-11-23.npz 对应年段
  对照（容差 ±0.01）；另做同起点切片验证组隔离引擎正确性与起跑点差异。

输出：walk_forward_result_2026-11-23.json
"""
import os, sys, json, pickle, time
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding='utf-8')
BASE = r'D:\我的工作台\02.输出区'
sys.path.insert(0, BASE)
from xbx_engine import Panel, metrics
from v3_s02_deepdive import cs_flex, cost_of, yearly, max_dd_span
from v3_perm import tradeable_mask

TEST_YEARS = [2022, 2023, 2024, 2025, 2026]
TRAIN_N = 3
HOLD = 20
t0 = time.time()

def log(msg):
    print('[%7.1fs] %s' % (time.time() - t0, msg), flush=True)

log('加载 Panel ...')
p = Panel(os.path.join(BASE, 'panel_v3.pkl'))
T = p.T
log('Panel 就绪 T=%d N=%d dates %s ~ %s' % (T, p.N, str(p.dates[0])[:10], str(p.dates[-1])[:10]))

mask_main = tradeable_mask(p.codes)
log('mask_main=%d' % int(mask_main.sum()))

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
NPZ_KEY = {'冠军A_神奇公式': 'magic', '冠军B_经营现金净余率': 'cash', '冠军C_价值现金合成': 'combo'}
sp0 = spec(); cb0 = cost_of(sp0)[0]
log('cost cb0=%.3fbp' % cb0)

def idx_at(ds):
    return int(np.searchsorted(p.dates, pd.Timestamp(ds)))

def year_last_idx(Y):
    """Y 年最后交易日的全局索引；Y+1 无数据时取数据末尾。"""
    nxt = idx_at('%d-01-01' % (Y + 1))
    return (nxt - 1) if nxt < T else T - 1

def seg_end_i1(Y):
    """测试段 end_i1：年末与引擎默认上限 p.T-hold-2 取小，保证卖出日不越界。"""
    return min(year_last_idx(Y), T - HOLD - 2)

_cache = {}
def run_seg(sname, start, end_i1):
    key = (sname, str(start), int(end_i1))
    if key not in _cache:
        log('  cs_flex %s start=%s end_i1=%d' % (sname, start, end_i1))
        _cache[key] = cs_flex(p, sp0, mask_main, cb0, start=start, end_i1=end_i1,
                              signal_fn=CAND[sname])
    return _cache[key]

def seg_year_mult(r, Y):
    dts = pd.DatetimeIndex(r['dates']); rr = np.asarray(r['rets'])
    k = dts.year == Y
    return float(np.prod(1 + rr[k])) if k.sum() >= 20 else None

# ============ 1. 滚动主循环：训练段三选一 + 各测试段 ============
log('===== 滚动训练段评估与测试段 =====')
selection = []          # 每年选择记录
seg_store = {}          # (Y, sname) -> 段结果
for Y in TEST_YEARS:
    tr_start = '%d-01-01' % (Y - TRAIN_N)
    tr_end_i1 = year_last_idx(Y - 1)
    tr_years = '%d-%d' % (Y - TRAIN_N, Y - 1)
    log('[%d] 训练段 %s (end_i1=%d)' % (Y, tr_years, tr_end_i1))
    tm = {}; sh = {}; nd = {}
    for s in CAND:
        r = run_seg(s, tr_start, tr_end_i1)
        m = metrics(rets=r['rets'])
        tm[s] = m['total_multiple']; sh[s] = m['sharpe']; nd[s] = m['n_days']
        log('  训练 %s: mult=%.4f sharpe=%.4f days=%d' % (s, tm[s], sh[s], m['n_days']))
    # 选择规则（写死）：训练段全期倍数最高；并列（1e-9）选夏普高者
    best_tm = max(tm.values())
    tied = [s for s in CAND if abs(tm[s] - best_tm) < 1e-9]
    sel = max(tied, key=lambda s: sh[s])
    log('[%d] 选中 %s' % (Y, sel))
    # 测试段：三个信号都跑（固定版曲线需要）
    te_start = '%d-01-01' % Y
    te_end = seg_end_i1(Y)
    for s in CAND:
        r = run_seg(s, te_start, te_end)
        seg_store[(Y, s)] = r
        log('  测试 %d %s: mult=%.4f days=%d' % (Y, s, float(np.prod(1 + np.asarray(r['rets']))), len(r['rets'])))
    selection.append({
        'test_year': Y,
        'train_start': str(p.dates[idx_at(tr_start)])[:10],
        'train_end': str(p.dates[tr_end_i1])[:10],
        'train_years': tr_years,
        'train_days': tr_end_i1 - idx_at(tr_start) + 1,
        'train_total_multiple': {s: round(tm[s], 4) for s in CAND},
        'train_sharpe': {s: round(sh[s], 4) for s in CAND},
        'train_n_days': {s: int(nd[s]) for s in CAND},
        'selected': sel,
        'tied': tied,
        'test_seg_days': len(seg_store[(Y, sel)]['rets']),
        'test_seg_multiple': round(float(np.prod(1 + np.asarray(seg_store[(Y, sel)]['rets']))), 4),
        'test_year_complete': (Y != 2026),
    })

# ============ 2. 四条曲线拼接 ============
log('===== 拼接四条曲线 =====')
def build_curve(signals_by_year):
    rets_l = []; dates_l = []; segs = []
    prev_i1 = None
    for Y in TEST_YEARS:
        s = signals_by_year[Y]
        r = seg_store[(Y, s)]
        i0 = idx_at('%d-01-01' % Y)
        i1 = i0 + len(r['rets']) - 1
        if prev_i1 is not None and i0 > prev_i1 + 1:
            gap = i0 - prev_i1 - 1
            rets_l.append(np.zeros(gap)); dates_l.append(np.asarray(p.dates[prev_i1 + 1:i0]))
            log('警告：%d 年段前有 %d 个空档日，填 0 收益' % (Y, gap))
        rets_l.append(np.asarray(r['rets'])); dates_l.append(np.asarray(r['dates']))
        segs.append({'year': Y, 'signal': s, 'i0': i0, 'i1': i1, 'days': len(r['rets'])})
        prev_i1 = i1
    return np.concatenate(rets_l), pd.DatetimeIndex(np.concatenate(dates_l)), segs

sel_by_year = {rec['test_year']: rec['selected'] for rec in selection}
curves_spec = {
    'WF选择版': sel_by_year,
    'WF固定A_神奇公式': {Y: '冠军A_神奇公式' for Y in TEST_YEARS},
    'WF固定B_经营现金净余率': {Y: '冠军B_经营现金净余率' for Y in TEST_YEARS},
    'WF固定C_价值现金合成': {Y: '冠军C_价值现金合成' for Y in TEST_YEARS},
}
curves = {}
for cname, sby in curves_spec.items():
    rets, dts, segs = build_curve(sby)
    m = metrics(rets=rets)
    curves[cname] = {
        'metrics': m,
        'yearly': {y: v['ret'] for y, v in yearly(rets, dts).items()},
        'yearly_days': {y: v['days'] for y, v in yearly(rets, dts).items()},
        'mdd_span': max_dd_span(rets, dts),
        'seg_multiples': {str(g['year']): round(float(np.prod(1 + np.asarray(seg_store[(g['year'], g['signal'])]['rets']))), 4) for g in segs},
    }
    log('%s: mult=%.4f cagr=%.4f mdd=%.4f sharpe=%.4f days=%d' % (
        cname, m['total_multiple'], m['cagr'], m['mdd'], m['sharpe'], m['n_days']))

# ============ 3. 自检 ============
log('===== 自检：同起点切片复现 =====')
sel_dates = [rec['selected'] for rec in selection]
n_switch = sum(1 for i in range(1, len(sel_dates)) if sel_dates[i] != sel_dates[i - 1])

full18 = {}; oos23 = {}
for s in CAND:
    log('复现 full2018 %s' % s)
    full18[s] = cs_flex(p, sp0, mask_main, cb0, start='2018-01-02', signal_fn=CAND[s])
    log('复现 oos2023 %s' % s)
    oos23[s] = cs_flex(p, sp0, mask_main, cb0, start='2023-01-01', signal_fn=CAND[s])

npz = np.load(os.path.join(BASE, 'daily_sequences_2026-11-23.npz'))
dates_all = npz['_dates']

def npz_year_mult(key, Y):
    arr = npz[key]; idx = arr[:, 0].astype(int); rets = arr[:, 1]
    ys = np.array([x[:4] for x in dates_all[idx]])
    k = ys == str(Y)
    return float(np.prod(1 + rets[k])) if k.sum() >= 20 else None

def npz_total(key):
    arr = npz[key]
    return float(np.prod(1 + arr[:, 1]))

# 3a. 同起点切片验证组：复现序列切年段 vs npz 对应序列年段（引擎与切片正确性）
slice_check = []
for s in CAND:
    k = NPZ_KEY[s]
    for Y in range(2018, 2027):
        rm = seg_year_mult(full18[s], Y); rn = npz_year_mult(k + '__main', Y)
        if rm is not None and rn is not None:
            slice_check.append({'signal': s, 'series': 'full2018 vs npz main', 'year': Y,
                                'repro': round(rm, 4), 'npz': round(rn, 4),
                                'diff': round(rm - rn, 4), 'pass_001': abs(rm - rn) <= 0.01})
    for Y in range(2023, 2027):
        rm = seg_year_mult(oos23[s], Y); rn = npz_year_mult(k + '__main__oos', Y)
        if rm is not None and rn is not None:
            slice_check.append({'signal': s, 'series': 'oos2023 vs npz main__oos', 'year': Y,
                                'repro': round(rm, 4), 'npz': round(rn, 4),
                                'diff': round(rm - rn, 4), 'pass_001': abs(rm - rn) <= 0.01})
n_slice_pass = sum(1 for x in slice_check if x['pass_001'])
log('同起点切片验证：%d/%d 通过' % (n_slice_pass, len(slice_check)))

# 3b. 复现 oos2023 总倍数 vs 权威 JSON oos 字段
auth = json.load(open(os.path.join(BASE, 'champion_verify_result_fairplacebo_20261122.json'), encoding='utf-8'))
oos_auth_check = []
for s in CAND:
    rm = metrics(rets=oos23[s]['rets'])['total_multiple']
    ra = auth[s]['main']['oos']['total_multiple']
    oos_auth_check.append({'signal': s, 'repro': rm, 'authority': ra,
                           'diff': round(rm - ra, 4), 'pass_001': abs(rm - ra) <= 0.01})
    log('oos2023 %s 复现 %.4f 权威 %.4f' % (s, rm, ra))

# 3c. WF 固定版各测试年段倍数 vs npz 权威年段倍数
fix_vs_npz = []
for Y in TEST_YEARS:
    for s in CAND:
        wm = seg_year_mult(seg_store[(Y, s)], Y)
        if Y == 2023:
            ref_key = NPZ_KEY[s] + '__main__oos'; note = '同起点 2023-01-01，应一致'
        elif Y == 2022:
            ref_key = NPZ_KEY[s] + '__main'; note = '起跑点不同：npz 为 2018 起跑连续持仓，WF 为 2022 独立空仓起跑'
        else:
            ref_key = NPZ_KEY[s] + '__main__oos'; note = '起跑点不同：npz 为 2023 起跑连续持仓，WF 为当年独立空仓起跑'
        rm = npz_year_mult(ref_key, Y)
        fix_vs_npz.append({'year': Y, 'signal': s, 'wf_seg_mult': round(wm, 4),
                           'npz_ref_mult': round(rm, 4), 'npz_ref_key': ref_key,
                           'diff': round(wm - rm, 4), 'pass_001': abs(wm - rm) <= 0.01,
                           'note': note})
n_fix_pass = sum(1 for x in fix_vs_npz if x['pass_001'])
log('固定版年段对照：%d/%d 在 ±0.01 内（其中 2023 同起点段应全过）' % (n_fix_pass, len(fix_vs_npz)))

# ============ 4. 对比分析 ============
def sub_from(rets, dts, ds):
    k = pd.DatetimeIndex(dts) >= pd.Timestamp(ds)
    return metrics(rets=np.asarray(rets)[k])

wf_rets, wf_dts, _ = build_curve(sel_by_year)
wf_2023 = sub_from(wf_rets, wf_dts, '2023-01-01')
fixA_rets, fixA_dts, _ = build_curve(curves_spec['WF固定A_神奇公式'])
fixA_2023 = sub_from(fixA_rets, fixA_dts, '2023-01-01')
fixB_rets, fixB_dts, _ = build_curve(curves_spec['WF固定B_经营现金净余率'])
fixB_2023 = sub_from(fixB_rets, fixB_dts, '2023-01-01')
fixC_rets, fixC_dts, _ = build_curve(curves_spec['WF固定C_价值现金合成'])
fixC_2023 = sub_from(fixC_rets, fixC_dts, '2023-01-01')

single_oos = {s: auth[s]['main']['oos'] for s in CAND}
analysis = {
    'n_switch': n_switch,
    'selection_sequence': {str(rec['test_year']): rec['selected'] for rec in selection},
    'wf_2023_onward': wf_2023,
    'wf_fixed_A_2023_onward': fixA_2023,
    'wf_fixed_B_2023_onward': fixB_2023,
    'wf_fixed_C_2023_onward': fixC_2023,
    'single_oos_authority': single_oos,
    'compare_common_window': {
        'desc': '共同覆盖段 2023-01-01 起。WF 各年独立空仓起跑，与单点 OOS 连续持仓存在起跑摩擦，固定版与单点的差异即摩擦量级',
        'wf_select_vs_single_magic': round(wf_2023['total_multiple'] - single_oos['冠军A_神奇公式']['total_multiple'], 4),
        'wf_fixA_vs_single_magic': round(fixA_2023['total_multiple'] - single_oos['冠军A_神奇公式']['total_multiple'], 4),
        'wf_fixB_vs_single_cash': round(fixB_2023['total_multiple'] - single_oos['冠军B_经营现金净余率']['total_multiple'], 4),
        'wf_fixC_vs_single_combo': round(fixC_2023['total_multiple'] - single_oos['冠军C_价值现金合成']['total_multiple'], 4),
    },
}

out = {
    'meta': {
        'date': '2026-11-23',
        'scheme': 'walk-forward 3年训练/1年测试，训练段锁参数只做信号三选一，测试段不回头调',
        'test_years': TEST_YEARS,
        'train_rule': '测试年 Y 训练段 = Y 前推 3 个日历年（cs_flex end_i1 限定，不改引擎）',
        'select_rule': '训练段内三信号各跑 cs_flex，取全期倍数（metrics.total_multiple）最高；并列(1e-9)选夏普高者。规则写死于脚本',
        'metrics_caliber': 'xbx_engine.metrics（TRADING_DAYS=244），与权威 JSON champion_verify_result_fairplacebo_20261122.json 同口径',
        'spec': 'topn=20 hold=20 liq=5e7',
        'cost_bp': cb0,
        'mask': 'main = tradeable_mask(p.codes)，纯板块过滤无静态前视，n=%d' % int(mask_main.sum()),
        'data_range': [str(p.dates[0])[:10], str(p.dates[-1])[:10]],
        'seg_impl': '每个测试年独立起跑 start=Y-01-01，end_i1=min(年末索引, T-hold-2)；各段按日期拼接，空档填 0',
        'note_2026': '2026 数据截至 10-08 且末段受 hold 限制提前停止开仓，属不完整年，指标仅供参考',
        'n_cs_flex_calls': len(_cache),
        'elapsed_sec': round(time.time() - t0, 1),
    },
    'selection_records': selection,
    'curves': curves,
    'selfcheck': {
        'slice_same_start': slice_check,
        'slice_same_start_pass': '%d/%d' % (n_slice_pass, len(slice_check)),
        'oos2023_vs_authority': oos_auth_check,
        'wf_fixed_vs_npz': fix_vs_npz,
        'wf_fixed_vs_npz_pass': '%d/%d' % (n_fix_pass, len(fix_vs_npz)),
    },
    'analysis': analysis,
}
P = os.path.join(BASE, 'walk_forward_result_2026-11-23.json')
json.dump(out, open(P, 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=str)
log('SAVED %s' % P)
log('完成，总耗时 %.1fs，cs_flex 调用 %d 次' % (time.time() - t0, len(_cache)))
