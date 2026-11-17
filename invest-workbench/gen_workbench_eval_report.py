# -*- coding: utf-8 -*-
"""生成《投资工作台架构·性能评测与开源方案对标报告》HTML。
纯标准库；数据内嵌；零外链；浅色主题；涨红跌绿。
"""
import html
import datetime
import os

OUT = "投资工作台架构性能评测与开源对标_2026-11-18.html"

PAGES = [
    ("今日", "全景首屏：账户条/今日决策/资产配置/核心池净值双图/待办；操作模块默认折叠",
     "区间切换(1m/3m/1y/all)、主行动卡、清缓存浮标",
     "boot 串行拉取 account_baseline→trades→cached→holdingsSnapshot→perf→swing→recs→valuation；/api/pool_daily 双 canvas",
     "首屏节点最密(231 标签/74 id/2 canvas)；15+ 步串行 await 拉长首屏；refreshAll 渲染全量页"),
    ("选股池", "core/watch/other 名单卡牌、近一周收益排名、批量扒取/停扒、管理子页",
     "池筛选、排名键切换、手动/强制/停止扒取",
     "/api/cached + /api/poolcfg + /api/names；持仓 asof 来自 holdings_snapshot.json",
     "卡牌逐张拼 HTML；asof(调仓时间)被误读为抓取时间，历史故障已 bump sw 修"),
    ("跟单推荐", "回测优选 Top3 + 近一周领涨组合；配置方案/权重/条件单三件套",
     "方案切换(8 种含 risk_parity)、资金/手数试算",
     "/api/recs_top3 现场解析 3.1MB strategy_lab.json；/api/recs_momentum 用完整净值缓存",
     "每次请求全量 json.load + 重排；Top3 派生无服务端缓存"),
    ("波段操作", "六分组(立即操作/接近触发/无需动手/不可买/自选/持仓)、买标损三件套",
     "分组切换、自选股增删、刷新",
     "/api/swing 技术判定；触发优先级 止损>目标>买入",
     "分组渲染依赖 refreshAll 全量重绘；自选股补名链路额外请求"),
    ("我的持仓", "持仓表/交易权限/归因逐笔/风控/因子/基金账户/条件单列",
     "15s 盘中现价轮询、买入价防呆、折叠明细",
     "/api/my_holdings?auto=1 每15秒；/api/attribution 逐笔 buy→sell 对齐沪深300",
     "15s 轮询 + renderHold 全表重建；归因逐笔表节点多"),
    ("做T信号", "强/中/弱信号分级，谨慎徽章(历史胜率56.6%/累计-4.19%)",
     "5 分钟盘中自动刷新、强弱排序",
     "/api/tsig；仅当前页+交易时段轮询",
     "轮询已做页面闸门，较好；信号表仍随 refreshAll 重绘"),
    ("我的ETF", "ETF 排名/共识度/轮动信号/本地资金试算",
     "60s 行情轮询、scope/window 切换、恢复本金",
     "/api/etf_rank?scope=、/api/etf_signal、/api/etf_backtest",
     "多接口独立加载；用户编辑态与轮询曾有竞争(已修)"),
    ("业绩跟踪", "核心池等权 vs 沪深300 归一化净值 + 几何超额，双 canvas",
     "1m/3m/1y/all 区间切换、重绘",
     "/api/pool_daily 208KB 全历史(2149天)；区间内归一化 _normSeries",
     "隐藏页宽 0 不画，切页重绘；全历史序列每次整体传输"),
    ("市场情绪", "情绪仪表/分项/广度/3年分位；盘中/收盘双视图(口径硬隔离)",
     "盘中/收盘切换、刷新",
     "/api/mood + /api/sector_rotation + 5 分钟自动刷新",
     "多源降级绘制；[DEGRADED]/[PARTIAL] 状态管理复杂"),
    ("复盘分析", "推荐 vs 实际持仓、盈亏归因、投资月报",
     "静态查看/折叠",
     "/api/review 类接口；依赖账本与净值缓存",
     "低频页，随 refreshAll 重绘属浪费"),
    ("盯盘监控台", "关注标的实时价/到价预警、持仓实时涨跌、东财高手重仓、集思录补充",
     "行情刷新、卡片编辑/移除",
     "/api/watch_quotes + /api/my_holdings；公开源行情",
     "修复过切页漏拉行情；外部源多，部分降级"),
    ("指数估值", "指数/个股估值表、资讯源(eastmoney 固化)",
     "刷新、切换标签",
     "/api/valuation /api/stock_valuation /api/news",
     "低频页；随 refreshAll 重绘"),
    ("趋势保护", "个股趋势 + 大盘 200 日线仓位滤镜",
     "刷新",
     "/api/trend_signal + /api/market_state",
     "与今日页 market 状态有重复取数风险"),
    ("我的策略/实验室", "策略营(自建曲线) + 策略实验室(3池×25策略回测) + 策略说明书",
     "选策略、参数表单、回测曲线切换",
     "/api/strat、/api/strat_lab；strategy_lab.json 3.1MB",
     "回测约 138.6s；大 JSON 每次读取解析；曲线手绘 canvas"),
    ("工具箱", "冠军因子选股独立页入口、现金流水/对账小工具、低频模块折叠",
     "记账、折叠展开",
     "/api/cashflow 等本地读写",
     "低频页随 refreshAll 重绘"),
    ("博主情报", "抖音博主/视频列表、服务端 ASR 转写状态、看视频外链",
     "Cookie 设置、转写、折叠稿",
     "/api/blog_items(1.38MB)、/api/blog_transcript 等；sherpa-onnx 服务端 ASR",
     "大 JSON 列表无分页/虚拟滚动；长文本 DOM 折叠但仍在文档树"),
    ("信息雷达", "本机服务状态灯、情报分析、iframe(本机)/新窗口(线上)",
     "状态检查、操作提示",
     "/api/radar/brief + 本机同步推送",
     "iframe 与跨站策略复杂；推送去重靠状态文件"),
    ("对账单导入", "Excel 解析(快照/流水自动识别)、三类核对、应用",
     "选文件、解析、确认应用",
     "前端解析 + /api/ledger 写回",
     "仅按需加载，影响小"),
    ("设置", "主题/布局/运维状态/提醒/凭据/高级设置折叠",
     "开关切换、测试推送、会话恢复",
     "/api/config /api/session /api/autorefresh /api/ops",
     "78 id/266 标签，单页最重；多接口串行"),
    ("估值弹窗(全局)", "任意 6 位代码三因子合理价、负 PE 原因显示",
     "任意页打开、关闭",
     "/api/fair_value_one?code= 快照命中秒回，否则实时兜底",
     "弹窗 DOM 常驻；按需请求做得较好"),
]

