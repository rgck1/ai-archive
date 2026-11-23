# -*- coding: utf-8 -*-
"""把工作台「新手限购」权限口径贯穿进 11.2 万资金方案。

工作台真源 parts/30-script/08-perm.html:
  USER_PROFILE = expYears:1, assetsWan:0, riskLevel:C1
  PERM_RULES   = 沪深主板(SH60/SZ00) 已开通；普通ETF(kind=etf) 已开通；
                 创业板SZ(300/301)、科创板SH(688/689)、科创ETF SH(588/589)、
                 北交所BJ/(43|83|87|92)、可转债(11/12)、退市整理、ST 全部需2年+C4/C3 → 当前不可买
  BUYABLE_ETF_RE = SH(51|56)xxxx | SZ1(5|6|8)xxxx  （排除 588/589 科创ETF、12 转债）

本脚本做什么：
  1) 个股：在 Panel 上加 tradeable 掩码，板块过滤后重跑 G01/G02/G03/S02。
     同时做 1 手可买性检查（板块过滤后候选池会缩小，重新算每只能否买够 1 手）。
  2) ETF：按 BUYABLE_ETF_RE 重新筛每个策略的 assets，科创类剔除，重跑 I04-I08。
  3) 可转债：整组剔除（新手无权限），只登记不回测。
  4) 真实成本沿用 v3_capital10w 的两档费率（最低佣金+印花税+冲击）。
  5) 输出对比：过滤前(全A/全ETF) vs 过滤后(仅可买)，看净值变化与可执行清单。

不伪造任何数据，不改动既有引擎，权限掩码只在本地注入。凭证不回显。
"""
import os, sys, json, time, math, re, traceback
import numpy as np
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

BASE = r'D:\我的工作台\02.输出区'
sys.path.insert(0, BASE)
import xbx_engine as xe
from xbx_engine import Panel, signal, metrics
from xbx_engines_v3 import ETFData, index_rotation_v3

CAP = 112000.0
CAP_LABEL = '11.2万'
ETA = 0.5
MAX_PART = 5.0

FEE = {
    'standard': {'stock': (0.00025, 5.0, 0.0005), 'etf': (0.00012, 0.0, 0.0), 'cb': (0.00010, 0.0, 0.0)},
    'budget':   {'stock': (0.00012, 0.0, 0.0005), 'etf': (0.00012, 0.0, 0.0), 'cb': (0.00010, 0.0, 0.0)},
}

# 板块判定（与 08-perm.html 的 PERM_RULES / MAIN_BOARD_RE / BUYABLE_ETF_RE 对齐）
def board_of(code):
    c = str(code).zfill(6)
    if re.match(r'^60\d{4}$', c):  return ('沪主板', True)
    if re.match(r'^00[0123]\d{3}$', c): return ('深主板', True)
    if re.match(r'^(300|301)\d{3}$', c): return ('创业板', False)
    if re.match(r'^(688|689)\d{3}$', c): return ('科创板', False)
    if re.match(r'^(43|83|87|88|92|920)\d{3,4}$', c): return ('北交所', False)
    if re.match(r'^(40|42)\d{4}$', c):  return ('老三板', False)
    if re.match(r'^(11|12)\d{4}$', c):  return ('可转债', False)
    if re.match(r'^[589]\d{5}$', c) or re.match(r'^(15|16|18)\d{4}$', c):
        # 普通场内ETF 可买；588/589 科创ETF 单独判不可买
        if re.match(r'^(588|589)\d{3}$', c): return ('科创ETF', False)
        return ('ETF', True)
    return ('其他', False)   # 未知品种保守判不可买，与 newbie_restricted 一致

def tradeable_mask(codes):
    return np.array([board_of(c)[1] for c in codes], dtype=bool)

def buyable_etf(code6):
    return bool(re.match(r'^(SH(51|56)\d{4}|SZ1[568]\d{4})$', code6))

