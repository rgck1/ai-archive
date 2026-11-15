# -*- coding: utf-8 -*-
"""策略实验室：以页面标的池为单位，跑现有方案与公开策略，输出统一口径的对比结果。

设计要点：
1. 直接 import 同目录的 server 模块，复用 _fetch_kline_dc（腾讯前复权日线）、
   _bt_metrics_at、_bt_weights、_std。现有 8 个方案的结果与 /api/backtest 同口径。
2. 公开策略只在本文件里新增权重规则，不改动 api_backtest 的既有行为。
3. 允许权重和小于 1，未配置部分按现金 0 收益处理，与工作台「余额留现金」口径一致。
4. 结果写入 data/strategy_lab.json，由 /api/strategy_lab 只读返回。

本地可用 --selftest 用合成行情验证逻辑，不访问网络。
"""
import datetime
import json
import math
import os
import re
import sys
import time
import urllib.request

os.environ.setdefault("XQ_CACHE_DIR", "/opt/invest-workbench/data")
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import server as S  # noqa: E402

DATA = S.CACHE_DIR
OUT = os.path.join(DATA, "strategy_lab.json")

# v46：回溯窗口可配置（环境变量 LAB_DAYS 或 --days N）。
# 2026-11-07 用户拍板改为「五年为单位择优收录」：默认 1250 交易日 ≈ 5 年（覆盖一轮较完整牛熊），
# 上限放开到 2000。旧版 500（≈2 年）/ 250（≈1 年）样本太短，无法覆盖一轮完整牛熊。
DAYS = 1250
try:
    DAYS = int(os.environ.get("LAB_DAYS", str(DAYS)))
except (TypeError, ValueError):
    DAYS = 1250
if "--days" in sys.argv:
    try:
        DAYS = int(sys.argv[sys.argv.index("--days") + 1])
    except (IndexError, ValueError):
        pass
DAYS = max(60, min(DAYS, 2000))
REBAL = 20
CAPITAL = 100000.0
CAP = 0.20
WARM = 61
# v47 第 11 项：用户拍板「允许不满仓 / 留现金」。
# 旧版对 8 个现有方案一律「迭代注水回摊 + 归一化到 100%」，N≤5 只票时
# cap 被抬到 1/N，数学上唯一解就是等权，signal/copy 的真实权重被抹平。
# 现在：等权方案仍满仓作为对照基准，其余方案只向下削顶、余额留现金。
# LAB_ALLOW_CASH=0 可复现旧口径。
ALLOW_CASH = str(os.environ.get("LAB_ALLOW_CASH", "1")).lower() not in ("0", "false", "no")
# v47 第 12 项：signal/copy 按再平衡时点读取 consensus_history 快照，消除前视偏差。
ASOF_REPLAY = str(os.environ.get("LAB_ASOF_REPLAY", "1")).lower() not in ("0", "false", "no")

# --- 2026-11-07（续）：真实交易成本与市场摩擦（均可环境变量覆盖，便于做敏感性分析）---
# A 股单边成本假设：
#   佣金 COMMISSION：默认万 2.5（0.00025），单笔最低 5 元（COMMISSION_MIN）；
#   印花税 STAMP：卖出单边万 5（0.0005，2023-08-28 起减半，且仅卖方）；
#   滑点 SLIPPAGE：双边各 0.1%（0.001），保守估计（市价单冲击 + 买卖价差）；
#   过户费 TRANSFER：双边各万 0.1（0.00001），并入佣金口径。
COMMISSION = float(os.environ.get("LAB_COMMISSION", "0.00025"))
COMMISSION_MIN = float(os.environ.get("LAB_COMMISSION_MIN", "5.0"))
STAMP = float(os.environ.get("LAB_STAMP", "0.0005"))
SLIPPAGE = float(os.environ.get("LAB_SLIPPAGE", "0.001"))
TRANSFER = float(os.environ.get("LAB_TRANSFER", "0.00001"))
# 样本内外切分：前 IS_RATIO 用于择优、后 (1-IS_RATIO) 做样本外验证；OOS 至少保留 OOS_MIN_DAYS 天。
IS_RATIO = float(os.environ.get("LAB_IS_RATIO", "0.6"))
OOS_MIN_DAYS = 250

# 现有 /api/backtest 的 8 个配置方案
EXISTING = [
    ("equal", "等权", "工作台现有配置方案"),
    ("signal", "信号强度", "工作台现有配置方案（v46：共识广度 + 当期技术信号命中数加权，不再等权）"),
    ("copy", "等比缩放", "工作台现有配置方案（v46：原组合权重合计等比缩放至 100%，不再等权）"),
    ("invvol", "波动率倒数", "工作台现有配置方案"),
    ("coresat", "核心-卫星", "工作台现有配置方案"),
    ("score", "四维打分", "工作台现有配置方案"),
    ("drawdown", "回撤预算", "工作台现有配置方案"),
    ("mom", "动量加权", "工作台现有配置方案"),
]
EXISTING_KEYS = set(k for k, _, _ in EXISTING)
DEGENERATE = set()   # v46：signal/copy 已有真实权重源，纳入排名比较

