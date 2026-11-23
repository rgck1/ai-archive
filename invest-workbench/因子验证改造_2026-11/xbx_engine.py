# -*- coding: utf-8 -*-
"""
邢不行全视频策略 · 统一独立回测引擎
所有策略共用同一套数据、成交口径、成本与检验，保证结论可比。

数据：
  - 个股面板 D:/我的工作台/量化/w/_stock_panel.pkl (2018-01-02~2026-10-08, 2061只)
  - 申万一级行业指数 / 沪深300: 02.输出区/轮动验证_data/
关键方法：
  - 同时跑 close / open 两种成交口径，剥离 A 股「日内正、隔夜负」的口径偏差
  - 默认双边 20bp 成本；零成本仅作对照
  - 样本内 2018-2022 / 样本外 2023-2026 分段
  - 随机选股安慰剂对照
"""
import os, json, math, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore', category=RuntimeWarning)

BASE = r'D:\我的工作台\02.输出区'
PANEL_PKL = r'D:\我的工作台\量化\w\_stock_panel.pkl'
SW_CSV = BASE + r'\轮动验证_data\sw1_daily.csv'
HS_CSV = BASE + r'\轮动验证_data\hs300_daily.csv'
OUT_JSON = BASE + r'\xbx_results.json'

TRADING_DAYS = 244.0


class Panel:
    PRICE_COLS = ('o', 'h', 'l', 'c', 'cn')

    def __init__(self, path=PANEL_PKL):
        d, meta = pd.read_pickle(path)
        self.d = {}
        for k, v in d.items():
            arr = np.asarray(v.values)
            if arr.dtype == np.bool_:
                self.d[k] = arr.astype(bool)
                continue
            arr = arr.astype(np.float64)
            arr[~np.isfinite(arr)] = np.nan
            if k in self.PRICE_COLS:
                arr[arr <= 0] = np.nan
            self.d[k] = arr
        self.dates = pd.DatetimeIndex(meta['dates'])
        self.codes = list(meta['codes'])
        self.names = meta['names']
        self.T, self.N = self.d['c'].shape
        self.valid = self.d['valid']
        self.listed = self.d['listed']
        with np.errstate(divide='ignore', invalid='ignore'):
            self.ret_cc = self._ratio('c', 'c', 1)
            self.ret_oc = self.d['c'] / self.d['o'] - 1.0
            self.ret_co = self.d['o'] / np.vstack(
                [np.full((1, self.N), np.nan), self.d['c'][:-1]]) - 1.0
        for nm in ('ret_cc', 'ret_oc', 'ret_co'):
            x = getattr(self, nm)
            x[~np.isfinite(x)] = np.nan
            setattr(self, nm, x)
        # --- 数据清洗：A股涨跌停约束下的异常跳变视为数据错误 ---
        r = self.ret_cc
        self.bad_day = np.isfinite(r) & ((r > 0.25) | (r < -0.22))
        self.bad_cs = np.cumsum(self.bad_day.astype(np.int32), axis=0)
        self.ret_clean = np.where(self.bad_day, np.nan, r)
        # 上市满 60 交易日才允许入选（规避新股连板 / 前复权拼接异常）
        first_listed = np.argmax(self.listed, axis=0)
        self.enough_age = (np.arange(self.T)[:, None] - first_listed[None, :]) >= 60
        self.mv_bad = ~(np.isfinite(self.d['mv']) & (self.d['mv'] > 0))
        # 常用派生矩阵（进入缓存体系）
        self.d['lu'] = (self.ret_clean > 0.095).astype(np.float64)
        self.d['ld'] = (self.ret_clean < -0.095).astype(np.float64)
        self.d['amp'] = (self.d['h'] - self.d['l']) / np.where(
            self.d['c'] > 0, self.d['c'], np.nan)
        self.d['intraday'] = self.ret_oc
        self.d['ret_clean'] = self.ret_clean
        self._roll = {}
        print('CLEAN bad_days=%d (%.3f%%), mv_bad=%d, enough_age_last=%d' % (
            int(self.bad_day.sum()), 100.0 * self.bad_day.mean(),
            int(self.mv_bad.sum()), int(self.enough_age[-1].sum())), flush=True)

    def roll(self, key, win, op='mean'):
        """带缓存的滚动统计，避免每个调仓日重算整张面板。"""
        k = (key, win, op)
        if k not in self._roll:
            src = self.ret_clean if key == 'ret_clean' else self.d.get(key)
            if src is None:
                src = getattr(self, key, None)
            if src is None:
                raise KeyError(key)
            self._roll[k] = rolling(src, win, op)
        return self._roll[k]

    def has_bad(self, t0, t1):
        """[t0, t1) 区间内是否出现异常跳变。"""
        a = self.bad_cs[t1 - 1] if t1 > 0 else np.zeros(self.N, dtype=np.int32)
        b = self.bad_cs[t0 - 1] if t0 > 0 else np.zeros(self.N, dtype=np.int32)
        return (a - b) > 0

    def oneword_limit(self, t, up=True):
        """一字板：最高=最低 且 达到涨跌停幅度。"""
        o, h, l, c = self.d['o'], self.d['h'], self.d['l'], self.d['c']
        flat = np.isfinite(h[t]) & np.isfinite(l[t]) & (np.abs(h[t] - l[t]) < 1e-6)
        if up:
            return flat & (self.ret_clean[t] > 0.095)
        return flat & (self.ret_clean[t] < -0.095)

    def _ratio(self, num, den, lag):
        a, b = self.d[num], self.d[den]
        out = np.full_like(a, np.nan)
        out[lag:] = a[lag:] / b[:-lag] - 1.0
        return out

    def px(self, k):
        return self.d[k]


