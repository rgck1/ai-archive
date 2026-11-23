# -*- coding: utf-8 -*-
"""逐日收益序列导出（路径B前置数据准备）2026-11-23。

只跑真实策略，跳过安慰剂循环。复用 v3_s02_deepdive.cs_flex 的逐日盯市口径，
导出冠军因子三信号乘三口径共 9 条，以及 topn 敏感性 5 档乘 2 口径乘 3 信号共 30 条。
每个策略导出两条序列：full 从 START 起，oos 从 OOS 起独立重跑。
key 命名与权威 JSON 的字段一一对应，便于逐条做倍数自检。

输出：daily_sequences_2026-11-23.npz 与 daily_sequences_导出说明_2026-11-23.md
"""
import os, sys, json, pickle, time, warnings
import numpy as np
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')
np.seterr(all='ignore')

BASE = r'D:\我的工作台\02.输出区'
sys.path.insert(0, BASE)
from xbx_engine import Panel, metrics
from v3_s02_deepdive import cs_flex, cost_of
from v3_perm import tradeable_mask

START = '2018-01-02'
OOS = '2023-01-01'
TOPNS = [5, 10, 15, 20, 30]
TOL = 0.01
t0 = time.time()

# ---------------- 数据与掩码 ----------------
p = Panel(os.path.join(BASE, 'panel_v3.pkl'))
ALL_DATES = np.asarray(p.dates)
mask_main = tradeable_mask(p.codes)
mask_pit = mask_main.copy()
_ep = os.path.join(BASE, 'exclude_st_pit.json')
if os.path.exists(_ep):
    _ex = set(json.load(open(_ep, encoding='utf-8')))
    for _i, _c in enumerate(p.codes):
        if str(_c).zfill(6) in _ex:
            mask_pit[_i] = False
print('mask main=%d pit=%d excluded=%d' % (int(mask_main.sum()), int(mask_pit.sum()),
      int((~mask_pit & mask_main).sum())), flush=True)

# 时点化 ST/退市 grid，逻辑与 champion_verify_timestamppit_20261122.py 完全一致
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
            ei = int(np.searchsorted(dates_str, e, side='left'))
        if si < ei:
            st_grid[si:ei, i] = True
    dl = rec.get('delist')
    if dl:
        di = int(np.searchsorted(dates_str, dl, side='left'))
        st_grid[di:, i] = True
print('st_grid=%s active_cells=%d open_intervals=%d' % (str(st_grid.shape),
      int(st_grid.sum()), n_open), flush=True)

# 财务面板与信号字段
fp = pickle.load(open(os.path.join(BASE, 'fin_panel.pkl'), 'rb'))
F = fp['fields']
fdi = {ds: i for i, ds in enumerate(fp['dates'])}
fcodes = {c: i for i, c in enumerate(fp['codes'])}
cmap = np.array([fcodes.get(str(c).strip().split('.')[-1].zfill(6), -1) for c in p.codes])


def fld(key, t):
    if key in ('mv', 'c', 'cn', 'a', 'tr', 'v'):
        return np.asarray(p.d[key][t], float)
    ds = str(p.dates[t])[:10]
    fi = fdi.get(ds)
    if fi is None:
        _av = [k for k in fdi if k <= ds]
        fi = fdi[max(_av)] if _av else None
    if fi is None:
        return np.full(p.N, np.nan)
    v = np.full(p.N, np.nan)
    ok = cmap >= 0
    v[ok] = F[key][fi][cmap[ok]]
    return v


def rank_col(v, asc):
    r = np.full(p.N, np.nan)
    ok = np.isfinite(v)
    vals = v[ok]
    if len(vals) < 30:
        return r
    order = np.argsort(vals, kind='stable')
    den = max(len(vals) - 1, 1)
    rk = np.empty(len(vals))
    if asc:
        rk[order] = np.arange(len(vals) - 1, -1, -1) / den
    else:
        rk[order] = np.arange(len(vals)) / den
    r[ok] = rk
    return r


def sig_magic(pp, sp, t, rng=None):
    roe = fld('roe', t)
    pb = fld('pb', t)
    ok = (roe > 0) & (pb > 0)
    return np.where(ok, (rank_col(roe, False) + rank_col(1 / np.where(pb > 0, pb, np.nan), False)) / 2, np.nan)


def sig_cash(pp, sp, t, rng=None):
    ocf = fld('ocf_ttm', t)
    ps = fld('ps', t)
    cn = fld('cn', t)
    with np.errstate(all='ignore'):
        cm = ocf / (cn / ps)
    return rank_col(cm, False)