# 网上收集、有公开定义且可用日线复现的策略（v47 初版 7 个；2026-11-07 扩到 18 个，新增 11 个技术指标/因子类）。
PUBLIC = [
    ("buy_hold", "买入持有", "Quant Wiki：Buy & Hold 静态策略，期间不再平衡",
     "https://quant-wiki.com/start/quant_trader/"),
    ("sma200", "10月均线择时", "Mebane Faber 2007《A Quantitative Approach to Tactical Asset Allocation》：价格站上 10 月（≈200 日）均线才持有",
     "https://dualmomentumsystems.com/strategies/gtaa-agg3"),
    ("dual_mom", "双动量", "Gary Antonacci Dual Momentum；相对动量选最强、绝对动量为负转现金",
     "https://quantengines.com/blog/tactical-asset-allocation"),
    ("mom_rot", "动量轮动Top5", "Quant Buffet momentum_rotation；每月持有近期最强前 5 名",
     "https://quantbuffet.com/zh/learn/classic-strategies"),
    ("mean_rev", "均值回归", "Quant Buffet mean_reversion；买入 20 日超跌（z-score 为负）标的",
     "https://quantbuffet.com/zh/learn/classic-strategies"),
    ("vol_target", "目标波动率", "Quant Buffet vol_target / 次方量化风险平价：按成分波动缩放总体仓位",
     "https://www.cifangquant.com/docs/common-etf-quant-strategies"),
    ("sixty_forty", "60/40 股债", "次方量化：60% 股票 + 40% 债券的战略配置（股票池无债券，本实验室跳过）",
     "https://www.cifangquant.com/docs/common-etf-quant-strategies"),
    # --- 2026-11-07 新增 11 个，均有公开权威出处，可用日线指标复现 ---
    ("risk_parity", "风险平价", "Risk Parity（Bridgewater All Weather 思路）：按波动率倒数分配权重，使各成分风险贡献相等",
     "https://www.investopedia.com/terms/r/risk-parity.asp"),
    ("low_vol", "低波动异象", "Low-Volatility Anomaly：买入历史波动率最低的约 1/3 标的并等权，实证中低波组合长期跑赢高波",
     "https://en.wikipedia.org/wiki/Low-volatility_anomaly"),
    ("mom120", "12月动量", "12-Month Momentum：持有过去 120 个交易日收益最高的约半数标的（Carhart 动量因子）",
     "https://www.investopedia.com/terms/m/momentum.asp"),
    ("rsi_rev", "RSI均值回归", "Wilder RSI(14) 低于 30 视为超卖，按超卖程度加权买入等待反弹",
     "https://www.investopedia.com/terms/r/rsi.asp"),
    ("macd_cross", "MACD金叉", "MACD 柱（快线减慢线）转正视为短期动能转强，等权持有金叉标的",
     "https://www.investopedia.com/terms/m/macd.asp"),
    ("donchian", "唐奇安突破", "Donchian / Turtle Trading：价格创 20 日新高买入（海龟交易法则）",
     "https://en.wikipedia.org/wiki/Turtle_trading"),
    ("boll_rev", "布林带反转", "Bollinger Bands：价格跌破下轨（20 日均值 -2σ）视为超跌，按偏离度加权买入",
     "https://www.investopedia.com/terms/b/bollingerbands.asp"),
    ("sma_cross", "均线金叉", "Moving Average Crossover：20 日 SMA 上穿 50 日 SMA 视为中期转多，等权持有金叉标的",
     "https://www.investopedia.com/terms/m/movingaverage.asp"),
    ("trend_filter", "趋势过滤+等权", "多数成分站上 200 日均线才持有、否则空仓避险（Faber 战术资产配置思路）",
     "https://dualmomentumsystems.com/strategies/gtaa-agg3"),
    ("rel_strength", "相对强度", "Relative Strength（O'Shaughnessy 式）：持有 120 日相对涨幅最强的前 5 只",
     "https://www.investopedia.com/terms/r/relativestrength.asp"),
    ("breakout", "55日通道突破", "Channel Breakout：价格创 55 日新高视为趋势启动，等权持有突破标的",
     "https://en.wikipedia.org/wiki/Breakout_(technical_analysis)"),
]
PUBLIC_KEYS = set(k for k, _, _, _ in PUBLIC)
SKIPPED = {"sixty_forty"}
ALL = [(k, n, o, "") for k, n, o in EXISTING] + PUBLIC
NAME = {k: n for k, n, _, _ in ALL}
ORIGIN = {k: o for k, _, o, _ in ALL}
SOURCE_URL = {k: u for k, _, _, u in ALL}

# 跟单推荐页候选池的兜底快照（与前端 onBacktest 的取法一致：可买、未超一手、前 10 只）
FALLBACK_RECS = ["601872", "000333", "601137", "600825", "002487",
                 "600026", "601899", "000807", "000933", "601975"]
FALLBACK_RECS_AT = "2026-11-06 23:20"

SOURCES = [
    {"name": "Quant Wiki 中文量化百科（交易风格与风险平价）",
     "url": "https://quant-wiki.com/start/quant_trader/"},
    {"name": "Quant Buffet 经典策略家族（动量轮动、趋势、均值回归、目标波动）",
     "url": "https://quantbuffet.com/zh/learn/classic-strategies"},
    {"name": "Mebane Faber 2007 战术资产配置（10 月均线 / 趋势过滤）",
     "url": "https://dualmomentumsystems.com/strategies/gtaa-agg3"},
    {"name": "Gary Antonacci 双动量与趋势跟踪综述",
     "url": "https://quantengines.com/blog/tactical-asset-allocation"},
    {"name": "次方量化：常见 ETF 量化策略（目标波动、60/40）",
     "url": "https://www.cifangquant.com/docs/common-etf-quant-strategies"},
    {"name": "Investopedia：Risk Parity / Momentum / RSI / MACD / Bollinger / Moving Average / Relative Strength",
     "url": "https://www.investopedia.com/"},
    {"name": "Wikipedia：Low-Volatility Anomaly / Turtle Trading / Breakout (technical analysis)",
     "url": "https://en.wikipedia.org/"},
]

CAVEATS = [
    "王文选股 Top20 与跟单推荐候选池是当前时点筛出的名单，用它回测过去 250 个交易日存在前视偏差，结果偏乐观，只能用于同区间策略之间的相对比较。",
    "已计入真实交易成本：佣金万 2.5（单笔最低 5 元）+ 过户费、印花税（仅卖方万 5）、滑点（双边各 0.1%）；"
    "并建模涨跌停封板无法成交（封板涨停买不进、封板跌停卖不出）与停牌（当日无成交则维持原仓位、差额留现金）。换手高的策略成本拖累更明显。",
    "已做样本外验证：前 %d%% 交易日用于择优，后段（至少 %d 天）作为样本外（OOS）验证；入选要求样本外在多数回测池仍盈利，以抑制过拟合。" % (int(IS_RATIO * 100), OOS_MIN_DAYS),
    "信号强度/等比缩放的外部源（共识权重快照、真实持仓市值）是采集时点的快照，用于回测整段历史存在前视偏差；"
    "信号强度已尽量改用当期可得技术信号，等比缩放按其定义本来就是复制固定目标权重，两者只作同区间相对比较。",
    "现金部分按 0 收益计算，未计货币基金或国债利息。",
    "10 月均线用可得窗口近似 200 日；目标波动率用成分股平均日波动近似组合波动，均未估计协方差矩阵；"
    "科创板(688)/创业板(300/301) 按 20% 涨跌停、其余按 10% 判定，ST（±5%）无法从代码识别，按普通板处理。",
    "三个池按各自成分股的交易日并集对齐并前向填充（停牌日沿用最近收盘价），回测起止日可能不同；跨池比较采用池内排名百分位，不对绝对收益做直接横比。",
    "结果为历史模拟，不代表未来收益，不构成投资建议。",
]