def etf_code_of(a):
    # 'etf_518880' -> 'SH518880'；指数名 idx_xxx 用映射
    if a.startswith('etf_'):
        c = a.split('_', 1)[1]
        return ('SH' if c[0] in '5' else 'SZ') + c
    m = {'idx_hs300': 'SH510300', 'idx_zz500': 'SH510500', 'idx_cyb': 'SZ159915', 'idx_sz50': 'SH510050'}
    return m.get(a, '')

def roundtrip_bp(per_order, kind, fee):
    rate, minc, stamp = fee[kind]
    com = max(per_order * rate, minc)
    bp = com / per_order * 10000.0
    return round(bp * 2 + stamp * 10000.0 + 0.2, 2)

def impact_bp(capital, adv, sigma, n):
    if not (np.isfinite(adv) and adv > 0 and np.isfinite(sigma) and sigma > 0): return 0.0
    part = min((capital / max(int(n), 1)) / adv, MAX_PART)
    return ETA * sigma * math.sqrt(part) * 10000.0

# 带板块掩码的截面回测：复用 xbx_engine.cross_section 的成交/成本逻辑，仅在选股后屏蔽无权标的
def cross_section_masked(p, spec, mask, exec_mode='close', cost_bp=20.0, start=None):
    hold = int(spec.get('params', {}).get('hold', 5))
    topn = int(spec.get('params', {}).get('topn', 20))
    asc = bool(spec.get('params', {}).get('ascending', False))
    i0 = int(np.searchsorted(p.dates, pd.Timestamp(start))) if start else 60
    i1 = p.T - hold - 2
    i0 = max(i0, 60)
    if i1 <= i0: return None
    cost = cost_bp / 10000.0
    c, o = p.d['c'], p.d['o']
    rets = np.zeros(i1 - i0 + 1); n_trades = 0; picks = 0
    t = i0
    while t + hold + 1 <= i1:
        s = signal(p, spec, t)
        ok = np.isfinite(s) & mask
        if ok.sum() < topn:
            t += 1; continue
        if asc: order = np.argsort(np.where(ok, s, np.inf), kind='stable')
        else:   order = np.argsort(-np.where(ok, s, -np.inf), kind='stable')
        sel = np.asarray(order[:topn])
        buy_i, sell_i = t + 1, t + 1 + hold
        bp = o[buy_i, sel] if exec_mode == 'open' else c[buy_i, sel]
        sp = o[sell_i, sel] if exec_mode == 'open' else c[sell_i, sel]
        good = np.isfinite(bp) & np.isfinite(sp) & (bp > 0)
        good &= p.enough_age[buy_i, sel] & ~p.mv_bad[buy_i, sel]
        min_liq = float(spec.get('filters', {}).get('min_avg_amount', 5e7))
        if min_liq > 0: good &= p.d['a'][buy_i, sel] >= min_liq * 0.5
        good &= ~p.has_bad(buy_i, sell_i + 1)[sel]
        good &= ~p.oneword_limit(buy_i, up=True)[sel]
        good &= ~p.oneword_limit(sell_i, up=False)[sel]
        if exec_mode == 'open':
            good &= ~(bp >= c[buy_i - 1, sel] * 1.098)
            good &= ~(sp <= c[sell_i - 1, sel] * 0.902)
        if good.sum() == 0:
            t += hold; continue
        n_trades += 1; picks += int(good.sum())
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
    return {'rets': rets, 'n_trades': n_trades, 'avg_picks': picks / max(n_trades, 1)}

