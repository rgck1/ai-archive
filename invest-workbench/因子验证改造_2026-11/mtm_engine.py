# -*- coding: utf-8 -*-
"""
逐日盯市（mark-to-market）回测引擎
用于替代 v3_s02_deepdive.cs_flex 中"把持仓期总收益平摊成固定日收益"的错误做法。

核心差异：
- 旧做法：period = mean(20日收益)，daily = period^(1/20)-1，把同一个 daily 填进20个交易日。
  后果：日收益序列被人为平滑，std 缩小约 √20 倍，夏普虚高，最大回撤被隐藏。
- 新做法：每个交易日按真实收盘价计算持仓组合净值，逐日生成真实日收益序列。

执行口径：
- t 日收盘后算信号，t+1 日收盘价成交（与前版一致，无同日成交前视）
- 持有期 hold 个交易日，期间逐日盯市
- 成本在买入当日一次性扣除（bp/10000）
- 持仓期内标的停牌或DELETE_LIST时按前值持有
"""
import numpy as np
import pandas as pd
import sys, math
sys.path.insert(0, r'D:\我的工作台\02.输出区')

# 与 xbx_engine.metrics 保持同一常数，统一 √252
SHARPE_DAYS = 252.0
I0 = 60                     # 与 v3_s02_deepdive.I0 一致，预热60交易日


def cs_flex_mtm(p, spec, mask, cost_bp, start, signal_fn,
                end_i1=None, rng=None, verbose=False):
    """逐日盯市版 cs_flex，接口与 v3_s02_deepdive.cs_flex 对齐。

    返回 dict: rets/dates/n_trades/avg_picks/nav_method
    rets 为逐日真实收益序列（不再平摊），可直接送 xbx_engine.metrics。
    """
    hold = int(spec['params'].get('hold', 20))
    topn = int(spec['params'].get('topn', 10))
    asc = bool(spec['params'].get('ascending', False))
    i0 = max(int(np.searchsorted(p.dates, pd.Timestamp(start))), I0) if start else I0
    i1 = end_i1 if end_i1 is not None else p.T - hold - 2
    if i1 <= i0:
        return None

    cost = cost_bp / 10000.0
    c = np.asarray(p.d['c'], dtype=float)          # 复权收盘价 (T,N)，具体复权方式按数据源标注
    # 用 ret_clean 而非价格比值：bad_day（单日涨幅>25%或跌幅<-22%）已被置 NaN，
    # 停牌日亦为 NaN。逐日盯市必须显式按 0 处理，不能让异常跳变混入收益。
    rc = np.asarray(p.ret_clean, dtype=float)
    rets = np.zeros(i1 - i0 + 1)                    # 逐日收益，初始 0（空仓日）
    n_trades = 0
    picks_sum = 0
    min_liq = float(spec.get('filters', {}).get('min_avg_amount', 5e7))

    t = i0
    while t + hold + 1 <= i1:
        s = signal_fn(p, spec, t, rng=rng) if signal_fn is not None else None
        if s is None:
            t += 1
            continue
        ok = np.isfinite(s) & mask
        if ok.sum() < topn:
            t += 1
            continue
        order = (np.argsort(np.where(ok, s, np.inf), kind='stable') if asc
                 else np.argsort(-np.where(ok, s, -np.inf), kind='stable'))
        sel = np.asarray(order[:topn])

        buy_i = t + 1                               # t 收盘算信号，t+1 收盘成交
        sell_i = t + 1 + hold
        bp = c[buy_i, sel]
        good = np.isfinite(bp) & (bp > 0)
        good &= p.enough_age[buy_i, sel] & (~p.mv_bad[buy_i, sel])
        if min_liq > 0:
            good &= p.d['a'][buy_i, sel] >= min_liq * 0.5
        good &= ~p.has_bad(buy_i, sell_i + 1)[sel]
        good &= ~p.oneword_limit(buy_i, up=True)[sel]
        good &= ~p.oneword_limit(sell_i, up=False)[sel]
        held = sel[good]
        if len(held) == 0:
            t += hold
            continue

        # 逐日盯市：t+1 收盘建仓，从 t+2 开始产生收益，到 sell_i 共 hold 个日收益。
        # 边界修正：seg0=t-i0，正确区间为 [seg0+2, seg1+1)，即 hold 天，
        # 不含买入日 t+1 的收益（建仓在 t+1 收盘，当天收益不属于策略）。
        # 旧版错误地填 [seg0+1, seg1+1) 共 hold+1 天，多算一天且与相邻期重叠。
        seg0 = t - i0
        seg1 = sell_i - i0
        day_ret_start = seg0 + 2                    # t+2 对应的收益索引
        day_ret_end = min(seg1 + 1, len(rets))      # 到 sell_i 收盘，共 hold 天
        for pos in range(day_ret_start, day_ret_end):
            rr_day = rc[pos + i0, held]            # ret_clean 在第 pos+i0 个交易日
            rr_day = np.where(np.isfinite(rr_day), rr_day, 0.0)   # 停牌/bad_day 按 0
            rr_day = np.clip(rr_day, -0.11, 0.11)  # 极端值兜底
            rets[pos] = float(np.mean(rr_day))

        # 成本只在建仓日扣一次（buy_i = t+1，对应索引 seg0+1），禁止每天扣
        cost_pos = seg0 + 1
        if 0 <= cost_pos < len(rets):
            rets[cost_pos] -= cost

        n_trades += 1
        picks_sum += int(len(held))
        t += hold

    return {'rets': rets, 'dates': p.dates[i0:i0 + len(rets)],
            'n_trades': n_trades,
            'avg_picks': round(picks_sum / max(n_trades, 1), 2),
            'nav_method': 'daily_mark_to_market'}