def _load(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _codes(xs):
    out = []
    for x in xs:
        c = S._norm_code(x)
        if re.match(r"^\d{6}$", c) and c not in out:
            out.append(c)
    return out


def _pools():
    ww = _load(os.path.join(DATA, "ww_top20.json"), {})
    ww_codes = _codes([(x or {}).get("code") for x in (ww.get("top20") or [])])[:20]
    mh = _load(os.path.join(DATA, "my_holdings.json"), {})
    hold_codes = _codes([(x or {}).get("code") for x in (mh.get("items") or [])])
    rec_codes, rec_src = [], ""
    try:
        rows = (S.api_recs() or {}).get("rows") or []
        rec_codes = _codes([x.get("symbol") for x in rows
                            if x.get("buyable") is not False and not x.get("over_lot")])[:10]
        if rec_codes:
            rec_src = "实时 /api/recs"
    except Exception:
        rec_codes = []
    if not rec_codes:
        rec_codes = list(FALLBACK_RECS)
        rec_src = "本次采集快照 %s（实时候选池读取失败）" % FALLBACK_RECS_AT
    return [
        {"key": "wangwen", "title": "王文选股页", "source": "data/ww_top20.json 的 Top20",
         "codes": ww_codes, "source_note": "按 2026-11-01 基本面四标准筛出"},
        {"key": "hold", "title": "我的持仓页", "source": "data/my_holdings.json 的 items",
         "codes": hold_codes, "source_note": "当前真实持仓"},
        {"key": "recs", "title": "跟单推荐页", "source": rec_src,
         "codes": rec_codes, "source_note": "与配置方案回测「跟单候选」同源，可买且未超一手的前 10 只"},
    ]


def _ema(seq, span):
    """指数移动平均（初始值取首元素）。"""
    if not seq:
        return []
    k = 2.0 / (span + 1)
    out = [seq[0]]
    for i in range(1, len(seq)):
        out.append(seq[i] * k + out[-1] * (1 - k))
    return out


def _rsi(seq, period=14):
    """Wilder RSI；序列不足返回 None。"""
    n = len(seq)
    if n < period + 1:
        return None
    gains = [max(seq[i] - seq[i - 1], 0.0) for i in range(1, n)]
    losses = [max(seq[i - 1] - seq[i], 0.0) for i in range(1, n)]
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    if al <= 0:
        return 100.0
    rs = ag / al
    return 100.0 - 100.0 / (1.0 + rs)


def _donchian(seq, period):
    """唐奇安通道：返回 (period 日最高, period 日最低)，不足返回 (None, None)。"""
    if len(seq) < period:
        return (None, None)
    seg = seq[-period:]
    return (max(seg), min(seg))


def _boll(seq, period=20, kk=2.0):
    """布林带：返回 (中轨, 上轨, 下轨)，不足返回 (None, None, None)。"""
    if len(seq) < period:
        return (None, None, None)
    seg = seq[-period:]
    m = sum(seg) / period
    var = sum((x - m) ** 2 for x in seg) / period
    sd = var ** 0.5
    return (m, m + kk * sd, m - kk * sd)


# 东财前复权日线 OHLC 的进程内缓存（单跑内同一标的只抓一次）。
_OHLC_CACHE = {}
# 2026-11-14：云服务器 IP 访问东财 push2his 被风控（SSL EOF / RemoteDisconnected）。
# 月度自动回测必须能自愈——东财连续失败后整体切到腾讯前复权日线，并对后续标的
# 直接跳过东财，省掉每只票 3 次必失败的重试。
_EM_BLOCKED = [False]
_TX_OHLC_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param="


def _fetch_ohlc_tx(sym, n):
    """腾讯前复权日线 OHLC 兜底，返回与 _fetch_ohlc_dc 同构的元组序列。

    qfqday 每行 = [日期, 开, 收, 高, 低, 成交量]；单次请求上限约 320 根，
    故按自然年窗口逐年拉取（每年 ≤ 244 个交易日）再按日期去重合并。
    """
    s = S._pub_sym(sym)
    if not s:
        return []
    need = max(int(n or 250), 60)
    years = max(2, int(need / 240.0) + 2)
    this_year = datetime.date.today().year
    out = {}
    for y in range(this_year - years + 1, this_year + 1):
        end = ("%d-01-01" % (y + 1)) if y < this_year else (
            (datetime.date.today() + datetime.timedelta(days=1)).isoformat())
        param = "%s,day,%d-01-01,%s,400,qfq" % (s, y, end)
        try:
            req = urllib.request.Request(_TX_OHLC_URL + param,
                                         headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                j = json.loads(resp.read().decode("utf-8", "replace"))
            node = ((j.get("data") or {}).get(s)) or {}
            rows = node.get("qfqday") or node.get("day") or []
            for r in rows:
                try:
                    d = str(r[0])[:10]
                    # 统一成 (date, open, high, low, close, vol)
                    out[d] = (d, float(r[1]), float(r[3]), float(r[4]),
                              float(r[2]), float(r[5]))
                except (IndexError, TypeError, ValueError):
                    continue
        except Exception:
            continue
    rows = [out[k] for k in sorted(out)]
    return rows[-need:] if len(rows) > need else rows


def _fetch_ohlc_dc(sym, n):
    """前复权日线 OHLC，返回升序 [(日期, 开, 高, 低, 收, 成交量), ...]；失败返回 []。

    主源东财 push2his（fqt=1），不可用时自动回落腾讯 qfqday；保留 OHLC 与成交量
    用于判定涨跌停与停牌——这两类市场摩擦用收盘价无法识别。
    返回元组顺序固定为 (date, open, high, low, close, vol)。
    """
    secid = S._em_secid(sym)
    if not secid or "." not in secid:
        return []
    cached = _OHLC_CACHE.get(sym)
    if cached and len(cached) >= min(int(n or 250), 4000):
        return cached
    url = ("https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=" + secid
           + "&fields1=f1,f2,f3,f4,f5,f6"
           + "&fields2=f51,f52,f53,f54,f55,f56,f57,f58"
           + "&klt=101&fqt=1&end=20500101&lmt=" + str(int(n)))
    j = None
    if not _EM_BLOCKED[0]:
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": "Mozilla/5.0",
                                  "Referer": "https://quote.eastmoney.com/"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    j = json.loads(resp.read().decode("utf-8", "replace"))
                break
            except Exception as e:
                if attempt < 2:
                    time.sleep(0.8)
                else:
                    print("[lab-warn] 东财 OHLC 拉取失败 %s: %s" % (sym, str(e)[:120]))
        if j is None and not _EM_BLOCKED[0]:
            _EM_BLOCKED[0] = True
            print("[lab-warn] 东财 push2his 不可用，本次回测全部改用腾讯前复权日线")
    out = []
    if j is not None:
        for line in (((j or {}).get("data") or {}).get("klines") or []):
            p = str(line).split(",")
            if len(p) < 7:
                continue
            try:
                # f51=日期 f52=开 f53=收 f54=高 f55=低 f56=成交量(手)
                out.append((str(p[0])[:10], float(p[1]), float(p[3]),
                            float(p[4]), float(p[2]), float(p[5])))
            except (IndexError, TypeError, ValueError):
                continue
    if not out:
        out = _fetch_ohlc_tx(sym, n)
        if out:
            print("[lab-warn] 腾讯前复权兜底 %s: %d 根" % (sym, len(out)))
    if out:
        _OHLC_CACHE[sym] = out
    return out


def _limit_pct(code):
    """日涨跌幅限制比例：科创板(688)/创业板(300/301) 为 20%，其余主板/北交为 10%。
    ST（±5%）无法从代码识别，按普通板 10% 处理并在说明里标注。"""
    c = (code or "").strip()
    if c[:3] in ("688", "300", "301"):
        return 0.20
    return 0.10


def _day_flags(prev_close, row, code, suspended):
    """由 OHLC 一行 + 昨收算当日市场状态。

    row = (date, open, high, low, close, vol)。封板判定：当日最高触及涨停价且收盘
    也贴近涨停价（开盘即封死或盘中封死未开板），视为「无法买入」；跌停同理「无法卖出」。
    停牌：当日无成交（suspended=True）时无法买卖。
    """
    pct = _limit_pct(code)
    lu = round(prev_close * (1 + pct), 2) if prev_close and prev_close > 0 else None
    ld = round(prev_close * (1 - pct), 2) if prev_close and prev_close > 0 else None
    close, high, low = row[4], row[2], row[3]
    sealed_up = bool(lu and high >= lu - 0.005 and close >= lu - 0.005)
    sealed_down = bool(ld and low <= ld + 0.005 and close <= ld + 0.005)
    return {"suspended": bool(suspended), "sealed_up": sealed_up,
            "sealed_down": sealed_down, "limit_up": lu, "limit_down": ld,
            "close": close, "high": high, "low": low}


def _ext(win):
    """扩展指标：MA200/50/20、250/120 日动量、20 日 z-score、20 日日波动、
    RSI(14)、EMA12/26 与 MACD(12,26,9)、Donchian(20/55)、Bollinger(20,2σ)。"""
    px = win[-1]
    n = len(win)
    ma200 = sum(win[-200:]) / min(200, n)
    ma50 = sum(win[-50:]) / min(50, n)
    ma20 = sum(win[-20:]) / min(20, n)
    mom250 = (px / win[-251] - 1) if (n >= 251 and win[-251] > 0) else 0.0
    mom120 = (px / win[-121] - 1) if (n >= 121 and win[-121] > 0) else 0.0
    seg = win[-21:] if n >= 21 else win
    r20 = [seg[i] / seg[i - 1] - 1 for i in range(1, len(seg))]
    sd20 = S._std(r20) if len(r20) > 1 else 0.0
    mean20 = sum(seg) / len(seg)
    z20 = (px - mean20) / (sd20 * mean20) if (sd20 > 0 and mean20 > 0) else 0.0
    rsi14 = _rsi(win, 14)
    e12 = _ema(win, 12)
    e26 = _ema(win, 26)
    macd_line = (e12[-1] - e26[-1]) if (e12 and e26) else 0.0
    macd_series = [e12[i] - e26[i] for i in range(min(len(e12), len(e26)))]
    sig = _ema(macd_series, 9)
    macd_sig = sig[-1] if sig else 0.0
    macd_hist = macd_line - macd_sig
    dhi20, dlo20 = _donchian(win, 20)
    dhi55, dlo55 = _donchian(win, 55)
    bm, bu, bl = _boll(win, 20, 2.0)
    return {"px": px, "ma200": ma200, "ma50": ma50, "ma20": ma20,
            "mom250": mom250, "mom120": mom120, "z20": z20, "sd20": sd20,
            "rsi14": rsi14, "macd": macd_line, "macd_sig": macd_sig,
            "macd_hist": macd_hist, "don_hi20": dhi20, "don_lo20": dlo20,
            "don_hi55": dhi55, "don_lo55": dlo55,
            "boll_m": bm, "boll_u": bu, "boll_l": bl}


def _lab_ctx():
    """signal/copy 的外部权重源：共识快照 + 真实持仓市值（与 server._bt_source_ctx 同口径）。"""
    cons, src, snap = {}, {}, {}
    try:
        snap = _load(os.path.join(DATA, "last_consensus.json"), {}) or {}
        for x in (snap.get("top") or []):
            c = S._norm_code(x.get("symbol"))
            if re.match(r"^\d{6}$", c):
                cons[c] = len(x.get("in") or [])
                src[c] = max(0.0, float(x.get("weight_sum") or 0))
    except Exception:
        pass
    mh = _load(os.path.join(DATA, "my_holdings.json"), {}) or {}
    for it in (mh.get("items") or []):
        c = S._norm_code(it.get("code"))
        if not re.match(r"^\d{6}$", c):
            continue
        try:
            v = float(it.get("mkt") or 0) or (
                float(it.get("lots") or 0) * 100.0 * float(it.get("buy_price") or 0))
        except (TypeError, ValueError):
            v = 0.0
        if c not in src or src[c] <= 0:
            src[c] = max(0.0, v)
    return {"consensus": cons, "source_weights": src,
            "consensus_at": (snap.get("time") if isinstance(snap, dict) else "") or ""}


def _weights(key, metas, extm, n, ctx=None):
    if key in EXISTING_KEYS:
        return S._bt_weights(key, metas, ctx if ctx is not None else S._bt_source_ctx())
    if key == "buy_hold":
        return None
    if key == "sma200":
        return {c: (1.0 / n if extm[c]["px"] > extm[c]["ma200"] else 0.0) for c in extm}
    if key == "dual_mom":
        best = max(extm, key=lambda c: extm[c]["mom250"])
        return {best: 1.0} if extm[best]["mom250"] > 0 else {}
    if key == "mom_rot":
        top = [c for c in sorted(extm, key=lambda c: -extm[c]["mom250"])[:5]
               if extm[c]["mom250"] > 0]
        return {c: 0.2 for c in top}
    if key == "mean_rev":
        ws = {c: max(0.0, -extm[c]["z20"]) for c in extm}
        tot = sum(ws.values())
        return {c: v / tot for c, v in ws.items()} if tot > 0 else {}
    if key == "vol_target":
        avg_sd = sum(extm[c]["sd20"] for c in extm) / n
        target = 0.15 / math.sqrt(244.0)
        scale = min(1.0, target / avg_sd) if avg_sd > 0 else 1.0
        return {c: scale / n for c in extm}
    # --- 2026-11-07 新增 11 个公开策略权重规则 ---
    if key == "risk_parity":
        iv = {c: (1.0 / extm[c]["sd20"]) for c in extm if extm[c]["sd20"] > 0}
        tot = sum(iv.values())
        return {c: v / tot for c, v in iv.items()} if tot > 0 else {}
    if key == "low_vol":
        vols = sorted((c for c in extm if extm[c]["sd20"] > 0), key=lambda c: extm[c]["sd20"])
        pick = vols[: max(1, n // 3)]
        return {c: 1.0 / len(pick) for c in pick}
    if key == "mom120":
        ranked = [c for c in sorted(extm, key=lambda c: -extm[c]["mom120"]) if extm[c]["mom120"] > 0]
        pick = ranked[: max(1, n // 2)]
        return {c: 1.0 / len(pick) for c in pick}
    if key == "rsi_rev":
        ws = {c: max(0.0, 30.0 - extm[c]["rsi14"]) for c in extm
              if extm[c]["rsi14"] is not None and extm[c]["rsi14"] < 30.0}
        tot = sum(ws.values())
        return {c: v / tot for c, v in ws.items()} if tot > 0 else {}
    if key == "macd_cross":
        up = [c for c in extm if extm[c]["macd_hist"] is not None and extm[c]["macd_hist"] > 0]
        return {c: 1.0 / len(up) for c in up} if up else {}
    if key == "donchian":
        brk = [c for c in extm if extm[c]["don_hi20"] is not None and extm[c]["px"] >= extm[c]["don_hi20"]]
        return {c: 1.0 / len(brk) for c in brk} if brk else {}
    if key == "boll_rev":
        ws = {c: max(0.0, extm[c]["boll_l"] - extm[c]["px"]) for c in extm
              if extm[c]["boll_l"] is not None and extm[c]["px"] < extm[c]["boll_l"]}
        tot = sum(ws.values())
        return {c: v / tot for c, v in ws.items()} if tot > 0 else {}
    if key == "sma_cross":
        gc = [c for c in extm if extm[c]["ma20"] is not None and extm[c]["ma50"] is not None
              and extm[c]["ma20"] > extm[c]["ma50"]]
        return {c: 1.0 / len(gc) for c in gc} if gc else {}
    if key == "trend_filter":
        above = sum(1 for c in extm if extm[c]["px"] > extm[c]["ma200"])
        return {c: 1.0 / n for c in extm} if above >= n / 2 else {}
    if key == "rel_strength":
        ranked = [c for c in sorted(extm, key=lambda c: -extm[c]["mom120"])][:5]
        return {c: 0.2 for c in ranked} if ranked else {}
    if key == "breakout":
        hi = [c for c in extm if extm[c]["don_hi55"] is not None
              and extm[c]["px"] >= extm[c]["don_hi55"] * 0.995]
        return {c: 1.0 / len(hi) for c in hi} if hi else {}
    return {}


def _apply_cap(w, cap, legacy):
    """现有方案沿用 api_backtest 的迭代注水与归一化；公开策略削顶后余额留现金。"""
    w = dict(w)
    if legacy:
        for _ in range(12):
            over = {k: v for k, v in w.items() if v > cap}
            if not over:
                break
            excess = sum(v - cap for v in over.values())
            for k in over:
                w[k] = cap
            rest = {k: v for k, v in w.items() if v < cap}
            tot = sum(rest.values())
            if tot <= 0:
                break
            for k in rest:
                w[k] += excess * (rest[k] / tot)
        s = sum(w.values())
        return {k: v / s for k, v in w.items()} if s > 0 else {}
    return {k: min(v, cap) for k, v in w.items()}


def _metrics(vals, base=None):
    """由净值序列算总收益/年化/最大回撤/夏普；base 为真实起始本金（默认取序列首值）。

    用真实起始本金做基准，成本扣减才不会在「窗口首值」里被抵消（详见 _run_one 的 drag 计算）。
    """
    if len(vals) < 2 or vals[0] <= 0:
        return {"total": 0.0, "ann": None, "mdd": None, "sharpe": None,
                "final": (vals[-1] if vals else 0.0)}
    b = base if (base is not None and base > 0) else vals[0]
    total = vals[-1] / b - 1
    rets = [vals[i] / vals[i - 1] - 1 for i in range(1, len(vals))]
    yrs = max(len(vals) / 244.0, 1e-6)
    ann = ((1 + total) ** (1 / yrs) - 1) if (1 + total) > 0 else None
    peak, mdd = vals[0], 0.0
    for v in vals:
        if v > peak:
            peak = v
        if peak > 0:
            mdd = max(mdd, (peak - v) / peak)
    sd = S._std(rets) if len(rets) > 1 else 0.0
    sharpe = ((sum(rets) / len(rets)) / sd * (244 ** 0.5)) if sd > 0 else None
    return {"total": round(total, 4), "ann": round(ann, 4) if ann is not None else None,
            "mdd": round(mdd, 4), "sharpe": round(sharpe, 2) if sharpe is not None else None,
            "final": round(vals[-1], 2)}


def _run_one(key, px, dates, ctx=None, dayinfo=None, trade_start=WARM, trade_end=None):
    """带真实成本与市场摩擦的回测（离散再平衡模型）。

    px: {code: {date: close}}（停牌日已前向填充为最近收盘价，当日收益记 0）。
    dayinfo: {code: {date: {suspended, sealed_up, sealed_down, ...}}}。
    trade_start/trade_end：交易区间（含），区间外持有现金、净值走平（用于 IS/OOS 切分）。

    交易时点：进入第 i 日时持有上一期实际权重（含漂移），赚取当日收益；收盘后再平衡，
    按目标权重与「上一期实际权重」之差计算买卖 delta，并以成交金额计：
      - 佣金（万 2.5、单笔最低 5 元）+ 过户费；印花税仅卖方万 5；滑点双边 0.1%。
    若再平衡当日标的封板涨停（想买买不进）/ 封板跌停（想卖卖不出）/ 停牌，则该标的
    无法成交，维持原权重、差额留现金，并计入 blocked。
    返回净收益、毛收益（不计成本）、成本拆解、换手、被阻断统计；IS/OOS 由调用方切分。
    """
    codes = list(px.keys())
    n = len(codes)
    if n < 2:
        return {"status": "error", "reason": "有效标的不足 2 只"}
    if trade_end is None:
        trade_end = len(dates) - 1
    nav = [CAPITAL]
    nav_raw = [CAPITAL]   # 不计成本的对照净值
    curve = [{"d": dates[0], "v": round(CAPITAL, 2)}]
    cur_w, shares = None, None
    # v47 第 11 项：只有等权（或显式关闭留现金）沿用满仓归一化口径
    legacy = (key == "equal") or (not ALLOW_CASH)
    cap = max(CAP, 1.0 / n) if legacy else CAP
    cash_sum, cash_cnt = 0.0, 0
    prev_w_eff = {c: 0.0 for c in codes}   # 上一期实际（含漂移）权重，delta 基准
    comm_tot = stamp_tot = slip_tot = 0.0
    turnover_sum = 0.0
    n_rebal = 0
    blocked_rebal = 0
    blocked_trades = 0
    for i in range(1, len(dates)):
        d = dates[i]
        prev = dates[i - 1]
        if i < trade_start or i > trade_end:
            nav.append(nav[-1]); nav_raw.append(nav_raw[-1])
            curve.append({"d": d, "v": round(nav[-1], 2)})
            continue
        if key == "buy_hold":
            if shares is None:
                shares = {c: (CAPITAL / n) / px[c][prev] for c in codes}
            v = sum(sh * px[c][d] for c, sh in shares.items())
            nav.append(v); nav_raw.append(v)
            curve.append({"d": d, "v": round(v, 2)})
            prev_w_eff = {c: (shares[c] * px[c][d]) / v for c in codes}
            continue
        # 1) 用进入当日的实际权重赚取当日收益
        r = 0.0
        for c, wt in prev_w_eff.items():
            try:
                r += wt * (px[c][d] / px[c][prev] - 1)
            except (KeyError, ZeroDivisionError):
                continue
        nav.append(nav[-1] * (1 + r))
        nav_raw.append(nav_raw[-1] * (1 + r))
        # 2) 收盘后决定是否再平衡（首日为建仓）
        do_rebal = (cur_w is None) or ((i - trade_start) % REBAL == 0)
        if do_rebal:
            closes = {c: [px[c][dd] for dd in dates[:i + 1]] for c in codes}
            metas = [{"code": c, "rk": S._bt_metrics_at(closes[c], i - 1)} for c in codes]
            extm = {c: _ext(closes[c]) for c in codes}
            ctx_i = ctx
            if ctx_i is None and ASOF_REPLAY and key in ("signal", "copy"):
                try:
                    ctx_i = S._bt_source_ctx(asof=prev)
                except Exception:
                    ctx_i = None
            w = _weights(key, metas, extm, n, ctx_i)
            if w is None:
                return {"status": "error", "reason": "权重规则返回空"}
            target = _apply_cap(w, cap, legacy)
            new_w = {}
            rebal_blocked = 0
            for c in codes:
                tw = target.get(c, 0.0)
                pw = prev_w_eff.get(c, 0.0)
                delta = tw - pw
                if abs(delta) < 1e-9:
                    new_w[c] = pw
                    continue
                di = (dayinfo or {}).get(c, {}).get(d) if dayinfo else None
                blocked = False
                if di is not None:
                    if delta > 0 and (di.get("suspended") or di.get("sealed_up")):
                        blocked = True
                    elif delta < 0 and (di.get("suspended") or di.get("sealed_down")):
                        blocked = True
                if blocked:
                    new_w[c] = pw          # 无法成交：维持原权重，差额留现金
                    rebal_blocked += 1
                    blocked_trades += 1
                else:
                    new_w[c] = tw
            # 成本：按实际成交金额计
            buy_val = sell_val = 0.0
            for c in codes:
                dlt = new_w.get(c, 0.0) - prev_w_eff.get(c, 0.0)
                if dlt > 0:
                    buy_val += dlt * nav[-1]
                elif dlt < 0:
                    sell_val += (-dlt) * nav[-1]
            comm = 0.0
            for c in codes:
                dlt = abs(new_w.get(c, 0.0) - prev_w_eff.get(c, 0.0))
                if dlt <= 1e-9:
                    continue
                val = dlt * nav[-1]
                comm += max(COMMISSION_MIN, val * COMMISSION) + val * TRANSFER
            stamp = sell_val * STAMP
            slip = (buy_val + sell_val) * SLIPPAGE
            cost = comm + stamp + slip
            comm_tot += comm; stamp_tot += stamp; slip_tot += slip
            turnover_sum += sum(abs(new_w.get(c, 0.0) - prev_w_eff.get(c, 0.0)) for c in codes)
            nav[-1] -= cost
            cur_w = new_w
            prev_w_eff = new_w          # 建仓/调仓当日权重不再漂移（次日起才漂移）
            cash_sum += max(0.0, 1.0 - sum(new_w.values()))
            cash_cnt += 1
            n_rebal += 1
            if rebal_blocked:
                blocked_rebal += 1
        else:
            # 非再平衡日：权重随价格漂移
            vt = nav[-1]
            if vt > 0 and (1 + r) != 0:
                prev_w_eff = {c: prev_w_eff[c] * (px[c][d] / px[c][prev]) / (1 + r)
                              for c in codes}
            else:
                prev_w_eff = {c: 0.0 for c in codes}
        curve.append({"d": d, "v": round(nav[-1], 2)})
    s = max(trade_start, 1)
    e = min(trade_end, len(nav) - 1)
    # 以真实起始本金 CAPITAL 为基准，成本扣减才会真实体现在净收益与 drag 上
    net = _metrics(nav[s:e + 1], CAPITAL)
    gross = _metrics(nav_raw[s:e + 1], CAPITAL)
    drag = (gross["total"] - net["total"]) if (gross["total"] is not None
                                               and net["total"] is not None) else None
    return {
        "status": "ok",
        "total": net["total"], "ann": net["ann"], "mdd": net["mdd"], "sharpe": net["sharpe"],
        "final": net["final"], "curve": curve,
        "gross_total": gross["total"], "gross_ann": gross["ann"],
        "cost": {
            "commission": round(comm_tot, 2), "stamp": round(stamp_tot, 2),
            "slippage": round(slip_tot, 2),
            "drag": round(drag, 4) if drag is not None else None,
            "turnover_avg": round(turnover_sum / n_rebal, 4) if n_rebal else 0.0,
            "n_rebal": n_rebal, "blocked_rebal": blocked_rebal,
            "blocked_trades": blocked_trades,
        },
    }


def _rank_pct(vals, v):
    if len(vals) < 2:
        return 1.0
    return sum(1 for x in vals if x < v) / (len(vals) - 1)


def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    return cov / (vx ** 0.5 * vy ** 0.5)


def _summarize(pools):
    keys = [k for k, _, _, _ in ALL if k not in DEGENERATE and k not in SKIPPED]
    stat = {k: {"scores": [], "sharpes": [], "totals": [], "mdds": [], "pools": [],
                "oos_totals": [], "oos_sharpes": [], "min_score": 1.0} for k in keys}
    for pool in pools:
        ok = [r for r in pool["results"] if r["status"] == "ok"]
        if len(ok) < 2:
            continue
        sh = [(r["sharpe"] if r["sharpe"] is not None else -9.0) for r in ok]
        tt = [r["total"] for r in ok]
        md = [r["mdd"] for r in ok]
        for r in ok:
            k = r["key"]
            if k not in stat:
                continue
            p_sh = _rank_pct(sh, r["sharpe"] if r["sharpe"] is not None else -9.0)
            p_tt = _rank_pct(tt, r["total"])
            p_md = 1.0 - _rank_pct(md, r["mdd"])
            score = 0.5 * p_sh + 0.3 * p_tt + 0.2 * p_md
            s = stat[k]
            s["scores"].append(score)
            s["sharpes"].append(r["sharpe"])
            s["totals"].append(r["total"])
            s["mdds"].append(r["mdd"])
            s["pools"].append(pool["key"])
            s["min_score"] = min(s["min_score"], score)
            oos = r.get("oos") or {}
            if oos.get("total") is not None:
                s["oos_totals"].append(oos["total"])
            if oos.get("sharpe") is not None:
                s["oos_sharpes"].append(oos["sharpe"])
    rows = []
    for k, s in stat.items():
        pools_ok = len(s["pools"])
        avg_oos_total = (sum(s["oos_totals"]) / len(s["oos_totals"])) if s["oos_totals"] else None
        avg_oos_sharpe = (sum(s["oos_sharpes"]) / len(s["oos_sharpes"])) if s["oos_sharpes"] else None
        oos_pass = sum(1 for t, sh in zip(s["oos_totals"], s["oos_sharpes"])
                        if t is not None and sh is not None and t > 0 and sh > 0)
        rows.append({
            "key": k, "name": NAME[k], "origin": ORIGIN[k],
            "score": round(sum(s["scores"]) / len(s["scores"]), 4) if s["scores"] else 0.0,
            "stable_pools": sum(1 for x in s["sharpes"] if x is not None and x > 0),
            "pools_ok": pools_ok,
            "avg_total": round(sum(s["totals"]) / len(s["totals"]), 4) if s["totals"] else None,
            "avg_mdd": round(sum(s["mdds"]) / len(s["mdds"]), 4) if s["mdds"] else None,
            "avg_oos_total": round(avg_oos_total, 4) if avg_oos_total is not None else None,
            "avg_oos_sharpe": round(avg_oos_sharpe, 2) if avg_oos_sharpe is not None else None,
            "oos_pass_pools": oos_pass,
            "passed_oos": (oos_pass >= 2) if s["oos_totals"] and s["oos_sharpes"] else False,
            "min_pool_score": round(s["min_score"], 4),
        })
    rows.sort(key=lambda x: -x["score"])
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    threshold = 0.55
    # 入选：综合分达线 + 至少 2 池夏普为正 + 样本外（OOS）在多数池盈利（防过拟合）。
    # 严格入选不足 2 名时逐级放宽：先放宽到「至少 1 池 OOS 盈利」，再放宽到仅看综合分。
    strict = [r for r in rows if r["score"] >= threshold
              and r["stable_pools"] >= 2 and r.get("passed_oos")]
    selected = strict[:2]
    if len(selected) < 2:
        fill = [r for r in rows if r not in selected and r["score"] >= threshold
                and r["stable_pools"] >= 2 and r["oos_pass_pools"] >= 1]
        selected += fill[:2 - len(selected)]
    if len(selected) < 2:
        fill = [r for r in rows if r not in selected and r["score"] >= threshold
                and r["stable_pools"] >= 2]
        selected += fill[:2 - len(selected)]
    sel_keys = set(r["key"] for r in selected)
    rejected = []
    for r in rows:
        if r["key"] in sel_keys:
            continue
        if r["pools_ok"] < 2:
            why = "可用回测池不足 2 个，跨池证据不够"
        elif r["score"] < threshold:
            why = "跨池综合分 %.2f 低于入选线 %.2f" % (r["score"], threshold)
        elif r["stable_pools"] < 2:
            why = "仅 %d 个池夏普为正，跨池稳定性不足" % r["stable_pools"]
        elif not r.get("passed_oos"):
            why = "样本外未通过（%d/%d 池样本外亏损或夏普为负），放宽后仍按综合分处理" % (
                r["oos_pass_pools"], r["pools_ok"])
        else:
            why = "综合分排名靠后（第 %d 名），择优取前 2 名" % r["rank"]
        if r["avg_mdd"] is not None and r["avg_mdd"] > 0.25:
            why += "；平均最大回撤 %.1f%% 偏大" % (r["avg_mdd"] * 100)
        rejected.append({"key": r["key"], "name": r["name"], "score": r["score"], "reason": why})
    rejected.append({"key": "sixty_forty", "name": NAME["sixty_forty"], "score": None,
                     "reason": "三个页面标的池里没有债券或债券 ETF，无法构造 60/40 股债组合，未纳入回测"})
    # IS/OOS 稳定性：全样本综合分与样本外平均收益的相关系数（>0 表示样本内强者样本外仍强）
    xs, ys = [], []
    for r in rows:
        if r.get("avg_oos_total") is not None:
            xs.append(r["score"])
            ys.append(r["avg_oos_total"])
    oos_corr = _pearson(xs, ys)
    passed_oos_cnt = sum(1 for r in rows if r.get("passed_oos"))
    return {
        "scoring": "池内按夏普 50% + 总收益 30% + 回撤反向 20% 取排名百分位，再对可用池取平均；"
                   "入选需综合分不低于 0.55、至少 2 个池夏普为正，且样本外（OOS）在多数池盈利，"
                   "按分数取前 2 名。评分规则在跑回测之前固定，避免事后挑参数。",
        "threshold": threshold,
        "ranking": rows,
        "selected": selected,
        "rejected": rejected,
        "oos_checked": len(xs),
        "passed_oos": passed_oos_cnt,
        "oos_rank_corr": round(oos_corr, 3) if oos_corr is not None else None,
    }


def _pool_report(pool, ctx=None):
    codes = pool["codes"]
    if len(codes) < 2:
        return {"key": pool["key"], "title": pool["title"], "source": pool["source"],
                "source_note": pool["source_note"], "codes": codes, "ok": False,
                "error": "标的不足 2 只", "results": []}
    # 抓东财前复权 OHLC（含成交量，用于判定涨跌停/停牌）
    ohlc = {}
    for c in codes:
        try:
            ohlc[c] = _fetch_ohlc_dc(c, DAYS + 60)
        except Exception:
            ohlc[c] = []
    valid = {c: ohlc[c] for c in codes if len(ohlc[c]) >= WARM}
    if len(valid) < 2:
        return {"key": pool["key"], "title": pool["title"], "source": pool["source"],
                "source_note": pool["source_note"], "codes": codes, "ok": False,
                "error": "K 线有效标的不足 2 只", "results": []}
    # 主时间轴 = 所有有效标的交易日的并集；停牌日由前向填充补齐（沿用最近收盘价，收益记 0）
    alld = set()
    for c in valid:
        for row in valid[c]:
            alld.add(row[0])
    dates = sorted(alld)
    if len(dates) < WARM + 1:
        return {"key": pool["key"], "title": pool["title"], "source": pool["source"],
                "source_note": pool["source_note"], "codes": codes, "ok": False,
                "error": "共同交易日不足 61 天", "results": []}
    dates = dates[-(DAYS + 1):]
    px = {}
    dayinfo = {}
    for c in valid:
        m = {r[0]: r for r in valid[c]}
        first = valid[c][0]
        last = first
        px[c] = {}
        dayinfo[c] = {}
        for k, d in enumerate(dates):
            if d in m:
                last = m[d]
            close = last[4]
            prev_close = px[c][dates[k - 1]] if k > 0 else close
            suspended = (d not in m)
            dayinfo[c][d] = _day_flags(prev_close, last, c, suspended)
            px[c][d] = close
    # 样本内/样本外切分：前 IS_RATIO 用于择优、后段做样本外验证（OOS 至少 OOS_MIN_DAYS 天）
    last_idx = len(dates) - 1
    is_end = int(round(last_idx * IS_RATIO))
    if (last_idx - is_end) < OOS_MIN_DAYS:
        is_end = last_idx - OOS_MIN_DAYS
    is_end = max(WARM, is_end)
    results = []
    for key, name, origin, url in ALL:
        base = {"key": key, "name": name, "origin": origin, "source_url": url}
        if key in SKIPPED:
            base.update({"status": "skipped",
                         "reason": "标的池里没有债券类资产，无法构造 60/40 股债组合"})
        else:
            try:
                full = _run_one(key, px, dates, ctx, dayinfo, WARM, last_idx)
                if full.get("status") != "ok":
                    base.update(full)
                else:
                    is_r = _run_one(key, px, dates, ctx, dayinfo, WARM, is_end)
                    oos_r = _run_one(key, px, dates, ctx, dayinfo, is_end, last_idx)
                    base.update({
                        "status": "ok",
                        "total": full["total"], "ann": full["ann"], "mdd": full["mdd"],
                        "sharpe": full["sharpe"], "final": full["final"],
                        "curve": full["curve"],
                        "gross_total": full["gross_total"], "gross_ann": full["gross_ann"],
                        "cost": full["cost"],
                        "is": {"total": is_r.get("total"), "ann": is_r.get("ann"),
                               "mdd": is_r.get("mdd"), "sharpe": is_r.get("sharpe")},
                        "oos": {"total": oos_r.get("total"), "ann": oos_r.get("ann"),
                                "mdd": oos_r.get("mdd"), "sharpe": oos_r.get("sharpe")},
                    })
            except Exception as e:
                base.update({"status": "error", "reason": "回测异常：" + str(e)[:160]})
        results.append(base)
    return {
        "key": pool["key"], "title": pool["title"], "source": pool["source"],
        "source_note": pool["source_note"], "codes": sorted(px.keys()), "ok": True,
        "start": dates[WARM], "end": dates[-1], "days": len(dates) - WARM,
        "is_window": {"start": dates[WARM], "end": dates[is_end],
                      "days": is_end - WARM + 1},
        "oos_window": {"start": dates[is_end], "end": dates[-1],
                       "days": last_idx - is_end + 1},
        "results": results,
    }


def _sync_strategies(out):
    """把全部跑通回测的公开策略（lab_ 前缀）幂等写入策略营下拉，使「我的策略」不再为空。

    入选（实验室跨池综合分达标）者排在最前并标注 ★；其余候选策略一并收录，
    曲线均来自策略实验室同一条回测，与页面下方「策略实验室」三池对比表同源。
    """
    path = os.path.join(DATA, "strategies.json")
    lst = _load(path, [])
    if not isinstance(lst, list):
        lst = []
    lst = [x for x in lst if not str((x or {}).get("id") or "").startswith("lab_")]
    pools_by_key = {p.get("key"): p for p in (out.get("pools") or [])}
    sel_keys = set(r["key"] for r in (out.get("summary") or {}).get("selected", []))
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _best_pool(key):
        for pk in ("hold", "wangwen", "recs"):
            p = pools_by_key.get(pk)
            if not p:
                continue
            r = next((x for x in (p.get("results") or []) if x.get("key") == key), None)
            if r and r.get("status") == "ok":
                return p, r
        for p in (out.get("pools") or []):
            r = next((x for x in (p.get("results") or []) if x.get("key") == key), None)
            if r and r.get("status") == "ok":
                return p, r
        return None, None

    appended = []
    for k, n, o, u in PUBLIC:
        if k in SKIPPED:
            continue
        p, r = _best_pool(k)
        if p is None or r is None:
            continue
        is_sel = k in sel_keys
        lst.append({
            "id": "lab_" + k,
            "name": ("★入选 · " if is_sel else "候选 · ") + n,
            "codes": (p.get("codes") or []),
            "weights": None,
            "scheme": k if k in EXISTING_KEYS else "equal",
            "lab_key": k,
            "lab_pool": p.get("key"),
            "rebal": REBAL,
            "capital": CAPITAL,
            "cap_pct": round(CAP * 100, 2),
            "note": ("实验室跨池综合分达标、且样本外验证通过入选；" if is_sel else "实验室候选策略；")
                    + "净值曲线为含佣金/印花税/滑点的净收益，与页面下方「策略实验室」三池对比表同源。",
            "created": now,
        })
        appended.append(k)
    lst.sort(key=lambda x: (0 if str(x.get("name", "")).startswith("★") else 1, x.get("id") or ""))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(lst[:100], f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return len(appended)


def _selftest():
    """合成行情跑通全部策略，并验证现有等权方案与直接调用 _bt_weights 的一致性。"""
    import random
    random.seed(7)
    # 用 6 只票（与真实持仓池同规模）：4 只票时单票上限被抬到 1/N=25%，
    # 满仓 + 每票≤25% 在数学上只有唯一解 = 等权，会掩盖权重差异。
    codes = ["A00001", "B00002", "C00003", "D00004", "E00005", "F00006"]
    dates = ["2026-%02d-%02d" % (m, d) for m in range(1, 13) for d in range(1, 25)]
    series = {}
    for j, c in enumerate(codes):
        p, out = 10.0 + j, []
        for i in range(len(dates)):
            p *= (1 + random.uniform(-0.025, 0.026))
            out.append((dates[i], round(p, 4)))
        series[c] = out
    def _fake_ohlc(sym, n=250):
        rows = series.get(sym, [])
        # 合成 OHLC：开=高=低=收（无涨跌停），成交量极大（非停牌）
        return [(d, c, c, c, c, 1_000_000) for d, c in rows]
    orig_ohlc = globals().get("_fetch_ohlc_dc")
    globals()["_fetch_ohlc_dc"] = _fake_ohlc
    _OHLC_CACHE.clear()
    orig_pools = _pools

    def fake_pools():
        return [{"key": "t1", "title": "测试池", "source": "selftest",
                 "source_note": "合成行情", "codes": codes}]
    globals()["_pools"] = fake_pools
    # 伪造一份不等权的源组合，专门验证 copy 不再退化为等权
    ctx = {"consensus": {}, "consensus_at": "selftest",
           "source_weights": dict(zip(codes, [60.0, 25.0, 10.0, 3.0, 1.5, 0.5]))}
    try:
        pool = _pool_report(fake_pools()[0], ctx)
    finally:
        globals()["_pools"] = orig_pools
        if orig_ohlc is not None:
            globals()["_fetch_ohlc_dc"] = orig_ohlc
    ok = [r for r in pool["results"] if r["status"] == "ok"]
    bad = [r for r in pool["results"] if r["status"] == "error"]
    print("SELFTEST_POOL_OK=" + str(pool["ok"]))
    print("SELFTEST_STRATEGIES_OK=" + str(len(ok)) + " ERRORS=" + str(len(bad)))
    print("SELFTEST_CURVE_POINTS=" + str(len(ok[0]["curve"]) if ok else 0))
    eq = next((r for r in pool["results"] if r["key"] == "equal"), {})
    sg = next((r for r in pool["results"] if r["key"] == "signal"), {})
    cp = next((r for r in pool["results"] if r["key"] == "copy"), {})
    print("SELFTEST_EQUAL_TOTAL=" + str(eq.get("total")))
    print("SELFTEST_SIGNAL_TOTAL=" + str(sg.get("total")))
    print("SELFTEST_COPY_TOTAL=" + str(cp.get("total")))
    print("SELFTEST_NOT_DEGENERATE_SIGNAL=" + str(sg.get("total") != eq.get("total")))
    print("SELFTEST_NOT_DEGENERATE_COPY=" + str(cp.get("total") != eq.get("total")))
    for r in bad:
        print("  ERROR " + r["key"] + ": " + str(r.get("reason")))
    good = (pool["ok"] and len(ok) >= 18 and not bad
            and sg.get("total") != eq.get("total") and cp.get("total") != eq.get("total"))
    return 0 if good else 1


def main():
    if "--selftest" in sys.argv:
        return _selftest()
    t0 = time.time()
    out = {
        "ok": True,
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "params": {"days": DAYS, "rebal": REBAL, "capital": CAPITAL,
                   "cap_pct": round(CAP * 100, 2), "warmup": WARM,
                   "allow_cash": ALLOW_CASH, "asof_replay": ASOF_REPLAY,
                   "commission": COMMISSION, "commission_min": COMMISSION_MIN,
                   "stamp": STAMP, "slippage": SLIPPAGE, "transfer": TRANSFER,
                   "is_ratio": IS_RATIO, "oos_min_days": OOS_MIN_DAYS},
        "caliber": "东财前复权日线(OHLC)，按各成分股交易日并集对齐并前向填充停牌日；预热 61 个交易日；"
                   "每 20 个交易日按当期可得数据重算目标权重并离散再平衡。单票上限 20%。"
                   "v47：等权方案保持满仓作为对照，其余方案只向下削顶、余额留现金。"
                   "已计入交易成本（佣金万2.5/单笔最低5元+过户费、印花税卖出万5、滑点双边0.1%）与"
                   "市场摩擦（封板涨跌停无法成交、停牌维持原仓）。signal/copy 按再平衡时点读取每日共识快照做时点回放。"
                   "全样本净收益用于排名；前 60% 为样本内择优、后 40% 为样本外验证。指标口径与 /api/backtest 一致。",
        "sources": SOURCES,
        "caveats": CAVEATS,
        "pools": [],
    }
    ctx = _lab_ctx()
    for p in _pools():
        r = _pool_report(p, ctx)
        out["pools"].append(r)
        print("POOL %s codes=%d ok=%s strategies_ok=%d" % (
            r["key"], len(r.get("codes") or []), r["ok"],
            sum(1 for x in r.get("results") or [] if x["status"] == "ok")), flush=True)
    out["summary"] = _summarize(out["pools"])
    out["ohlc_source"] = ("腾讯前复权日线（东财 push2his 不可用，自动兜底）"
                          if _EM_BLOCKED[0] else "东财前复权日线")
    out["elapsed_sec"] = round(time.time() - t0, 1)
    try:
        out["synced_strategies"] = _sync_strategies(out)
    except Exception as e:
        out["synced_strategies"] = 0
        out["sync_error"] = str(e)[:160]
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, OUT)
    print("WRITTEN=%s SIZE=%d" % (OUT, os.path.getsize(OUT)), flush=True)
    print("SELECTED=" + ",".join(x["key"] for x in out["summary"]["selected"]), flush=True)
    for x in out["summary"]["ranking"][:5]:
        print("  RANK %d %s score=%.4f stable=%d" % (
            x["rank"], x["name"], x["score"], x["stable_pools"]), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
