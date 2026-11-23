# -*- coding: utf-8 -*-
"""幸存者偏差压力测试（温和版）
面板只含当前存续股票，缺失约 200+ 只退市股，且集中在小市值/低价/低成交额组。
按年化暴雷率随机给每期持仓中的 1 只施加 -60% 损失，多种子取中位数。
同时保留「每期最差1只-80%」作为极端下界（明确标注为不现实的上界压力）。
"""
import sys, json, copy, math
import numpy as np
sys.path.insert(0, r'D:\我的工作台\02.输出区')
import xbx_engine as E
from xbx_engine import Panel, cross_section, metrics

p = Panel()
specs = json.load(open(r'D:\我的工作台\02.输出区\xbx_specs.json', encoding='utf-8'))['strategies']
targets = [s for s in specs if s['id'] in ('S01', 'S02', 'S03', 'S04', 'S05')]
LIQ = 5e7


def bench():
    avg = p.roll('a', 20, 'mean')
    ok = (avg >= LIQ) & (p.d['a'] >= LIQ * 0.5)
    src = np.where(ok, p.ret_clean, np.nan)
    cnt = np.sum(np.isfinite(src), axis=1)
    return np.nan_to_num(np.nansum(src, axis=1), nan=0.0) / np.maximum(cnt, 1)


br = bench()
cut = np.searchsorted(p.dates, np.datetime64('2023-01-01'))
print('BENCH(5000万门槛等权) 全期=%.3f 样本外=%.3f' % (
    metrics(rets=br)['total_multiple'], metrics(rets=br[cut:])['total_multiple']))