def load_sw():
    df = pd.read_csv(SW_CSV)
    df['date'] = pd.to_datetime(df['date'])
    piv = {}
    for col in ('open', 'close', 'high', 'low'):
        piv[col] = df.pivot(index='date', columns='code', values=col).sort_index()
    return piv, df


def load_hs():
    df = pd.read_csv(HS_CSV)
    df['date'] = pd.to_datetime(df['date'])
    return df.set_index('date').sort_index()


def metrics(nav=None, dates=None, rets=None):
    """nav 与 rets 二选一；rets 为日收益序列时自动构造净值。"""
    if nav is None:
        if rets is None:
            return {}
        r = np.asarray(rets, dtype=float)
        r = np.nan_to_num(r, nan=0.0, posinf=0.0, neginf=-0.99)
        r = np.clip(r, -0.99, 5.0)
        nav = np.cumprod(1.0 + r)
    else:
        nav = np.asarray(nav, dtype=float)
        nav = nav[np.isfinite(nav)]
        r = np.diff(nav) / np.where(nav[:-1] > 0, nav[:-1], np.nan)
    if len(nav) < 2 or not np.all(np.isfinite(nav)):
        return {}
    years = len(nav) / TRADING_DAYS
    total = nav[-1] / nav[0] if nav[0] > 0 else np.nan
    cagr = total ** (1.0 / years) - 1.0 if years > 0 and total > 0 else np.nan
    peak = np.maximum.accumulate(nav)
    mdd = float(np.min(nav / peak - 1.0))
    rr = r[np.isfinite(r)]
    sharpe = float(np.mean(rr) / np.std(rr) * math.sqrt(TRADING_DAYS)) if len(rr) > 1 and np.std(rr) > 0 else 0.0
    win = float(np.mean(rr > 0)) if len(rr) else 0.0
    return {
        'total_multiple': round(float(total), 4),
        'cagr': round(float(cagr), 6),
        'mdd': round(mdd, 6),
        'sharpe': round(sharpe, 4),
        'daily_winrate': round(win, 4),
        'n_days': int(len(nav)),
        'years': round(years, 2),
    }