BOTTLENECKS = [
    ("首屏加载", "index.html 1,062,597 B，gzip 后实测 326,156 B / 0.16s（nginx gzip on）",
     "中", "单文件无代码分割；每次版本更新整包失效，sw 需 v97→v98 全量 bump"),
    ("启动链路", "boot() 顶层约 15 个串行 await（baseline/trades/health/session/restore/names/poolcfg/serverCodes/cached/holdings/config/backfill/market/perf/recs/swing/etf/valuation…）",
     "高", "RTT 串行累加；任一慢接口拖慢整体 ready，虽有 safeLoad 隔离但不并行"),
    ("渲染", "refreshAll() 一次调用 26 个 render* 函数；DOM 1438 div / 606 id / 647 内联 style；4 canvas 手绘",
     "高", "隐藏页也重绘；60s 行情轮询每次触发全量刷新；无虚拟列表"),
    ("数据读取", "server.py _json_load() 每次 open+json.load 全量解析：last_snapshot.json 3.43MB、strategy_lab.json 3.11MB、blog_items.json 1.38MB 等；data 目录 170 个 JSON / 27.13MB",
     "高", "无 ETag/304、无进程内 TTL 缓存（仅 _BT/_FV 等局部缓存）；重复请求 CPU 浪费"),
    ("并发", "根服务 ThreadingHTTPServer + daemon_threads，无连接数上限；引擎批量 ThreadPoolExecutor max_workers=6，抓数 max_workers=2",
     "中", "线程无节制创建；上游雪球风控迫使 12只/批+45s 冷却，推送必须 TAT 分片"),
    ("缓存一致性", "sw.js 手写 cache-first/网络回填；ASSETS 预缓存 7 项；API Cache-Control: no-store",
     "中", "版本 bump 全量换缓存；曾出现旧 HTML 外壳 + 新数据的错位（v98 修复）"),
    ("轮询", "持仓 15s、行情 60s、跟单 120s、做T 5min、告警 2min、全量刷新 5–120min(可配)",
     "中", "有页面可见性/交易时段闸门，设计较好；但 refreshAll 范围过大放大每次轮询成本"),
    ("资源占用", "服务进程 VmRSS≈154MB / Threads=2（systemd MainPID）；nginx worker_processes auto, worker_connections 768",
     "低-中", "单机够用；数据量增大后全量 JSON 解析会推高内存与 GC"),
    ("回测", "strategy_lab 3 池 × 25 策略 × ~1250 日窗口，上次 elapsed=138.6s；每月 1 日 04:30 timer",
     "中", "纯 Python 逐策略循环；可接受但向量化/并行仍有明显空间"),
]