def sig_combo(pp, sp, t, rng=None):
    sm = sig_magic(pp, sp, t)
    sc = sig_cash(pp, sp, t)
    ok = np.isfinite(sm) & np.isfinite(sc)
    return np.where(ok, (sm + sc) / 2, np.nan)


def apply_st(s, t):
    return np.where(st_grid[t], np.nan, s)


def make_st_signal(real_fn):
    def _f(pp, sp, t, rng=None):
        return apply_st(real_fn(pp, sp, t, rng=rng), t)
    return _f


CAND_BASE = {'magic': sig_magic, 'cash': sig_cash, 'combo': sig_combo}
# 权威 JSON 中的信号显示名映射
SIG_FAIR = {'magic': '冠军A_神奇公式', 'cash': '冠军B_经营现金净余率', 'combo': '冠军C_价值现金合成'}
SIG_TOPN = {'magic': 'A_神奇公式', 'cash': 'B_现金净余率', 'combo': 'C_价值现金合成'}


def spec(topn=20, hold=20, liq=5e7):
    return {'params': {'topn': topn, 'hold': hold, 'ascending': False},
            'filters': {'min_avg_amount': liq}}


# ---------------- 导出容器 ----------------
seqs = {}
cfg = {}
chk = []


def do_run(key, sp, mask, cb, sfn, start):
    """跑一条真实策略序列并落内存，返回 full 段乘积。"""
    r = cs_flex(p, sp, mask, cb, start=start, signal_fn=sfn)
    if not r:
        raise RuntimeError('cs_flex 返回空: ' + key)
    dates = np.asarray(r['dates'])
    idx = np.searchsorted(ALL_DATES, dates).astype(np.int64)
    if not np.array_equal(ALL_DATES[idx], dates):
        raise RuntimeError('日期索引未对齐: ' + key)
    rets = np.asarray(r['rets'], dtype=np.float64)
    arr = np.empty((len(idx), 2), dtype=np.float64)
    arr[:, 0] = idx
    arr[:, 1] = rets
    seqs[key] = arr
    mult = float(np.prod(1.0 + rets))
    return mult, r


def add_chk(src, group, key, seg, exported, auth_path):
    chk.append({'src': src, 'group': group, 'key': key, 'seg': seg,
                'exported': exported, 'auth_path': auth_path})


# ---------------- 1. 冠军因子三信号乘三口径 ----------------
sp0 = spec()
cb0 = float(cost_of(sp0)[0])
print('冠军成本 cb0=%.3fbp' % cb0, flush=True)

for sig, fn in CAND_BASE.items():
    # main 口径
    for calib, mask in [('main', mask_main), ('pit', mask_pit)]:
        k = '%s__%s' % (sig, calib)
        mf, _ = do_run(k, sp0, mask, cb0, fn, START)
        mo, _ = do_run(k + '__oos', sp0, mask, cb0, fn, OOS)
        cfg[k] = {'signal': sig, 'caliber': calib, 'topn': 20, 'hold': 20, 'liq': 5e7,
                  'cost_bp': round(cb0, 3), 'start': START, 'oos': OOS,
                  'mask_n': int(mask.sum()), 'st_grid': False}
        cfg[k + '__oos'] = dict(cfg[k], start=OOS)
        add_chk('fair', '冠军因子', k, 'full', mf,
                (SIG_FAIR[sig], calib, 'full', 'total_multiple'))
        add_chk('fair', '冠军因子', k, 'oos', mo,
                (SIG_FAIR[sig], calib, 'oos', 'total_multiple'))
        print('  %-22s full %.4f oos %.4f' % (k, mf, mo), flush=True)
    # timestamppit 口径，signal 层注入时点化 ST/退市
    sf = make_st_signal(fn)
    k = '%s__timestamppit' % sig
    mf, _ = do_run(k, sp0, mask_main, cb0, sf, START)
    mo, _ = do_run(k + '__oos', sp0, mask_main, cb0, sf, OOS)
    cfg[k] = {'signal': sig, 'caliber': 'timestamppit', 'topn': 20, 'hold': 20, 'liq': 5e7,
              'cost_bp': round(cb0, 3), 'start': START, 'oos': OOS,
              'mask_n': int(mask_main.sum()), 'st_grid': True,
              'st_active_cells': int(st_grid.sum()), 'open_intervals': n_open}
    cfg[k + '__oos'] = dict(cfg[k], start=OOS)
    add_chk('st', '冠军因子', k, 'full', mf,
            (SIG_FAIR[sig], 'timestamppit', 'full', 'total_multiple'))
    add_chk('st', '冠军因子', k, 'oos', mo,
            (SIG_FAIR[sig], 'timestamppit', 'oos', 'total_multiple'))
    print('  %-22s full %.4f oos %.4f' % (k, mf, mo), flush=True)