# ---------------- 信号 ----------------
def rolling(arr, win, op='mean'):
    T, N = arr.shape
    out = np.full((T, N), np.nan)
    if op == 'mean':
        cs = np.nancumsum(np.nan_to_num(arr, nan=0.0), axis=0)
        cnt = np.cumsum(np.isfinite(arr).astype(float), axis=0)
        out[win:] = (cs[win:] - cs[:-win]) / np.maximum(cnt[win:] - cnt[:-win], 1)
    elif op == 'std':
        for t in range(win, T):
            out[t] = np.nanstd(arr[t - win:t], axis=0)
    elif op == 'max':
        for t in range(win, T):
            out[t] = np.nanmax(arr[t - win:t], axis=0)
    elif op == 'min':
        for t in range(win, T):
            out[t] = np.nanmin(arr[t - win:t], axis=0)
    elif op == 'sum':
        cs = np.nancumsum(np.nan_to_num(arr, nan=0.0), axis=0)
        out[win:] = cs[win:] - cs[:-win]
    return out


def rank_pct(v):
    """横截面百分位：最小值 0，最大值 1；NaN 保持 NaN。"""
    out = np.full(v.shape, np.nan, dtype=float)
    ok = np.isfinite(v)
    idx = np.where(ok)[0]
    if len(idx) < 2:
        return out
    order = np.argsort(v[idx], kind='stable')
    rk = np.empty(len(idx), dtype=float)
    rk[order] = np.arange(len(idx), dtype=float) / (len(idx) - 1)
    out[idx] = rk
    return out