PAGE_ROWS = "".join(
    "<tr><td><b>%s</b></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" %
    tuple(html.escape(x) for x in row) for row in PAGES
)
BOTTLE_ROWS = "".join(
    "<tr><td><b>%s</b></td><td>%s</td><td><span class='sev s%s'>%s</span></td><td>%s</td></tr>" %
    (html.escape(a), html.escape(b), {"高":"3","中":"2","低-中":"1"}.get(c,"2"), html.escape(c), html.escape(d))
    for a,b,c,d in BOTTLENECKS
)

# 开源方案数据由外部检索 + GitHub API 核验；首版由前端检索代理产出，后端部分待补。
CANDIDATES = []  # 由 append_candidates.py 注入
CANDIDATE_HTML = ""
ROADMAP_HTML = ""

def render_candidates(rows):
    out=[]
    for r in rows:
        name, url, meta, match, perf, basis, scene, use, risk, cost = r
        cls = {"适合当前工作台":"fit","需谨慎接入":"care","高风险":"risk"}[risk]
        out.append(
            "<tr><td><a href='%s' target='_blank' rel='noopener'>%s</a><div class='meta'>%s</div></td>"
            "<td>%s</td><td>%s<div class='meta'>依据：%s</div></td><td>%s</td><td>%s</td>"
            "<td><span class='badge %s'>%s</span><div class='meta'>成本：%s</div></td></tr>" %
            (html.escape(url), html.escape(name), html.escape(meta),
             html.escape(match), html.escape(perf), html.escape(basis), html.escape(scene),
             html.escape(use), cls, html.escape(risk), html.escape(cost))
        )
    return "".join(out)