# ---------------- 2. topn 敏感性 30 组 ----------------
for tn in TOPNS:
    sp = spec(tn)
    cb = float(cost_of(sp)[0])
    for calib, mask in [('main', mask_main), ('pit', mask_pit)]:
        for sig, fn in CAND_BASE.items():
            k = 'topn%d__%s__%s' % (tn, calib, sig)
            mf, _ = do_run(k, sp, mask, cb, fn, START)
            mo, _ = do_run(k + '__oos', sp, mask, cb, fn, OOS)
            cfg[k] = {'signal': sig, 'caliber': calib, 'topn': tn, 'hold': 20, 'liq': 5e7,
                      'cost_bp': round(cb, 3), 'start': START, 'oos': OOS,
                      'mask_n': int(mask.sum()), 'st_grid': False}
            cfg[k + '__oos'] = dict(cfg[k], start=OOS)
            add_chk('topn', 'topn敏感性', k, 'full', mf,
                    ('data', calib, str(tn), 'strats', SIG_TOPN[sig], 'full_mult'))
            add_chk('topn', 'topn敏感性', k, 'oos', mo,
                    ('data', calib, str(tn), 'strats', SIG_TOPN[sig], 'oos_mult'))
        print('  topn=%-2d %-4s cost=%.3fbp 3信号 done' % (tn, calib, cb), flush=True)

# ---------------- 3. 自检对照 ----------------
J = {
    'fair': json.load(open(os.path.join(BASE, 'champion_verify_result_fairplacebo_20261122.json'), encoding='utf-8')),
    'st': json.load(open(os.path.join(BASE, 'champion_verify_result_timestamppit_20261122.json'), encoding='utf-8')),
    'topn': json.load(open(os.path.join(BASE, 'topn_sensitivity_result_newcal_20261122.json'), encoding='utf-8')),
}


def nav(d, path):
    for k in path:
        d = d[k]
    return float(d)


n_pass = 0
rows = []
for c in chk:
    auth = nav(J[c['src']], c['auth_path'])
    diff = c['exported'] - auth
    ok = abs(diff) <= TOL
    n_pass += int(ok)
    rows.append({'group': c['group'], 'key': c['key'], 'seg': c['seg'],
                 'exported': c['exported'], 'auth': auth, 'diff': diff, 'ok': ok})
    if not ok:
        print('  MISMATCH %-26s %-4s export=%.4f auth=%.4f diff=%.4f' % (
            c['key'], c['seg'], c['exported'], auth, diff), flush=True)

print('自检 %d/%d 通过' % (n_pass, len(chk)), flush=True)

# ---------------- 4. 落盘 npz ----------------
NPZ = os.path.join(BASE, 'daily_sequences_2026-11-23.npz')
dates_str_arr = np.asarray([str(d.date()) for d in p.dates], dtype='<U10')
meta = {
    'generated': time.strftime('%Y-%m-%d %H:%M:%S'),
    'start': START, 'oos': OOS, 'tolerance': TOL,
    'engine': 'v3_s02_deepdive.cs_flex (mark_to_market_20261122)',
    'n_strategies': 39, 'n_series': len(seqs), 'n_dates': int(p.T),
    'date_index_basis': '整数索引，相对 _dates 全局交易日数组',
    'series_columns': ['date_index', 'daily_return'],
    'seg_note': 'key 为 full 段（start=%s）；key__oos 为样本外独立重跑（start=%s）' % (START, OOS),
    'cost': {'champion_topn20_bp': round(cb0, 3),
             'topn_bp': {str(tn): round(float(cost_of(spec(tn))[0]), 3) for tn in TOPNS}},
    'masks': {'main_n': int(mask_main.sum()), 'pit_n': int(mask_pit.sum()),
              'pit_excluded': int((~mask_pit & mask_main).sum()),
              'st_grid_active_cells': int(st_grid.sum()), 'st_open_intervals': n_open},
    'configs': cfg,
    'selfcheck': rows,
    'selfcheck_pass': n_pass,
    'selfcheck_total': len(chk),
}
save_dict = dict(seqs)
save_dict['_dates'] = dates_str_arr
save_dict['_meta'] = np.array(json.dumps(meta, ensure_ascii=False, default=str))
np.savez_compressed(NPZ, **save_dict)
print('SAVED npz %s  keys=%d elapsed=%.1fs' % (NPZ, len(save_dict), time.time() - t0), flush=True)