def signal(p, spec, t):
    """返回 t 日收盘后可计算的横截面打分；NaN 表示不参与排序。"""
    st = spec['signal_type']
    prm = spec.get('params', {})
    win = int(prm.get('win', 20))
    c, o, h, l = p.d['c'], p.d['o'], p.d['h'], p.d['l']
    if st == 'momentum':
        s = c[t] / np.where(c[t - win] > 0, c[t - win], np.nan) - 1.0
    elif st == 'reversal':
        s = -(c[t] / np.where(c[t - win] > 0, c[t - win], np.nan) - 1.0)
    elif st == 'turnover':
        s = p.roll('tr', win, 'mean')[t]
    elif st == 'amount':
        s = p.roll('a', win, 'mean')[t]
    elif st == 'mv':
        s = p.d['mv'][t]
    elif st == 'price':
        s = c[t]
    elif st == 'volatility':
        s = p.roll('ret_clean', win, 'std')[t]
    elif st == 'ma_ratio':
        ma = p.roll('c', win, 'mean')[t]
        s = c[t] / np.where(ma > 0, ma, np.nan) - 1.0
    elif st == 'new_high':
        mx = p.roll('c', win, 'max')[t]
        s = c[t] / np.where(mx > 0, mx, np.nan) - 1.0
    elif st == 'limitup_recent':
        s = p.roll('lu', win, 'sum')[t]
    elif st == 'limitdown_recent':
        s = p.roll('ld', win, 'sum')[t]
    elif st == 'amplitude':
        s = p.roll('amp', win, 'mean')[t]
    elif st == 'gap':
        s = p.ret_co[t]
    elif st == 'intraday':
        s = p.roll('intraday', win, 'mean')[t]
    elif st == 'lucky_number':
        # 股价末位数字「吉利」程度：8/6 计 1，4 计 -1
        last = np.floor(np.mod(c[t], 10)).astype(float)
        s = np.where(np.isin(last, [8, 6]), 1.0, np.where(last == 4, -1.0, 0.0))
    elif st == 'low_price':
        s = -c[t]
    elif st == 'kdj_j':
        s = kdj_j(p, t, win)
    elif st == 'rsi':
        s = rsi(p, t, win)
    elif st == 'kline_star':
        s = kline_star(p, t, prm.get('pattern', 'morning'))
    elif st == 'rank_sum':
        # 多因子等权排名合成：factors=[{key,asc,weight}, ...]，asc=True 表示偏好小值
        s = np.full(p.N, np.nan)
        acc = np.zeros(p.N)
        cnt = np.zeros(p.N)
        for f in prm.get('factors', []):
            key = f['key']
            arr = p.d.get(key)
            if arr is None:
                arr = getattr(p, key, None)
            if arr is None:
                continue
            v = arr[t] if arr.ndim == 2 else arr
            rk = rank_pct(np.asarray(v, dtype=float))
            if f.get('asc'):
                rk = 1.0 - rk
            w = float(f.get('weight', 1.0))
            ok = np.isfinite(rk)
            acc[ok] += rk[ok] * w
            cnt[ok] += w
        good = cnt > 0
        s[good] = acc[good] / cnt[good]
    elif st == 'random':
        rng = np.random.default_rng(int(prm.get('seed', 0)) * 10000 + t)
        s = rng.random(p.N)
    else:
        raise ValueError('unknown signal_type: ' + st)
    # 修复（2026-11-11）：强制独立副本，切断别名污染。
    # 根因：mv/price 等分支把 p.d[k][t] 的行视图赋给 s；np.asarray 对已是
    # float64 的数组不拷贝，后续 s[...]=np.nan 就地写穿透回写 p.d 原矩阵，
    # 导致同一 Panel 实例上先跑 mv/price 类策略会把市值/价格矩阵永久挖成 NaN，
    # 后续依赖 mv/c 的横截面策略结果虚高且不可复现。改为 copy=True 后，
    # 后续所有就地写只作用于长度 N 的独立副本（约 46KB），开销可忽略。
    s = np.array(s, dtype=float, copy=True)
    s[~np.isfinite(s)] = np.nan
    s[~p.valid[t]] = np.nan
    s[~p.enough_age[t]] = np.nan
    s[p.mv_bad[t]] = np.nan
    w = max(win, 20)
    s[p.has_bad(max(0, t - w), t + 1)] = np.nan
    # 真实可交易约束：默认要求近20日日均成交额>=5000万，且当日成交额不枯竭
    min_liq = float(spec.get('filters', {}).get('min_avg_amount', 5e7))
    if min_liq > 0:
        avg = p.roll('a', 20, 'mean')[t]
        s[~(avg >= min_liq)] = np.nan
        s[~(p.d['a'][t] >= min_liq * 0.5)] = np.nan
    return apply_filters(p, spec, t, s)


def apply_filters(p, spec, t, s):
    f = spec.get('filters', {})
    # 价格类筛选用不复权真实价（成交额/成交量），避免后复权价失真
    c = p.d['cn'][t] if 'cn' in p.d else p.d['c'][t]
    if f.get('exclude_limitup_today'):
        s[p.ret_cc[t] > 0.095] = np.nan
    if f.get('exclude_limitdown_today'):
        s[p.ret_cc[t] < -0.095] = np.nan
    if f.get('min_amount') is not None:
        s[p.d['a'][t] < float(f['min_amount'])] = np.nan
    if f.get('max_price') is not None:
        s[c > float(f['max_price'])] = np.nan
    if f.get('min_price') is not None:
        s[c < float(f['min_price'])] = np.nan
    if f.get('mv_percentile') is not None:
        mv = p.d['mv'][t]
        finite_mv = mv[np.isfinite(mv)]
        if finite_mv.size:
            q = np.nanpercentile(finite_mv, float(f['mv_percentile']))
            side = f.get('mv_side', 'low')
            mask = (mv <= q) if side == 'low' else (mv >= q)
            s[~mask] = np.nan
    return s


def kdj_j(p, t, win=9):
    c = p.d['c'][t]
    lo = p.roll('l', win, 'min')[t]
    hi = p.roll('h', win, 'max')[t]
    return (c - lo) / np.where(hi - lo > 0, hi - lo, np.nan) * 100.0