ROADMAP = [
    ("P0", "启动并行化 + 接口合并", "把 boot() 的 15 步串行 await 改为按依赖分组 Promise.allSettled；/api/boot 聚合 baseline/names/poolcfg 等小接口；非首屏数据延迟到 idle 加载",
     "首屏可交互时间缩短 40%–60%（预计从 1–2s 降至 0.5–1s，需实测验证）", "FCP/TTI、boot stage 耗时、首次请求数、pageerror=0"),
    ("P0", "渲染按页订阅化", "refreshAll() 拆成 renderVisible(view) + 事件订阅表；行情轮询只重渲染持仓/今日相关卡片，隐藏页不重绘",
     "每次 60s 轮询的 JS 执行时间降 60%–80%；15s 持仓轮询不再触发 26 个渲染函数", "Performance 面板 scripting 时长、长任务数、DOM 变更数"),
    ("P0", "服务端大 JSON 缓存 + ETag", "给 _json_load 加 mtime+TTL 内存缓存；/api/cached、/api/recs_top3、/api/blog_items 支持 ETag/304 与分页游标",
     "3.4MB 快照与 3.1MB 回测结果不再每次重解析；带宽与 CPU 双降", "单请求耗时 p95、传输字节、缓存命中率、304 比例"),
    ("P1", "虚拟列表 / 分页", "博客情报(1.38MB)、选股池卡牌(76 组合)、日志类长列表引入虚拟滚动或分页；优先纯前端 IntersectionObserver 方案",
     "DOM 节点数与首屏渲染时间下降；长列表滚动不掉帧", "DOM 节点数、滚动 FPS、列表首帧时间"),
    ("P1", "图表层替换/局部优化", "评估 uPlot（约 45KB min，官方 benchmark 万点级交互仍流畅）替换手绘净值曲线；或先保留 canvas 仅加离屏缓存与增量绘制",
     "4 个 canvas 的重绘成本下降；曲线交互更顺；避免引入 ESM 构建", "canvas 绘制耗时、切换区间帧率、包体积增量"),
    ("P1", "回测向量化/缓存", "用 Polars/DuckDB 读取 OHLC 面板并预计算 sigma20 等指标；策略结果按数据指纹缓存；并行跑独立策略（现有 138.6s 有下降空间）",
     "月度回测端到端时间预计 138.6s → 30–60s；结果可复现性提升", "回测 elapsed_sec、内存峰值、逐策略结果一致性"),
    ("P2", "PWA 缓存工程化", "评估 Workbox 生成 SW（预缓存清单/版本哈希/导航回退），或至少把当前手写 SW 的 bump 流程自动化并加单测",
     "消除旧外壳+新数据错位；发布不再依赖人工 bump sw.js", "缓存命中率、版本错位工单数、部署后首屏 SHA 一致率"),
    ("P2", "数据代理链路加固", "保持本机住宅 IP 抓取 + TAT 分片推送；引入增量序号与幂等合并校验、失败重放队列；不迁移到服务端直抓",
     "上游风控下仍保持数据新鲜；重复推送安全", "净值/持仓 asof 推进及时率、推送失败可恢复率"),
]