def lot_check_masked(p, spec, mask, t, capital):
    s = signal(p, spec, t)
    ok = np.isfinite(s) & mask
    topn = int(spec.get('params', {}).get('topn', 10))
    asc = bool(spec.get('params', {}).get('ascending', False))
    if ok.sum() < topn: return {'topn': topn, 'n_candidates': int(ok.sum()), 'note': '候选不足'}
    if asc: order = np.argsort(np.where(ok, s, np.inf), kind='stable')
    else:   order = np.argsort(-np.where(ok, s, -np.inf), kind='stable')
    sel = np.asarray(order[:topn])
    px = p.d['cn'][t, sel]; per = capital / topn
    lots = per / (100.0 * px)
    afford = np.isfinite(px) & (lots >= 1.0)
    return {'topn': topn, 'n_candidates': int(ok.sum()), 'per_stock_yuan': round(per, 0),
            'price_median': round(float(np.nanmedian(px)), 2),
            'pct_affordable_1lot': round(float(np.mean(afford)) * 100, 1),
            'n_unaffordable': int(topn - afford.sum())}

def main():
    t0 = time.time()
    s1 = json.load(open(os.path.join(BASE, 'xbx_specs.json'), encoding='utf-8'))['strategies']
    s2 = json.load(open(os.path.join(BASE, 'xbx_specs_bloggers.json'), encoding='utf-8'))['strategies']
    by_id = {s['id']: s for s in s1 + s2}

    print('LOAD panel_v3 ...', flush=True)
    p = Panel(os.path.join(BASE, 'panel_v3.pkl'))
    mask = tradeable_mask(p.codes)
    from collections import Counter
    bd = Counter(board_of(c)[0] for c in p.codes)
    print('BOARD DIST', dict(bd), flush=True)
    print('TRADEABLE %d/%d (%.1f%%)' % (mask.sum(), p.N, 100.0 * mask.mean()), flush=True)

    adv20 = p.roll('a', 20, 'mean')
    with np.errstate(all='ignore'):
        adv_all = np.nanmedian(adv20, axis=0)
        sig_all = np.nanstd(p.ret_clean, axis=0)
    # 可买主板池的流动性基准
    ok_m = mask & np.isfinite(adv_all) & np.isfinite(p.d['mv'][-1])
    mv_last = p.d['mv'][-1]
    ordm = np.argsort(np.where(ok_m, mv_last, np.inf))
    small = ordm[:max(200, int(ok_m.sum() * 0.20))]
    adv_small = float(np.nanmedian(adv_all[small])); sig_small = float(np.nanmedian(sig_all[small]))

    out = {'generated': time.strftime('%Y-%m-%d %H:%M:%S'), 'capital': CAP, 'capital_label': CAP_LABEL,
           'permission': {'exp_years': 1, 'risk': 'C1', 'newbie_restricted': True,
                          'buyable': ['沪深主板 60/000/002/003', '普通ETF 沪51/56 深15/16/18'],
                          'blocked': ['创业板 300/301', '科创板 688/689', '科创ETF 588/589',
                                      '北交所 43/83/87/92', '可转债 11/12', '退市整理/老三板', 'ST']},
           'board_dist': dict(bd), 'tradeable_stocks': int(mask.sum()), 'total_stocks': int(p.N),
           'liquidity': {'adv_small_median': adv_small, 'sigma_small_median': sig_small},
           'stock': {}, 'etf': {}, 'cb_blocked': {}, 'lot_check': {}, 'verdict': []}

    # ---------- 1) 个股：板块过滤后重跑 ----------
    print('\n=== A. 个股（仅可买主板）真实成本重跑 ===', flush=True)
    t_check = p.T - 35
    for sid in ('G01', 'G02', 'G03', 'S02'):
        sp = by_id[sid]
        topn = int(sp.get('params', {}).get('topn', 10))
        adv, sg = adv_small, sig_small
        imp = impact_bp(CAP, adv, sg, topn)
        base_all = xe.cross_section(p, sp, exec_mode='close', cost_bp=20.0)   # 过滤前：全A
        base_perm = cross_section_masked(p, sp, mask, exec_mode='close', cost_bp=20.0)
        lc = lot_check_masked(p, sp, mask, t_check, CAP)
        out['lot_check'][sid] = lc
        rec = {'name': sp['name'], 'topn': topn, 'impact_bp': round(imp, 2),
               'all_universe_20bp': metrics(rets=base_all['rets']) if base_all else {},
               'perm_filtered_20bp': metrics(rets=base_perm['rets']) if base_perm else {},
               'avg_picks_after_filter': round(base_perm['avg_picks'], 1) if base_perm else None,
               'fees': {}}
        per = CAP / topn
        for fname, fee in FEE.items():
            real_bp = roundtrip_bp(per, 'stock', fee)
            total_bp = round(real_bp + imp, 2)
            r = cross_section_masked(p, sp, mask, exec_mode='close', cost_bp=total_bp)
            m = metrics(rets=r['rets']) if r else {}
            # 样本外：只跑一个时点切片（复用 masked 回测，起点 2023-01-01）
            ro = cross_section_masked(p, sp, mask, exec_mode='close', cost_bp=total_bp,
                                      start='2023-01-01')
            mo = metrics(rets=ro['rets']) if ro else {}
            rec['fees'][fname] = {'commission_stamp_bp': real_bp, 'total_bp': total_bp,
                                  'nav': m.get('total_multiple'), 'cagr': m.get('cagr'), 'mdd': m.get('mdd'),
                                  'out_sample': mo}
            print('%-4s %-8s 过滤前20bp nav=%s | 过滤后20bp nav=%s | 过滤后真实%5.1fbp nav=%s 样本外%s | 1手可买%4.1f%%(%d/%d)'
                  % (sid, fname, rec['all_universe_20bp'].get('total_multiple'),
                     rec['perm_filtered_20bp'].get('total_multiple'), total_bp, m.get('total_multiple'),
                     (mo or {}).get('total_multiple'),
                     lc.get('pct_affordable_1lot', 0), topn - lc.get('n_unaffordable', topn), topn), flush=True)
        out['stock'][sid] = rec

    # ---------- 2) ETF：按可买口径重筛资产池 ----------
    print('\n=== B. ETF（剔除科创ETF/转债ETF等无权品种）真实成本重跑 ===', flush=True)
    for sid in ('I04', 'I05', 'I06', 'I07', 'I08'):
        sp = by_id[sid]
        assets = sp.get('params', {}).get('assets', [])
        keep, drop = [], []
        for a in assets:
            sym = etf_code_of(a)
            (keep if (sym and buyable_etf(sym)) else drop).append(a)
        rec = {'name': sp['name'], 'assets_all': assets, 'assets_buyable': keep, 'assets_dropped': drop}
        try:
            if not keep:
                rec['error'] = '过滤后无标的'
            else:
                idata = ETFData(keep, 'hfq')
                if idata.N == 0: raise RuntimeError('no ETF data')
                adv = pd.DataFrame(idata.amt).rolling(20, min_periods=5).mean().to_numpy()
                sg = pd.DataFrame(idata.ret).rolling(20, min_periods=5).std().to_numpy()
                def imp_fn(t, pick, prev):
                    if pick < 0 or t >= len(adv): return 0.0
                    a_, s_ = adv[t, pick], sg[t, pick]
                    if not (np.isfinite(a_) and a_ > 0 and np.isfinite(s_) and s_ > 0): return 0.0
                    return ETA * s_ * math.sqrt(min(CAP / a_, MAX_PART))
                # 过滤前（全资产池）
                idata_all = ETFData(assets, 'hfq')
                r0 = index_rotation_v3(sp, idata=idata_all, cost_bp=20.0, start='2018-01-01', use_real_volume=False)
                rec['all_universe_20bp'] = metrics(rets=r0['rets']) if r0 else {}
                # 过滤后（仅可买）
                rp = index_rotation_v3(sp, idata=idata, cost_bp=20.0, start='2018-01-01', use_real_volume=False)
                rec['perm_filtered_20bp'] = metrics(rets=rp['rets']) if rp else {}
                rec['fees'] = {}
                for fname, fee in FEE.items():
                    real_bp = roundtrip_bp(CAP, 'etf', fee)
                    r = index_rotation_v3(sp, idata=idata, cost_bp=real_bp, extra_cost_fn=imp_fn,
                                          start='2018-01-01', use_real_volume=False)
                    m = metrics(rets=r['rets']) if r else {}
                    # 样本外：2023-01-01 起，用同一真实成本档重跑
                    ro = index_rotation_v3(sp, idata=idata, cost_bp=real_bp, extra_cost_fn=imp_fn,
                                           start='2023-01-01', use_real_volume=False)
                    mo = metrics(rets=ro['rets']) if ro else {}
                    rec['fees'][fname] = {'commission_bp': real_bp, 'nav': m.get('total_multiple'),
                                          'cagr': m.get('cagr'), 'mdd': m.get('mdd'),
                                          'out_sample': mo}
                fstd = rec['fees'].get('standard', {})
                oos = (fstd.get('out_sample') or {}).get('total_multiple')
                print('%-4s 全池nav=%s | 可买池nav=%s | 真实%4.1fbp nav=%s(样本外%s) | 剔除%s'
                      % (sid, rec['all_universe_20bp'].get('total_multiple'),
                         rec['perm_filtered_20bp'].get('total_multiple'), fstd.get('commission_bp'),
                         fstd.get('nav'), oos, ','.join(drop) or '无'), flush=True)
        except Exception as e:
            rec['error'] = repr(e)[:200]
            print('[ETF]', sid, 'FAIL', repr(e)[:120], flush=True)
        out['etf'][sid] = rec

    # ---------- 3) 可转债：整组剔除 ----------
    print('\n=== C. 可转债：新手无权限，整组剔除（仅登记） ===', flush=True)
    for sp in s2:
        if sp.get('engine') == 'cb_rotation':
            out['cb_blocked'][sp['id']] = {'name': sp['name'], 'reason': '需交易满2年+日均资产10万+C3，当前1年/C1不满足'}
            print('%s %s  剔除（无权限）' % (sp['id'], sp['name']), flush=True)

    # ---------- 4) 结论清单 ----------
    def nv(rec, k='standard'):
        try: return rec['fees'][k]['nav']
        except Exception: return None
    print('\n=== D. 11.2万 + 新手权限 可执行结论 ===', flush=True)
    verdict = []
    for sid, rec in out['stock'].items():
        lc = out['lot_check'].get(sid, {})
        afford = lc.get('pct_affordable_1lot', 100)
        v = nv(rec)
        if afford < 95:
            st, why = '不可执行', '仅%.0f%%标的买得起1手(每只%.0f元)' % (afford, lc['per_stock_yuan'])
        elif v is not None and v > 1:
            st, why = '可执行', '主板过滤后真实成本nav≈%s' % v
        else:
            st, why = '不建议', '成本前后均≤1'
        verdict.append({'id': sid, 'name': rec['name'], 'status': st, 'reason': why})
    for sid, rec in out['etf'].items():
        if 'fees' not in rec: 
            verdict.append({'id': sid, 'name': rec['name'], 'status': '无标的', 'reason': rec.get('error', '过滤后无标的')}); continue
        v = nv(rec)
        verdict.append({'id': sid, 'name': rec['name'], 'status': '可执行' if (v and v > 1) else '不建议',
                        'reason': '可买池%s→真实nav%s' % (','.join(rec['assets_buyable']), v)})
    for sid, rec in out['cb_blocked'].items():
        verdict.append({'id': sid, 'name': rec['name'], 'status': '不可买', 'reason': rec['reason']})
    out['verdict'] = verdict
    for v in verdict: print('%-4s %-26s %-8s %s' % (v['id'], v['name'], v['status'], v['reason']), flush=True)

    json.dump(out, open(os.path.join(BASE, 'v3_perm.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\nSAVED v3_perm.json elapsed', round(time.time() - t0, 1), flush=True)

if __name__ == '__main__':
    try: main()
    except Exception: print('FATAL', traceback.format_exc(), flush=True)