def rsi(p, t, win=14):
    if 'rup' not in p.d:
        r = p.ret_clean
        p.d['rup'] = np.where(np.isfinite(r) & (r > 0), r, 0.0)
        p.d['rdn'] = np.where(np.isfinite(r) & (r < 0), -r, 0.0)
    u = p.roll('rup', win, 'mean')[t]
    d = p.roll('rdn', win, 'mean')[t]
    return 100.0 - 100.0 / (1.0 + u / np.where(d > 0, d, np.nan))


def kline_star(p, t, pattern='morning'):
    """简化星线形态打分：实体、上下影线比例。"""
    o, h, l, c = p.d['o'][t], p.d['h'][t], p.d['l'][t], p.d['c'][t]
    body = np.abs(c - o)
    rng = np.where(h - l > 0, h - l, np.nan)
    lower = (np.minimum(o, c) - l) / rng
    upper = (h - np.maximum(o, c)) / rng
    small = body / rng
    if pattern in ('morning', 'evening'):
        s = lower * (1 - small)
    elif pattern == 'shooting':
        s = upper * (1 - small)
    elif pattern == 'hammer':
        s = lower * (1 - small)
    else:
        s = small
    return s


# ---------------- 回测 ----------------
def cross_section(p, spec, exec_mode='close', cost_bp=20.0, start=None, end=None,
                  seed_shift=0):
    """截面选股：调仓日 t 收盘算信号 -> 建仓 -> 持有 hold 日 -> 平仓。"""
    hold = int(spec.get('params', {}).get('hold', 5))
    topn = int(spec.get('params', {}).get('topn', 20))
    asc = bool(spec.get('params', {}).get('ascending', False))
    i0 = int(np.searchsorted(p.dates, pd.Timestamp(start))) if start else 60
    i1 = int(np.searchsorted(p.dates, pd.Timestamp(end))) if end else p.T - hold - 2
    i0 = max(i0, 60)
    i1 = min(i1, p.T - hold - 2)
    if i1 <= i0:
        return None
    cost = cost_bp / 10000.0
    c, o = p.d['c'], p.d['o']
    rets = np.zeros(i1 - i0 + 1)
    nav = np.ones(i1 - i0 + 1)
    n_trades = 0
    turnovers = []
    t = i0
    while t + hold + 1 <= i1:
        s = signal(p, spec, t)
        ok = np.isfinite(s)
        if ok.sum() < topn:
            t += 1
            continue
        if asc:
            order = np.argsort(np.where(ok, s, np.inf), kind='stable')
        else:
            order = np.argsort(-np.where(ok, s, -np.inf), kind='stable')
        sel = np.asarray(order[:topn])
        buy_i = t + 1          # 信号 t 日收盘后产生，两种口径统一在 t+1 成交，杜绝前视
        sell_i = buy_i + hold
        bp = o[buy_i, sel] if exec_mode == 'open' else c[buy_i, sel]
        sp = o[sell_i, sel] if exec_mode == 'open' else c[sell_i, sel]
        # 剔除无法成交：缺价、上市不足60日、持有期异常跳变、一字涨跌停
        good = np.isfinite(bp) & np.isfinite(sp) & (bp > 0)
        good &= p.enough_age[buy_i, sel] & ~p.mv_bad[buy_i, sel]
        min_liq = float(spec.get('filters', {}).get('min_avg_amount', 5e7))
        if min_liq > 0:
            good &= p.d['a'][buy_i, sel] >= min_liq * 0.5
        good &= ~p.has_bad(buy_i, sell_i + 1)[sel]
        good &= ~p.oneword_limit(buy_i, up=True)[sel]
        good &= ~p.oneword_limit(sell_i, up=False)[sel]
        if exec_mode == 'open':
            prev_c = c[buy_i - 1, sel]
            good &= ~(bp >= prev_c * 1.098)
            good &= ~(sp <= c[sell_i - 1, sel] * 0.902)
        if good.sum() == 0:
            t += hold
            continue
        n_trades += 1
        turnovers.append(2.0)
        # [MTM 修复 2026-11-22] 逐日盯市替代平摊收益。
        # 旧实现把 period 平摊成固定 daily，使夏普虚高约 √hold 倍并隐藏回撤。
        # 新实现：t+2 到 sell_i 共 hold 个日收益，用 ret_clean，停牌/bad_day 记 0，
        # 成本只在建仓日 seg0+1 扣一次。
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
    nav = np.cumprod(1.0 + rets)
    return {'nav': nav, 'rets': rets, 'dates': p.dates[i0:i0 + len(rets)],
            'n_trades': n_trades, 'avg_turnover': float(np.mean(turnovers)) if turnovers else 0.0}