# ---------------- 5. 说明文档 ----------------
MD = os.path.join(BASE, 'daily_sequences_导出说明_2026-11-23.md')
n_strat = len(cfg) // 2
L = []
L.append('# 逐日收益序列导出说明（2026-11-23）')
L.append('')
L.append('## 结论')
L.append('')
L.append('导出 %d 个策略，每个策略 full 与 oos 两条序列，合计 %d 条序列。倍数自检 %d/%d 条通过。总耗时 %.1f 秒。' % (
    n_strat, len(seqs), n_pass, len(chk), time.time() - t0))
L.append('')
L.append('## npz 字段含义')
L.append('')
L.append('文件：`daily_sequences_2026-11-23.npz`（numpy 压缩 npz）。')
L.append('')
L.append('- `_dates`：全局交易日字符串数组，长度 %d，格式为 YYYY-MM-DD。' % p.T)
L.append('- `_meta`：JSON 字符串（0 维数组，用 `.item()` 取出），含 start、oos、容差、引擎口径、成本、掩码规模、各策略配置与逐条自检结果。')
L.append('- 每个策略 key 存一个二维数组，形状 (n, 2)。第一列为日期序号，即该日相对 `_dates` 的整数索引；第二列为该交易日日收益（float）。')
L.append('- key 后缀规则：`magic__main` 为 full 段（start=%s）；`magic__main__oos` 为样本外独立重跑段（start=%s）。其余以此类推。' % (START, OOS))
L.append('')
L.append('## 如何读取')
L.append('')
L.append('```python')
L.append('import json, numpy as np')
L.append("d = np.load(r'%s')" % NPZ)
L.append("meta = json.loads(d['_meta'].item())")
L.append("dates_all = d['_dates']")
L.append("arr = d['magic__main']              # (n,2): [date_index, daily_return]")
L.append('idx = arr[:, 0].astype(int)')
L.append('rets = arr[:, 1]')
L.append('dates = dates_all[idx]')
L.append('full_mult = float(np.prod(1 + rets))')
L.append('```')
L.append('')
L.append('## 策略清单（%d 个）' % n_strat)
L.append('')
L.append('冠军因子 9 条：magic、cash、combo 各乘 main、pit、timestamppit 三口径。')
L.append('')
L.append('topn 敏感性 30 组：档位 5、10、15、20、30 各乘 main、pit 两口径，再乘 magic、cash、combo 三信号。')
L.append('')
L.append('每个策略另有 `__oos` 后缀的样本外独立重跑序列，共 %d 条。' % len(seqs))
L.append('')
L.append('## 自检对照表')
L.append('')
L.append('口径：对每条序列算 `np.prod(1+rets)`，与权威 JSON 对应字段比对，容差 ±%.2f。权威来源：冠军 main/pit 取 champion_verify_result_fairplacebo_20261122.json，timestamppit 取 champion_verify_result_timestamppit_20261122.json，topn 取 topn_sensitivity_result_newcal_20261122.json。' % TOL)
L.append('')
L.append('| 类别 | 策略 key | 段 | 导出倍数 | 权威倍数 | 差值 | 是否通过 |')
L.append('| --- | --- | --- | --- | --- | --- | --- |')
for r in rows:
    L.append('| %s | %s | %s | %.4f | %.4f | %+.6f | %s |' % (
        r['group'], r['key'], r['seg'], r['exported'], r['auth'], r['diff'],
        '通过' if r['ok'] else '不通过'))
L.append('')
L.append('汇总：%d/%d 条通过。' % (n_pass, len(chk)))
bad = [r for r in rows if not r['ok']]
if bad:
    L.append('')
    L.append('### 未通过的序列')
    L.append('')
    for r in bad:
        L.append('- %s %s：导出 %.4f，权威 %.4f，差值 %+.6f。' % (
            r['key'], r['seg'], r['exported'], r['auth'], r['diff']))
else:
    L.append('')
    L.append('全部序列与权威 JSON 在容差内一致，无未通过项。')
L.append('')
L.append('## 口径说明')
L.append('')
L.append('- 信号、成本、掩码与权威回测脚本逐行一致，冠军用 topn=20、hold=20，成本取 `cost_of(spec)[0]`；topn 逐档取 `cost_of(spec(tn))[0]`。')
L.append('- timestamppit 口径在 signal 层注入时点化 ST/退市排除，mask 用纯板块 main，排除区间语义与第三口径脚本一致。')
L.append('- 逐日收益来自 `cs_flex` 的 mark-to-market 口径，`rets[0]` 为空仓日 0，故 `np.prod(1+rets)` 与 `metrics.total_multiple` 等价。')
L.append('- 本次只跑真实策略，跳过安慰剂循环，故耗时远低于全量重跑。')
L.append('')
open(MD, 'w', encoding='utf-8').write('\n'.join(L))
print('SAVED md %s elapsed=%.1fs' % (MD, time.time() - t0), flush=True)
