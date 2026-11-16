```js
/* v86_B_panels.js —— 8 面板加载 / 渲染 / 降级 / 交互（纯 JS 片段，由 A 拼进单文件 PWA）
 * 作者：B(DuMate)。读者：A（合并方）。自包含，不依赖除全局既有函数外的任何东西。
 *
 * 既有全局函数（直接调用，不重实现）：
 *   apiGet(path, timeoutMs) / apiPost(path, body) / $(id) / esc(s) / safeUrl(u)
 *   toast(msg) / cls(v)->"up"|"down"|"flat" / fmtPctNum(v) / state(只读) / switchTab(name)
 *
 * 前端铁律（违反则 A 无法合并）：
 *   - CSS 禁止裸 hex，颜色一律 var(--token)
 *   - 涨红跌绿，--up/--down 永不覆写，用 cls() 上色
 *   - 字号只用 var(--fs-*)；禁裸 px 字号、禁 !important
 *   - 所有服务端文本用 esc()；空态用 <div class="empty">…</div>
 *   - 不输出 <script>/<style>；不新增 view/导航/页签；不修改 state；不覆盖桌面既有 DOM
 *   - 移动端克隆会重复 id：容器一律用 querySelectorAll('[data-v86="key"]') 遍历所有副本
 */

/* ============ 通用 helper ============ */

// 写主容器：遍历所有 data-v86="key" 副本（移动端克隆后 id 重复）
function _v86Set(key, html) {
  var nodes = document.querySelectorAll('[data-v86="' + key + '"]');
  nodes.forEach(function (el) { el.innerHTML = html; });
}

// 写提示行：遍历所有 data-v86-sub="key" 副本
function _v86Sub(key, text) {
  var nodes = document.querySelectorAll('[data-v86-sub="' + key + '"]');
  nodes.forEach(function (el) { el.textContent = text || ''; });
}

// 标记某面板读取失败：保留上一版内容，仅写提示行，绝不编造/清空
function _v86Stale(key, reason) {
  _v86Sub(key, '[STALE] 本次读取失败，保留上一版' + (reason ? '：' + esc(reason) : ''));
}

// 百分数数值格式化（带符号，例如 1.5 -> +1.50%；null -> [暂缺]）
function _fmtPctNum(v) {
  if (v === null || v === undefined || isNaN(v)) return '[暂缺]';
  var n = Number(v);
  return (n >= 0 ? '+' : '') + n.toFixed(2) + '%';
}

// 普通比率（无符号，例如 36.4 -> 36.4%）
function _fmtRate(v) {
  if (v === null || v === undefined || isNaN(v)) return '[暂缺]';
  return Number(v).toFixed(1) + '%';
}

// 金额
function _fmtMoney(v) {
  if (v === null || v === undefined || isNaN(v)) return '[暂缺]';
  var n = Number(v);
  return (n >= 0 ? '' : '-') + '¥' + Math.abs(n).toLocaleString('zh-CN', { maximumFractionDigits: 2 });
}

// 防重入 busy 标志
var _v86Busy = {};

// 安全包裹单个面板加载，失败隔离 + busy 防重入 + force 跳过节流
async function _v86Guard(key, force, fn) {
  if (_v86Busy[key] && !force) return;        // 节流：非 force 且正在加载则跳过
  _v86Busy[key] = true;
  try {
    await fn();
  } catch (e) {
    _v86Stale(key, (e && e.message) ? e.message : '网络/解析异常');
  } finally {
    _v86Busy[key] = false;
  }
}

/* ============ 面板 1：持仓归因 /api/trade_attribution ============ */
function _renderAttr(data) {
  if (!data || data.available === false || data.ok === false) {
    var r = (data && data.reason) ? data.reason : '数据暂不可用';
    return '<div class="empty">持仓归因不可用：' + esc(r) + '。请稍后重试或检查数据源。</div>';
  }
  var rows = data.rows || [];
  var closed = rows.filter(function (x) { return !x.open; });
  var openRows = rows.filter(function (x) { return x.open; });
  var ov = '<div class="row-between"><span class="muted">平仓笔数</span><span class="num">' + esc(data.closed != null ? data.closed : closed.length) + '</span></div>'
    + '<div class="row-between"><span class="muted">总盈亏</span><span class="num ' + cls(data.total_pnl) + '">' + _fmtMoney(data.total_pnl) + '</span></div>'
    + '<div class="row-between"><span class="muted">胜率</span><span class="num">' + _fmtRate(data.win_rate) + '</span></div>'
    + '<div class="row-between"><span class="muted">基准收益</span><span class="num ' + cls(data.bench_ret_pct) + '">' + _fmtPctNum(data.bench_ret_pct) + '</span></div>';

  function rowHtml(x) {
    var pnlCls = cls(x.pnl);
    var ret = (x.pnl == null) ? '—' : _fmtPctNum(x.ret_pct);
    var pnlTxt = (x.pnl == null) ? '持仓中' : _fmtMoney(x.pnl);
    return '<tr>'
      + '<td>' + esc(x.code) + '</td>'
      + '<td class="num">' + esc(x.qty) + '</td>'
      + '<td>' + esc(x.buy_date) + '</td>'
      + '<td class="num">' + esc(x.buy_price) + '</td>'
      + '<td>' + esc(x.sell_date || '—') + '</td>'
      + '<td class="num">' + esc(x.sell_price != null ? x.sell_price : '—') + '</td>'
      + '<td class="num ' + pnlCls + '">' + pnlTxt + '</td>'
      + '<td class="num ' + pnlCls + '">' + ret + '</td>'
      + '<td class="num">' + esc(x.annual_pct != null ? _fmtPctNum(x.annual_pct) : '—') + '</td>'
      + '<td class="num">' + esc(x.hold_days != null ? x.hold_days : '—') + '</td>'
      + '<td class="num ' + cls(x.bench_ret_pct) + '">' + esc(x.bench_ret_pct != null ? _fmtPctNum(x.bench_ret_pct) : '—') + '</td>'
      + '<td class="num ' + cls(x.select_pct) + '">' + esc(x.select_pct != null ? _fmtPctNum(x.select_pct) : '—') + '</td>'
      + '</tr>';
  }
  var body = closed.map(rowHtml).join('');
  var openBody = openRows.map(rowHtml).join('');
  var tbl = '<div class="tbl-wrap"><table class="alloc-tbl"><thead><tr>'
    + '<th>代码</th><th>数量</th><th>买日</th><th>买价</th><th>卖日</th><th>卖价</th>'
    + '<th>盈亏</th><th>收益率</th><th>年化</th><th>持有天</th><th>基准</th><th>选股超额</th>'
    + '</tr></thead><tbody>' + (body || '<tr><td colspan="12" class="muted">暂无平仓记录</td></tr>') + '</tbody></table></div>';
  var openTbl = openRows.length
    ? '<div class="hint">未平仓（不计入胜率）：</div>' + '<div class="tbl-wrap"><table class="alloc-tbl"><thead><tr>'
      + '<th>代码</th><th>数量</th><th>买日</th><th>买价</th><th>盈亏</th><th>收益率</th><th>年化</th><th>持有天</th>'
      + '</tr></thead><tbody>' + openBody + '</tbody></table></div>'
    : '';
  return ov + tbl + openTbl;
}

/* ============ 面板 2：风险控制 /api/risk_control ============ */
function _renderRisk(data) {
  if (!data) {
    return '<div class="empty">风险控制数据读取失败。</div>';
  }
  // 不可用但结构仍在：展示口径 + 已有黑名单/敞口
  var isUnavail = (data.available === false);
  var big3 = '<div class="row-between"><span class="muted">VaR95（95% 置信单日最大亏损估计）</span><span class="num ' + cls(data.var95) + '">' + (data.var95 != null ? _fmtMoney(data.var95) : '[暂缺]') + '</span></div>'
    + '<div class="row-between"><span class="muted">组合日波动率</span><span class="num">' + _fmtPctNum(data.port_daily_vol_pct) + '</span></div>'
    + '<div class="row-between"><span class="muted">总市值（估算）</span><span class="num">' + _fmtMoney(data.total_mv) + '</span></div>';

  var stress = data.stress || [];
  var stressTbl = '<div class="hint">4 档压力测试（情景 / 估算损失）：</div>'
    + '<div class="tbl-wrap"><table class="alloc-tbl"><thead><tr><th>情景</th><th>估算损失</th></tr></thead><tbody>'
    + (stress.length ? stress.map(function (s) {
        return '<tr><td>' + esc(s.scenario) + '</td><td class="num ' + cls(s.loss) + '">' + _fmtMoney(s.loss) + '</td></tr>';
      }).join('') : '<tr><td colspan="2" class="muted">暂无压力测试数据</td></tr>')
    + '</tbody></table></div>';

  var exp = data.exposure || [];
  var expTbl = '<div class="hint">逐票敞口：</div>'
    + '<div class="tbl-wrap"><table class="alloc-tbl"><thead><tr><th>代码</th><th>名称</th><th>市值</th><th>日波动率</th></tr></thead><tbody>'
    + (exp.length ? exp.map(function (e) {
        return '<tr><td>' + esc(e.code) + '</td><td>' + esc(e.name) + '</td><td class="num">' + _fmtMoney(e.mv) + '</td><td class="num">' + _fmtPctNum(e.daily_vol_pct) + '</td></tr>';
      }).join('') : '<tr><td colspan="4" class="muted">暂无敞口数据</td></tr>')
    + '</tbody></table></div>';

  var bl = data.blacklist || [];
  var blList = '<div class="hint">黑名单（在下方输入代码与原因后点「添加」）：</div>'
    + (bl.length ? '<div class="tbl-wrap"><table class="alloc-tbl"><thead><tr><th>代码</th><th>原因</th><th>时间</th><th></th></tr></thead><tbody>'
      + bl.map(function (b) {
          return '<tr><td>' + esc(b.code) + '</td><td>' + esc(b.reason || '') + '</td><td class="muted">' + esc(b.at || '') + '</td>'
            + '<td><button class="alloc-btn" data-v86-bl-del="' + esc(b.code) + '">删除</button></td></tr>';
        }).join('')
      + '</tbody></table></div>'
      : '<div class="muted">黑名单为空。</div>')
    + '<div class="row-between" style="margin-top:8px">'
    + '<input class="v86-input" data-v86-bl-code placeholder="代码 如 600519" style="width:120px">'
    + '<input class="v86-input" data-v86-bl-reason placeholder="原因" style="flex:1">'
    + '<button class="alloc-btn" data-v86-bl-add>添加</button></div>';

  var note = '<div class="sub-line">口径：VaR95 = 1.645 × 组合日波动率 × 总市值；个股波动率取近 60 日日线；'
    + '假设持仓完全相关（保守上界）、未计分散化；市值按 买入价×手数×100 估算、非实时市值。</div>';

  var warn = isUnavail
    ? '<div class="empty">风险面板暂不可用：' + esc(data.reason || '未知原因') + '。以下为最近已知快照，非实时。</div>'
    : '';
  return warn + big3 + stressTbl + expTbl + blList + note;
}

/* ============ 面板 3：个股因子 /api/stock_factors ============ */
function _renderFactor(data) {
  if (!data || data.available === false || data.ok === false) {
    var r = (data && data.reason) ? data.reason : '数据暂不可用';
    return '<div class="empty">个股因子不可用：' + esc(r) + '。</div>';
  }
  var items = data.items || [];
  if (!items.length) return '<div class="empty">暂无个股因子数据。</div>';
  var tbl = '<div class="tbl-wrap"><table class="alloc-tbl"><thead><tr>'
    + '<th>代码</th><th>名称</th><th>PE 分位</th><th>PB</th><th>20 日动量</th>'
    + '</tr></thead><tbody>'
    + items.map(function (x) {
        return '<tr>'
          + '<td>' + esc(x.code) + '</td>'
          + '<td>' + esc(x.name) + '</td>'
          + '<td class="num">' + (x.pe_pct != null ? _fmtPctNum(x.pe_pct) : '[暂缺]') + '</td>'
          + '<td class="num">' + (x.pb != null ? esc(x.pb) : '[暂缺]') + '</td>'
          + '<td class="num">' + (x.momentum_20d_pct != null ? _fmtPctNum(x.momentum_20d_pct) : '[暂缺]') + '</td>'
          + '</tr>';
      }).join('')
    + '</tbody></table></div>'
    + '<div class="sub-line">分位来自 stock_valuation.json；动量来自腾讯前复权日线。字段缺失显示 [暂缺]，不以 0 填充。</div>';
  return tbl;
}

/* ============ 面板 4：AI 洞察 /api/ai_insights ============ */
function _renderAi(data) {
  if (!data || data.available === false || data.ok === false) {
    var r = (data && data.reason) ? data.reason : 'AI 洞察暂不可用';
    return '<div class="empty">AI 洞察不可用：' + esc(r)
      + '。启用路径：设置 → 抖音/信息雷达 配置里的 LLM 开关。本面板不显示任何模拟洞察。</div>';
  }
  var items = data.items || [];
  if (!items.length) return '<div class="empty">暂无 AI 洞察。</div>';
  var cards = items.map(function (it) {
    return '<div class="panel"><div class="hint">' + esc(it.type || '洞察') + '</div>'
      + '<div class="row-between"><span>' + esc(it.title || '') + '</span></div>'
      + '<div class="muted">' + esc(it.text || '') + '</div></div>';
  }).join('');
  var meta = '<div class="sub-line">生成日期：' + esc(data.date || '—') + '；'
    + (data.cached ? '来源：缓存（非实时）' : '来源：实时生成')
    + '。LLM 生成，非投资建议，需自行核实。'
    + ' <button class="alloc-btn" data-v86-ai-refresh>重新生成</button></div>';
  return cards + meta;
}

/* ============ 面板 5：Top3 稳定性 /api/recs_hitrate ============ */
function _renderHit(data) {
  if (!data || data.available === false || data.ok === false) {
    var r = (data && data.reason) ? data.reason : '样本不足';
    return '<div class="empty">Top3 策略稳定性暂不可计算：' + esc(r)
      + '。每月 1 日自动回测后累积，满 2 次才能算稳定性。</div>';
  }
  var runs = data.history || [];
  var latest = data.latest;
  var head = '<div class="row-between"><span class="muted">留存率 / 稳定性</span><span class="num">' + _fmtRate(data.stability_pct) + '</span></div>'
    + '<div class="sub-line">术语说明：此处为「Top3 策略留存率 / 稳定性」，绝非命中率或胜率。</div>';
  var list = '<div class="tbl-wrap"><table class="alloc-tbl"><thead><tr><th>日期</th><th>Top3 名单（key / 名称 / 得分）</th></tr></thead><tbody>'
    + runs.map(function (h) {
        var names = (h.top3 || []).map(function (t) { return esc(t.key) + ' ' + esc(t.name) + ' ' + (t.score != null ? t.score : ''); }).join('、');
        return '<tr><td>' + esc(h.date || '') + '</td><td>' + (names || '—') + '</td></tr>';
      }).join('')
    + '</tbody></table></div>';
  var latestLine = latest ? '<div class="hint">最近一次（' + esc(latest.date || '') + '）：'
    + (latest.top3 || []).map(function (t) { return esc(t.name); }).join('、') + '</div>' : '';
  return head + list + latestLine;
}

/* ============ 面板 6：大盘趋势结构（复用 state.market，零新增请求）============ */
function _renderMkt(mkt) {
  if (!mkt || mkt.available === false || mkt.ok === false) {
    var r = (mkt && mkt.reason) ? mkt.reason : '趋势数据不可用';
    return '<div class="empty">大盘趋势结构不可用：' + esc(r) + '。</div>';
  }
  var idx = mkt.index || {};
  var crossMap = { golden: '金叉', death: '死叉', hold: '延续' };
  var stateMap = { healthy: '健康', danger: '危险' };
  var html = '<div class="row-between"><span class="muted">现价</span><span class="num">' + esc(idx.price != null ? idx.price : '—') + '</span></div>'
    + '<div class="row-between"><span class="muted">MA20</span><span class="num">' + esc(idx.ma20 != null ? idx.ma20 : '—') + '</span></div>'
    + '<div class="row-between"><span class="muted">MA60</span><span class="num">' + esc(idx.ma60 != null ? idx.ma60 : '—') + '</span></div>'
    + '<div class="row-between"><span class="muted">MA200</span><span class="num">' + esc(idx.ma200 != null ? idx.ma200 : '—') + '</span></div>'
    + '<div class="row-between"><span class="muted">多空状态</span><span class="num">' + esc(stateMap[mkt.breadth_state] || mkt.breadth_state || '—') + '</span></div>'
    + '<div class="row-between"><span class="muted">均线交叉</span><span class="num">' + esc(crossMap[mkt.breadth_cross] || mkt.breadth_cross || '—') + '</span></div>'
    + '<div class="row-between"><span class="muted">仓位建议</span><span class="num">' + esc(mkt.position_advice || '—') + '</span></div>'
    + '<div class="sub-line">趋势结构层，腾讯前复权日线；与盘中情绪指数不同源，不可并列比较或相加。'
    + '本面板仅补均线数值与交叉状态，不重复渲染「健康/危险」结论。数据源：' + esc(mkt.source || '—') + '，更新于 ' + esc(mkt.updated_at || '—') + '。</div>';
  return html;
}

/* ============ 面板 7：行业温度象限 /api/sector_temperature ============ */
function _renderTemp(data) {
  if (!data || data.available === false || data.ok === false) {
    var r = (data && data.reason) ? data.reason : '数据暂不可用';
    return '<div class="empty">行业温度不可用：' + esc(r) + '。与收盘复盘热力网格同源，可前往查看绝对涨跌。</div>';
  }
  var items = (data.items || []).slice();
  var n = items.length;
  if (!n) return '<div class="empty">暂无行业温度数据。</div>';
  // 横截面分位：升序排名 / (n-1) * 100
  var byPct = items.slice().sort(function (a, b) { return (a.signal_pct || 0) - (b.signal_pct || 0); });
  var pctRank = {};
  byPct.forEach(function (it, i) { pctRank[it.code] = n > 1 ? Math.round(i / (n - 1) * 100) : 50; });
  var byFlow = items.slice().sort(function (a, b) { return (a.flow || 0) - (b.flow || 0); });
  var flowRank = {};
  byFlow.forEach(function (it, i) { flowRank[it.code] = n > 1 ? Math.round(i / (n - 1) * 100) : 50; });

  function quad(it) {
    var p = pctRank[it.code], f = flowRank[it.code];
    if (p >= 50 && f >= 50) return '量价共振';
    if (p >= 50 && f < 50) return '价强钱弱（派发风险）';
    if (p < 50 && f >= 50) return '资金潜伏';
    return '量价齐弱';
  }
  var groups = { '量价共振': [], '价强钱弱（派发风险）': [], '资金潜伏': [], '量价齐弱': [] };
  items.forEach(function (it) { groups[quad(it)].push(it); });

  function bar(label, val, clsName) {
    return '<div class="row-between"><span class="muted">' + label + '</span>'
      + '<span class="num ' + clsName + '">' + val + '</span></div>'
      + '<div style="height:6px;background:var(--surface);border-radius:4px;overflow:hidden;margin:2px 0 6px">'
      + '<div style="width:' + Math.max(2, Math.min(100, val)) + '%;height:100%;background:var(--' + (clsName === 'up' ? 'up' : clsName === 'down' ? 'down' : 'muted') + ')"></div></div>';
  }
  var out = '';
  Object.keys(groups).forEach(function (g) {
    if (!groups[g].length) return;
    out += '<div class="hint">' + esc(g) + '（' + groups[g].length + ' 个行业）</div>';
    out += groups[g].map(function (it) {
      return '<div class="panel"><div class="row-between"><span>' + esc(it.name) + '</span>'
        + '<span class="num ' + cls(it.signal_pct) + '">' + _fmtPctNum(it.signal_pct) + '</span></div>'
        + bar('涨跌幅分位', pctRank[it.code], cls(it.signal_pct))
        + bar('净流入分位', flowRank[it.code], cls(it.flow))
        + '<div class="muted">主力净流入：' + (it.flow != null ? esc(it.flow) + ' 亿元' : '[暂缺]') + '</div></div>';
    }).join('');
  });
  out += '<div class="sub-line">与收盘复盘「行业热力网格」同源（数据宝申万一级），此处为横截面相对位置与量价配合，'
    + '非重复展示绝对涨跌；不构成趋势判断。signal_pct=当日涨跌幅(%)，flow=主力净流入(亿元)。快照日期：' + esc(data.date || '—') + '。</div>';
  return out;
}

/* ============ 面板 8：资讯流 /api/news_feed ============ */
function _renderNews(data) {
  if (!data || data.available === false || data.ok === false) {
    var r = (data && data.reason) ? data.reason : '资讯源不可用';
    return '<div class="empty">资讯流不可用：' + esc(r)
      + '。可前往「博主情报」查看：<button class="alloc-btn" data-v86-act="goto-blog">去看博主情报</button></div>';
  }
  var items = data.items || [];
  if (!items.length) return '<div class="empty">暂无资讯。</div>';
  return items.map(function (x) {
    // 注意：items 无 url 字段，不编造链接
    return '<div class="panel"><div class="row-between"><span>' + esc(x.title || '') + '</span>'
      + '<span class="muted">' + esc(x.time || '') + '</span></div>'
      + (x.src ? '<div class="muted">来源：' + esc(x.src) + '</div>' : '') + '</div>';
  }).join('');
}

/* ============ 三个 load（并发请求各自面板、失败隔离）============ */

async function loadV86Hold(force) {
  await _v86Guard('attr', force, async function () {
    var d = await apiGet('/api/trade_attribution');
    _v86Set('attr', _renderAttr(d));
    _v86Sub('attr', d && d.available === false ? '[STALE] 持仓归因不可用，保留上一版' : '持仓归因已加载');
  });
  await _v86Guard('risk', force, async function () {
    var d = await apiGet('/api/risk_control');
    _v86Set('risk', _renderRisk(d));
    _v86Sub('risk', d && d.available === false ? '[STALE] 风险面板降级，保留上一版快照' : '风险控制已加载');
  });
  await _v86Guard('factor', force, async function () {
    var d = await apiGet('/api/stock_factors');
    _v86Set('factor', _renderFactor(d));
    _v86Sub('factor', d && d.available === false ? '[STALE] 个股因子不可用，保留上一版' : '个股因子已加载');
  });
}

async function loadV86Recs(force) {
  await _v86Guard('ai', force, async function () {
    var d = await apiGet('/api/ai_insights' + (force ? '?refresh=1' : ''));
    _v86Set('ai', _renderAi(d));
    _v86Sub('ai', d && d.available === false ? '[STALE] AI 洞察不可用，保留上一版' : 'AI 洞察已加载');
  });
  await _v86Guard('hit', force, async function () {
    var d = await apiGet('/api/recs_hitrate');
    _v86Set('hit', _renderHit(d));
    _v86Sub('hit', d && d.available === false ? '[STALE] 稳定性样本不足，保留上一版' : 'Top3 稳定性已加载');
  });
}

async function loadV86Mood(force) {
  await _v86Guard('mkt', force, async function () {
    var mkt = (typeof state !== 'undefined' && state && state.market) ? state.market : null;
    if (!mkt || mkt.available === false) {
      try { mkt = await apiGet('/api/market_state'); } catch (e) { mkt = null; }
    }
    _v86Set('mkt', _renderMkt(mkt));
    _v86Sub('mkt', (!mkt || mkt.available === false) ? '[STALE] 趋势结构不可用，保留上一版' : '大盘趋势结构已加载');
  });
  await _v86Guard('temp', force, async function () {
    var d = await apiGet('/api/sector_temperature');
    _v86Set('temp', _renderTemp(d));
    _v86Sub('temp', d && d.available === false ? '[STALE] 行业温度不可用，保留上一版' : '行业温度象限已加载');
  });
  await _v86Guard('news', force, async function () {
    var d = await apiGet('/api/news_feed');
    _v86Set('news', _renderNews(d));
    _v86Sub('news', d && d.available === false ? '[STALE] 资讯流不可用，保留上一版' : '资讯流已加载');
  });
}

/* ============ 黑名单增删（风险面板内）============ */
async function _v86AddBlacklist(scopeEl) {
  var codeEl = (scopeEl || document).querySelector('[data-v86-bl-code]');
  var reasonEl = (scopeEl || document).querySelector('[data-v86-bl-reason]');
  var code = codeEl && codeEl.value ? codeEl.value.trim() : '';
  var reason = reasonEl && reasonEl.value ? reasonEl.value.trim() : '';
  if (!code) { toast('请先填写代码'); return; }
  try {
    await apiPost('/api/risk_control?action=add&code=' + encodeURIComponent(code) + '&reason=' + encodeURIComponent(reason));
    toast('已加入黑名单：' + code);
    await loadV86Hold(false);
  } catch (e) {
    toast('添加失败：' + ((e && e.message) || '异常'));
  }
}
async function _v86DelBlacklist(code) {
  if (!code) return;
  try {
    await apiGet('/api/risk_control?action=del&code=' + encodeURIComponent(code));
    toast('已删除黑名单：' + code);
    await loadV86Hold(false);
  } catch (e) {
    toast('删除失败：' + ((e && e.message) || '异常'));
  }
}

/* ============ 事件委托（initV86 仅绑一次）============ */
var _v86Inited = false;
function initV86() {
  if (_v86Inited) return;            // 幂等
  _v86Inited = true;
  document.addEventListener('click', function (ev) {
    var t = ev.target;
    if (!t || !t.closest) return;

    // 重新加载按钮
    var reload = t.closest('[data-v86-reload]');
    if (reload) {
      var which = reload.getAttribute('data-v86-reload');
      if (which === 'hold') loadV86Hold(true);
      else if (which === 'recs') loadV86Recs(true);
      else if (which === 'mood') loadV86Mood(true);
      return;
    }

    // AI 重新生成
    var ai = t.closest('[data-v86-ai-refresh]');
    if (ai) { loadV86Recs(true); return; }

    // 黑名单添加（在风险面板作用域内读取输入框）
    var add = t.closest('[data-v86-bl-add]');
    if (add) { _v86AddBlacklist(add.closest('[data-v86="risk"]')); return; }

    // 黑名单删除
    var del = t.closest('[data-v86-bl-del]');
    if (del) { _v86DelBlacklist(del.getAttribute('data-v86-bl-del')); return; }

    // 跳转博主情报
    var act = t.closest('[data-v86-act="goto-blog"]');
    if (act) { switchTab('blog'); return; }
  });
}

// 暴露全局（A 的 boot 里调用 initV86()，各视图切换时调用对应 load）
if (typeof window !== 'undefined') {
  window.initV86 = initV86;
  window.loadV86Hold = loadV86Hold;
  window.loadV86Recs = loadV86Recs;
  window.loadV86Mood = loadV86Mood;
}
```