def benchmark_equal(p, start=None, end=None, exec_mode='close'):
    i0 = int(np.searchsorted(p.dates, pd.Timestamp(start))) if start else 60
    i1 = int(np.searchsorted(p.dates, pd.Timestamp(end))) if end else p.T - 2
    c, o = p.d['c'], p.d['o']
    src = p.ret_clean if exec_mode == 'close' else p.ret_oc
    blk = src[i0:i1 + 1]
    cnt = np.sum(np.isfinite(blk), axis=1)
    r = np.nan_to_num(np.nansum(blk, axis=1), nan=0.0) / np.maximum(cnt, 1)
    r = np.clip(np.nan_to_num(r, nan=0.0, posinf=0.0, neginf=0.0), -0.5, 0.5)
    return np.cumprod(1 + r), r


def run_all(specs, panel, cost_bp=20.0, in_end='2022-12-31', out_start='2023-01-01'):
    out = {}
    for sp in specs:
        sid = sp['id']
        rec = {'name': sp.get('name'), 'video': sp.get('video'),
               'category': sp.get('category'), 'params': sp.get('params', {}),
               'claim': sp.get('claim', ''), 'verdict': sp.get('verdict', '')}
        try:
            for mode in ('close', 'open'):
                full = cross_section(panel, sp, exec_mode=mode, cost_bp=cost_bp)
                zero = cross_section(panel, sp, exec_mode=mode, cost_bp=0.0)
                si = cross_section(panel, sp, exec_mode=mode, cost_bp=cost_bp, end=in_end)
                so = cross_section(panel, sp, exec_mode=mode, cost_bp=cost_bp, start=out_start)
                rec[mode] = {
                    'cost': metrics(None, rets=full['rets']) if full else {},
                    'zero': metrics(None, rets=zero['rets']) if zero else {},
                    'in_sample': metrics(None, rets=si['rets']) if si else {},
                    'out_sample': metrics(None, rets=so['rets']) if so else {},
                    'n_trades': full['n_trades'] if full else 0,
                }
        except Exception as e:
            rec['error'] = repr(e)[:200]
        out[sid] = rec
        print('DONE', sid, sp.get('name', '')[:28],
              'close_cost', rec.get('close', {}).get('cost', {}).get('total_multiple'),
              'open_zero', rec.get('open', {}).get('zero', {}).get('total_multiple'), flush=True)
    return out


if __name__ == '__main__':
    p = Panel()
    print('PANEL', p.T, p.N, p.dates[0].date(), p.dates[-1].date())
    bn, br = benchmark_equal(p)
    print('BENCH_EQUAL_CLOSE', metrics(None, rets=br))
    demo = {'id': 'DEMO', 'name': '小市值月度', 'signal_type': 'mv',
            'params': {'win': 20, 'topn': 20, 'hold': 20, 'ascending': True}}
    for mode in ('close', 'open'):
        for cb in (0, 20):
            r = cross_section(p, demo, exec_mode=mode, cost_bp=cb)
            print('DEMO', mode, cb, metrics(None, rets=r['rets']), 'trades', r['n_trades'])