def render_roadmap():
    return "".join(
        "<tr><td><span class='badge %s'>%s</span></td><td><b>%s</b></td><td>%s</td><td>%s</td><td>%s</td></tr>" %
        ({"P0":"risk","P1":"care","P2":"fit"}[p], p, html.escape(t), html.escape(how), html.escape(gain), html.escape(metric))
        for p,t,how,gain,metric in ROADMAP
    )

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--text:#1d2129;--muted:#6b7280;--border:#e3e6eb;--primary:#2f5fd0;--up:#d92626;--down:#12864b;--warn:#b4690e;--fit:#12864b;--care:#b4690e;--risk:#c92a2a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.65 -apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif}
.wrap{max-width:1280px;margin:0 auto;padding:28px 22px 80px}
h1{font-size:26px;margin:0 0 6px}h2{font-size:19px;margin:34px 0 12px;padding-left:10px;border-left:4px solid var(--primary)}h3{font-size:15px;margin:18px 0 8px}
.lead{color:var(--muted);margin:0 0 22px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:18px 0}
.card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px 16px}
.kpi{font-size:24px;font-weight:700;color:var(--primary)}.lbl{color:var(--muted);font-size:12px}
.tbl{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--border);border-radius:8px;overflow:hidden;font-size:13px}
.tbl th,.tbl td{padding:9px 10px;border-bottom:1px solid var(--border);vertical-align:top;text-align:left}
.tbl th{background:#eef2f8;font-weight:600;white-space:nowrap}.tbl tr:last-child td{border-bottom:0}
.tbl td:nth-child(1){white-space:nowrap}.meta{color:var(--muted);font-size:11px;margin-top:3px}
a{color:var(--primary);text-decoration:none}a:hover{text-decoration:underline}
.badge{display:inline-block;padding:1px 8px;border-radius:10px;color:#fff;font-size:11px;white-space:nowrap}
.badge.fit{background:var(--fit)}.badge.care{background:var(--care)}.badge.risk{background:var(--risk)}
.sev{display:inline-block;padding:1px 7px;border-radius:9px;font-size:11px;color:#fff}.s3{background:var(--risk)}.s2{background:var(--care)}.s1{background:var(--fit)}
.note{background:#fff7e6;border:1px solid #f3d9a4;border-radius:8px;padding:10px 14px;margin:12px 0;color:#754c13}
.ok{background:#eaf7ef;border:1px solid #b7e0c4;border-radius:8px;padding:10px 14px;margin:12px 0;color:#135c34}
ul{margin:6px 0 6px 20px;padding:0}li{margin:3px 0}
footer{margin-top:40px;color:var(--muted);font-size:12px;border-top:1px solid var(--border);padding-top:14px}
@media(max-width:760px){.wrap{padding:16px 10px 60px}.tbl{font-size:12px;display:block;overflow-x:auto}.tbl th,.tbl td{min-width:110px}}
"""

def main():
    global CANDIDATE_HTML
    body = f"""<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>投资工作台架构性能评测与开源对标 2026-11-18</title><style>{CSS}</style></head><body><div class='wrap'>
<h1>投资工作台 · 架构与性能评测 / 开源方案对标</h1>
<p class='lead'>生成时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} · 口径：本地源码静态统计 + 线上 TAT 实测 + GitHub API 元数据核验（检索时间 2026-11-18）· 性能数字区分「实测」与「官方宣称」</p>
<div class='cards'>
<div class='card'><div class='kpi'>20</div><div class='lbl'>桌面页签（另有 4 入口移动 DOM）</div></div>
<div class='card'><div class='kpi'>1.04MB</div><div class='lbl'>index.html 原始 / gzip 326KB 实测</div></div>
<div class='card'><div class='kpi'>517</div><div class='lbl'>顶层 JS 函数；inline onclick 43 处</div></div>
<div class='card'><div class='kpi'>129</div><div class='lbl'>服务端 /api 路由；前端引用 118</div></div>
<div class='card'><div class='kpi'>27.13MB</div><div class='lbl'>data 目录 170 个 JSON</div></div>
<div class='card'><div class='kpi'>~154MB</div><div class='lbl'>服务进程 VmRSS 实测</div></div>
</div>

<h2>一、逐页功能 / 交互 / 数据流 / 瓶颈</h2>
<table class='tbl'><thead><tr><th>页面</th><th>核心功能</th><th>关键交互</th><th>数据流</th><th>当前瓶颈/注意</th></tr></thead><tbody>{PAGE_ROWS}</tbody></table>
<div class='note'>另有独立页：<b>/factor-picker.html</b>（冠军因子选股名单，2026-11-17 更新）、<b>/replay.html</b>、冻结移动页 <b>m.html</b>（仅 /m 显式入口）；SW 预缓存 7 项。前端真值源为 <code>src/parts/</code>（57 片段 + manifest），index.html 是构建产物，改动须走 build → 契约测试 → bump sw → 部署。</div>

<h2>二、性能瓶颈（按严重度标注）</h2>
<table class='tbl'><thead><tr><th>环节</th><th>证据（实测/静态）</th><th>严重度</th><th>成因与影响</th></tr></thead><tbody>{BOTTLE_ROWS}</tbody></table>

<h2>三、GitHub / 全网同类高性能方案对标</h2>
<p class='lead'>检索顺序：先 GitHub（ stars / 最近推送由 GitHub API 于 2026-11-18 核验），结果不足再扩展到全网公开仓库与官方文档。风险分级以「当前单文件 SPA + Python 标准库后端 + 上游风控代理抓取」这套约束为基准。</p>
<table class='tbl'><thead><tr><th>项目 / 元数据</th><th>功能匹配点</th><th>性能优势与依据</th><th>适用场景</th><th>可借鉴改进方向</th><th>分级与成本</th></tr></thead><tbody>{CANDIDATE_HTML}</tbody></table>

<h2>四、整体评测</h2>
<ul>
<li><b>功能覆盖度：优秀</b> — 20 页签覆盖选股、持仓、条件单、估值、业绩、情绪、回测、雷达、账本、ASR 等完整投资闭环；多数页面有明确降级/口径提示，数据真实性约束强（不编数）。</li>
<li><b>架构一致性：良好但耦合重</b> — parts 构建链、契约测试、令牌化主题、PWA 独立页分流等约束清晰；代价是 517 个全局函数、单文件 1.04MB、4 script/3 style 硬契约，任何局部优化都要全量重建。</li>
<li><b>加载性能：中等</b> — gzip 后 326KB / 0.16s 传输并不慢，真正耗时在启动 15 步串行请求与随后的全量渲染；PWA 让二次访问更快，但也引入过缓存错位。</li>
<li><b>渲染效率：偏弱</b> — refreshAll() 26 个渲染函数无差别执行、隐藏页照画、无虚拟列表、canvas 手绘；这是当前最值得改的部分。</li>
<li><b>资源与并发：够用但有上限</b> — 单进程 ~154MB、2 线程；ThreadingHTTPServer 无连接上限，大 JSON 每次全量解析；上游风控决定抓取只能代理+分批，短期不要推翻。</li>
<li><b>维护状态：活跃</b> — 服务端 7 个 systemd timer + 本机 15 个自动化（净值 7、持仓 8）在跑；本次评测时全链路均正常。</li>
</ul>

<h2>五、优先级改进路线（按收益/成本排序）</h2>
<table class='tbl'><thead><tr><th>优先级</th><th>方向</th><th>具体做法</th><th>预期收益</th><th>验证指标</th></tr></thead><tbody>{ROADMAP_HTML}</tbody></table>
<div class='ok'><b>建议的第一刀：</b>P0 三项（启动并行化 / 渲染订阅化 / 大 JSON 缓存+ETag）都属于「不动数据结构、不动导航契约、不动抓取链路」的局部改造，可在保持单文件 SPA 与 20 页签契约不变的前提下完成，风险低、收益可直接测量。P1/P2 涉及库替换或缓存机制改造，建议逐项做 A/B 验证后再决定是否合并。</div>

<h2>六、方法与局限</h2>
<ul>
<li>量化依据来自：本机 <code>build_frontend.py --verify</code> / <code>test_frontend_build.py</code> 契约、静态代码统计、线上 curl（gzip 响应与传输体积）、TAT 读取服务器 JSON 体积与 systemd timers/进程 RSS。</li>
<li>开源项目的 stars / pushed_at 为 GitHub API 当场核验；性能数字若为官方 benchmark 会在依据栏标注，未标注者属结构性推断（如"避免全量解析"），不等同于实测加速比。</li>
<li>未做真机 Profiler 录制（受当前会话工具限制）；所有"预计收益"须按表中验证指标在改造前后各测一次再确认。</li>
</ul>
<footer>投资工作台评测报告 · 生成脚本 gen_workbench_eval_report.py · 源码目录 投资工作台_full/src · 输出 02.输出区</footer>
</div></body></html>"""

    if CANDIDATES:
        CANDIDATE_HTML = render_candidates(CANDIDATES)
    body = body.replace("{CANDIDATE_HTML}", globals().get("CANDIDATE_HTML", ""))
    body = body.replace("{ROADMAP_HTML}", render_roadmap())
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), OUT)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    print("WROTE", path, len(body))

if __name__ == "__main__":
    main()