def metrics_mtm(rets, dates=None):
    """逐日盯市口径的指标，夏普统一 √252，避免与 √244 混用。"""
    r = np.nan_to_num(np.asarray(rets, dtype=float), nan=0.0,
                      posinf=0.0, neginf=-0.99)
    r = np.clip(r, -0.99, 5.0)
    nav = np.cumprod(1.0 + r)
    if len(nav) < 2:
        return {}
    years = len(nav) / SHARPE_DAYS
    total = float(nav[-1] / nav[0])
    cagr = total ** (1.0 / years) - 1.0 if years > 0 and total > 0 else np.nan
    peak = np.maximum.accumulate(nav)
    mdd = float(np.min(nav / peak - 1.0))
    sd = float(np.std(r))
    sharpe = float(np.mean(r) / sd * math.sqrt(SHARPE_DAYS)) if sd > 0 else 0.0
    win = float(np.mean(r > 0)) if len(r) else 0.0
    downside = r[r < 0]
    sortino = (float(np.mean(r) / np.std(downside) * math.sqrt(SHARPE_DAYS))
               if len(downside) > 1 and np.std(downside) > 0 else 0.0)
    return {'total_multiple': round(total, 4),
            'cagr': round(float(cagr), 6),
            'mdd': round(mdd, 6),
            'sharpe': round(sharpe, 4),
            'sortino': round(sortino, 4),
            'daily_winrate': round(win, 4),
            'n_days': int(len(nav)),
            'years': round(years, 2),
            'nav_method': 'daily_mark_to_market'}


def cross_section_mtm(p, spec, exec_mode='close', cost_bp=20.0,
                      start=None, end=None, mask=None, signal_fn=None,
                      seed_shift=0, verbose=False):
    """通用逐日盯市截面回测，替代以下四处平摊实现：
      - xbx_engine.cross_section
      - v3_s02_deepdive.cs_flex
      - v3_perm.cross_section_masked
      - v3_perm_check.cross_section_masked

    接口兼容四种调用：exec_mode 支持 open/close，mask 可选，signal_fn 可选。
    返回 rets/nav/dates/n_trades/avg_picks/nav_method。
    """
    from xbx_engine import signal as default_signal

    hold = int(spec.get('params', {}).get('hold', 5))
    topn = int(spec.get('params', {}).get('topn', 20))
    asc = bool(spec.get('params', {}).get('ascending', False))
    i0 = int(np.searchsorted(p.dates, pd.Timestamp(start))) if start else 60
    i1 = (int(np.searchsorted(p.dates, pd.Timestamp(end)))
          if end else p.T - hold - 2)
    i0 = max(i0, I0)
    i1 = min(i1, p.T - hold - 2)
    if i1 <= i0:
        return None

    cost = cost_bp / 10000.0
    c, o = p.d['c'], p.d['o']
    rc = np.asarray(p.ret_clean, dtype=float)
    if mask is None:
        mask = np.ones(p.N, dtype=bool)
    rets = np.zeros(i1 - i0 + 1)
    n_trades = 0
    picks_sum = 0
    t = i0

    sigfn = signal_fn if signal_fn is not None else default_signal
    while t + hold + 1 <= i1:
        s = sigfn(p, spec, t)
        ok = np.isfinite(s) & mask
        if ok.sum() < topn:
            t += 1
            continue
        order = (np.argsort(np.where(ok, s, np.inf), kind='stable') if asc
                 else np.argsort(-np.where(ok, s, -np.inf), kind='stable'))
        sel = np.asarray(order[:topn])
        buy_i, sell_i = t + 1, t + 1 + hold
        bp = o[buy_i, sel] if exec_mode == 'open' else c[buy_i, sel]
        sp = o[sell_i, sel] if exec_mode == 'open' else c[sell_i, sel]
        good = np.isfinite(bp) & np.isfinite(sp) & (bp > 0)
        good &= p.enough_age[buy_i, sel] & (~p.mv_bad[buy_i, sel])
        min_liq = float(spec.get('filters', {}).get('min_avg_amount', 5e7))
        if min_liq > 0:
            good &= p.d['a'][buy_i, sel] >= min_liq * 0.5
        good &= ~p.has_bad(buy_i, sell_i + 1)[sel]
        good &= ~p.oneword_limit(buy_i, up=True)[sel]
        good &= ~p.oneword_limit(sell_i, up=False)[sel]
        if exec_mode == 'open':
            good &= ~(bp >= c[buy_i - 1, sel] * 1.098)
            good &= ~(sp <= c[sell_i - 1, sel] * 0.902)
        held = sel[good]
        if len(held) == 0:
            t += hold
            continue

        seg0 = t - i0
        seg1 = sell_i - i0
        # 逐日盯市：t+2 到 sell_i 共 hold 个日收益，不含建仓日 t+1
        for pos in range(seg0 + 2, min(seg1 + 1, len(rets))):
            rr_day = rc[pos + i0, held]
            rr_day = np.where(np.isfinite(rr_day), rr_day, 0.0)
            rr_day = np.clip(rr_day, -0.11, 0.11)
            rets[pos] = float(np.mean(rr_day))
        # 成本只在建仓日扣一次
        cost_pos = seg0 + 1
        if 0 <= cost_pos < len(rets):
            rets[cost_pos] -= cost

        n_trades += 1
        picks_sum += int(len(held))
        t += hold

    return {'rets': rets, 'nav': np.cumprod(1.0 + rets),
            'dates': p.dates[i0:i0 + len(rets)],
            'n_trades': n_trades,
            'avg_picks': round(picks_sum / max(n_trades, 1), 2),
            'avg_turnover': 2.0,
            'nav_method': 'daily_mark_to_market'}