def run_shocked(s, annual_rate=0.0, extreme=False, start=None, seed=0):
    sp = copy.deepcopy(s)
    sp.setdefault('filters', {})['min_avg_amount'] = LIQ
    hold = int(sp.get('params', {}).get('hold', 20))
    topn = int(sp.get('params', {}).get('topn', 20))
    asc = bool(sp.get('params', {}).get('ascending', False))
    i0 = int(np.searchsorted(p.dates, start)) if start else 60
    i1 = p.T - hold - 2
    i0 = max(i0, 60)
    cost = 20.0 / 10000.0
    c = p.d['c']
    rets = np.zeros(i1 - i0 + 1)
    rng = np.random.default_rng(seed)
    # [ShockFix 2026-11-22] 年化暴雷率按"每只持仓股每年暴雷概率"解释。
    # 每期（约1个月）单票暴雷概率 = annual_rate/12；
    # 每期至少一只中招概率 = 1-(1-annual_rate/12)^topn，随持仓数放大，符合直觉。
    # 旧实现 p_event=annual_rate/12 直接当组合级触发率，5% 档仅 0.42%，几乎不触发。
    p_per_stock = annual_rate / 12.0
    p_event = 1.0 - (1.0 - p_per_stock) ** topn if annual_rate > 0 else 0.0
    t = i0
    while t + hold + 1 <= i1:
        sgn = E.signal(p, sp, t)
        okk = np.isfinite(sgn)
        if okk.sum() < topn:
            t += 1; continue
        order = np.argsort(np.where(okk, sgn, np.inf) if asc
                           else -np.where(okk, sgn, -np.inf), kind='stable')
        sel = np.asarray(order[:topn])
        bi, si = t + 1, t + 1 + hold
        bp, spx = c[bi, sel], c[si, sel]
        good = np.isfinite(bp) & np.isfinite(spx) & (bp > 0)
        good &= p.enough_age[bi, sel] & ~p.mv_bad[bi, sel]
        good &= p.d['a'][bi, sel] >= LIQ * 0.5
        good &= ~((p.bad_cs[si, sel] - p.bad_cs[bi, sel]) > 0)
        good &= ~p.oneword_limit(bi, up=True)[sel]
        good &= ~p.oneword_limit(si, up=False)[sel]
        if good.sum() == 0:
            t += hold; continue
        rr = np.clip(spx[good] / bp[good] - 1.0, -0.6, 1.0) - cost
        # [ShockFix 2026-11-22] 暴雷冲击必须注入盯市实际读取的日收益矩阵 rc，
        # 旧实现只改 rr，而盯市收益来自 rc，导致冲击对净值零影响（0%/5% 输出全同）。
        # 建模：单票退市按连续跌停路径实现累计损失 —— 每日封死跌停 -10%，
        # 连续 n 日使 (1-0.10)^n ≈ (1+loss)；A 股主板跌停 10%，跌停日无法卖出，
        # 停牌日记 0。loss 温和档 -60%、极端下界档 -80%。
        held = sel[good]; seg0, seg1 = t - i0, si - i0
        rc = np.asarray(p.ret_clean, dtype=float)
        # 决定本期是否、对哪只票施加冲击
        hit_local = -1
        loss = 0.0
        if extreme and len(rr) > 1:
            hit_local = int(np.argsort(rr)[0])   # 最差票作为极端下界
            loss = -0.80
        elif annual_rate > 0 and rng.random() < p_event and len(rr) > 1:
            hit_local = int(rng.integers(len(rr)))  # 随机一票按年化暴雷率触发
            loss = -0.60
        # 连续跌停天数：(1-0.10)^n = (1+loss)
        n_limit = int(np.ceil(np.log1p(loss) / np.log(1.0 - 0.10))) if hit_local >= 0 else 0
        # 冲击起点随机落在建仓后、持有期内，且留出足够跌停交易日
        n_days = min(seg1 + 1, len(rets)) - (seg0 + 2)
        shock_start = seg0 + 2
        if hit_local >= 0 and n_days > n_limit:
            shock_start = seg0 + 2 + int(rng.integers(0, n_days - n_limit + 1))
        for pos in range(seg0 + 2, min(seg1 + 1, len(rets))):
            rd = rc[pos + i0, held]
            rd = np.where(np.isfinite(rd), rd, 0.0)
            rd = np.clip(rd, -0.11, 0.11)
            # 对中招票：冲击窗口内按 -10%/日 连续跌停覆盖；窗口后已退市/停牌记 0
            if hit_local >= 0:
                if shock_start <= pos < shock_start + n_limit:
                    rd = rd.copy()
                    rd[hit_local] = -0.10
                elif pos >= shock_start + n_limit:
                    rd = rd.copy()
                    rd[hit_local] = 0.0
            rets[pos] = float(np.mean(rd))
        if 0 <= seg0 + 1 < len(rets): rets[seg0 + 1] -= cost
        t += hold
    return metrics(rets=rets).get('total_multiple', 0.0)


def avg_multiple(s, rate, start=None, seeds=7):
    vals = [run_shocked(s, rate, start=start, seed=sd) for sd in range(seeds)]
    return float(np.median(vals))


print('\n=== 温和压力：年化暴雷率 0% / 1% / 3% / 5%（多种子中位数，全期净值倍数）===')
hdr = '%-24s' % '策略'
for r in (0.0, 0.01, 0.03, 0.05):
    hdr += ' %10s' % ('%.0f%%' % (r * 100))
hdr += ' %12s' % '极端下界'
print(hdr)
for s in targets:
    row = '%-24s' % s['name'][:22]
    for r in (0.0, 0.01, 0.03, 0.05):
        row += ' %10s' % ('%.2f' % avg_multiple(s, r))
    row += ' %12s' % ('%.3f' % run_shocked(s, 0, extreme=True))
    print(row)

print('\n=== 样本外 2023-01-01 起 ===')
print(hdr)
for s in targets:
    row = '%-24s' % s['name'][:22]
    for r in (0.0, 0.01, 0.03, 0.05):
        row += ' %10s' % ('%.2f' % avg_multiple(s, r, start='2023-01-01'))
    row += ' %12s' % ('%.3f' % run_shocked(s, 0, extreme=True, start='2023-01-01'))
    print(row)
