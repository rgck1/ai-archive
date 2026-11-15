# 给 B 的指令（v86 前端模块协作）· 2026-11-15

（以下从「===== 复制开始 =====」到「===== 复制结束 =====」整段可直接复制给 B）

===== 复制开始 =====

你是 B，与 A 分工协作完成「投资工作台 v86」的前端部分。用户反馈 A 的免费额度吃紧，
所以把可独立交付的部分交给你。你做完请**自行上传到 GitHub 仓库**，A 会从仓库读取并集成。

## 一、先找到并阅读仓库

仓库地址：https://github.com/rgck1/ai-archive （public，默认分支 `main`）

公开只读，不需要 token。请按顺序读这几个文件，对齐用户的协作偏好与硬性规则：

1. https://raw.githubusercontent.com/rgck1/ai-archive/main/README.md
2. https://raw.githubusercontent.com/rgck1/ai-archive/main/about-me.md
3. https://raw.githubusercontent.com/rgck1/ai-archive/main/writing-style.md
4. https://raw.githubusercontent.com/rgck1/ai-archive/main/rules.md
5. https://raw.githubusercontent.com/rgck1/ai-archive/main/projects.md

再读交换协议：
6. https://raw.githubusercontent.com/rgck1/ai-archive/main/handoff/README.md
   （若 404 说明 A 还没上传成功，不要卡住——本协议内容已完整包含在本指令第三节，
   按本指令执行即可）

目录清单可用公开 API 查（无需 token）：
https://api.github.com/repos/rgck1/ai-archive/contents/handoff

## 二、重要现状（别踩坑）

- 仓库根目录目前只有 7 个 md 文件：README / about-me / projects / rules /
  writing-style / 发布说明 / 接入指南。**没有** `handoff/` 目录，也没有
  `invest-workbench/`（本地有，但从没同步上去）。
- `handoff/` 目录**需要你创建**。
- 仓库根目录的 `sync_ai_archive.py`（若你看到）**不能用来传 handoff**：
  它只遍历根目录顶层文件、跳过子目录和所有 .py。你必须用
  **GitHub Contents API 或 git** 上传，见第五节。
- **A 当前无写权限**：A 这边 `GH_TOKEN` 为空、本地目录也不是 git 仓库，
  所以 A 暂时只能公开读、不能上传。你是当前唯一的写入方。
  A 给你的技术输入已全部写在本指令里，**不依赖仓库里任何尚未存在的文件**。
- 仓库是**公开的**：禁止写入任何密钥、口令、Cookie、token、服务器地址、
  第三方网页账号密码、凭据文件内容。产出文件里也不要出现这些。

## 三、分工

### A 负责（不用你做，了解即可）
- 3 个视图的面板 HTML 骨架插入、新建脚本片段并注册 manifest、`switchTab` 派发
- 构建 / 契约测试 / JS 语法校验 / sw.js bump / 部署上线 / 线上核验
- 合并你的产出、最终回归、在你初稿基础上出最终交付总结

### 你负责（两项，都上传到仓库）
- **B-T1**：`handoff/v86_panels.js` —— 8 个面板的加载 / 渲染 / 降级 / 交互代码
- **B-T2**：`handoff/v86_summary.md` —— 面向用户的《v86 交付总结与待确认事项》初稿
- 另外写 `handoff/STATUS.md`：完成时间、已完成项、遗留问题、需要 A 或用户拍板的事项

## 四、技术契约（必须严格遵守，否则无法与 A 的 HTML 拼合）

### 4.1 运行环境（全部是既有全局函数/变量，直接调用，不要重新实现）
- `apiGet(path, timeoutMs)` / `apiPost(path, body)` —— 带超时的请求
- `$(id)`、`esc(s)`（HTML 转义）、`safeUrl(u)`（外链白名单）、`toast(msg)`
- `cls(v)` → 正数 `"up"`（红）、负数 `"down"`（绿）、0 `"flat"`
- `fmtPctNum(v)` —— v 已是百分数数值（如 1.5 → "+1.50%"）
- `state` —— 全局状态对象，**只读**，不要新增或改写字段
- `switchTab(name)` —— 切页（A 在 switchTab 里调用你的入口）

### 4.2 DOM 契约（A 会在 3 个视图里创建这些容器，**id 与 data 属性一一对应，不许改**）

持仓页 `view-hold`：
- `<div id="attrBox" data-v86="attr">` 交易归因
- `<div id="riskBox" data-v86="risk">` 组合风控
- `<div id="factorBox" data-v86="factor">` 个股因子

跟单页 `view-recs`：
- `<div id="aiInsightBox" data-v86="ai">` AI 每日洞察
- `<div id="recsHitBox" data-v86="hit">` 跟单 Top3 稳定性

情绪页 `view-mood` 的「收盘复盘」子视图：
- `<div id="mktBreadthBox" data-v86="mkt">` 大盘趋势结构
- `<div id="sectorTempBox" data-v86="temp">` 行业温度象限
- `<div id="newsFeedBox" data-v86="news">` 实时资讯

每个面板另有提示行 `<div data-v86-sub="同上的 key">`（如 `data-v86-sub="attr"`）。

### 4.3 关键：移动端克隆 DOM
移动端会在切页后约 800ms 把整个 `#view-*` 的 innerHTML **克隆**到
`#mFeature .m-feature-body`，导致 **id 重复**。因此：
- **禁止**用 `document.getElementById` / `$()` 定位你要写的容器；
- 必须 `document.querySelectorAll('[data-v86="attr"]')` 遍历**所有副本**逐个写 innerHTML；
- 提示行同理用 `[data-v86-sub="attr"]` 遍历；
- 请自己实现 `_v86Set(key, html)` 和 `_v86Sub(key, text)` 两个 helper 统一处理；
- 交互按钮**禁止**用 addEventListener 绑到单个节点（克隆后会失效），
  改用**事件委托**：在 `initV86()` 里对 `document` 绑一次 `click`，
  用 `ev.target.closest('[data-v86-act]')` 分发。这是 A 会调用的唯一初始化函数。

### 4.4 A 在 HTML 里放的交互控件（你只需实现委托响应，不要改 HTML）
- 刷新：`<button data-v86-reload="hold|recs|mood">`，对应调用你的三个入口
- 风控黑名单：输入框 `<input data-v86-bl-code>`、`<input data-v86-bl-reason>`，
  按钮 `<button data-v86-bl-add>`；列表里的删除按钮由你渲染成
  `<button data-v86-bl-del="股票代码">移除</button>`
- AI 洞察强制刷新：`<button data-v86-ai-refresh>`

### 4.5 你必须导出的全局函数（A 会调用，函数名不许改）
```
initV86()                 // 只绑事件委托，幂等；A 在 boot 里调
loadV86Hold(force)        // async，加载 attr/risk/factor
loadV86Recs(force)        // async，加载 ai/hit
loadV86Mood(force)        // async，加载 mkt/temp/news
```
三个 load 要**并发**请求各自面板、彼此独立失败隔离（一个失败不影响其余），
有 busy 标志防重入，`force` 时跳过节流。失败时给对应容器写
`[STALE] 本次读取失败，保留上一版` 标记，**不要清空已有内容、不要编造数据**。

### 4.6 八个接口的真实返回结构（已上线，字段精确，按此渲染）

1. `GET /api/trade_attribution`
```
{ok, available, count, closed, open, total_pnl, win_rate, bench_ret_pct,
 rows:[{code,qty,buy_date,buy_price,sell_date,sell_price,pnl,ret_pct,
        annual_pct,hold_days,bench_ret_pct,select_pct,open}]}
```
- `ret_pct/annual_pct/select_pct/bench_ret_pct` 都是**百分数数值**（如 -3.21 表示 -3.21%）
- `open:true` 是未平仓（pnl 为 null），单独分组，"不计入胜率"
- 不可用：`{ok:false, available:false, reason, rows:[]}`
- 展示：概览（平仓笔数 / 总盈亏 / 胜率 / 基准收益）+ 逐笔表；
  `select_pct` = 个股收益 − 基准，标为「选股超额」；盈亏用 cls() 上色

2. `GET /api/risk_control`
```
{ok, available, total_mv, port_daily_vol_pct, var95,
 stress:[{scenario,loss}],
 blacklist:[{code,reason,at}],
 exposure:[{code,name,mv,daily_vol_pct}]}
```
- 不可用：`{ok:true, available:false, reason, blacklist, var95:null, stress:[], exposure}`
- 增删黑名单：`GET /api/risk_control?action=add&code=600519&reason=xxx`
  或 `?action=del&code=600519`（用 encodeURIComponent）；操作后重新 load 本面板
- 展示：VaR95 / 组合日波动率 / 总市值 三个大数 + 4 档压力测试表
  + 逐票敞口 + 黑名单列表（带移除按钮）
- 必须写明口径：VaR95 = 1.645 × 组合日波动率 × 总市值；
  个股波动率取近 60 日日线；**假设持仓间完全相关（保守上界）、未计分散化**；
  市值按 买入价×手数×100 估算，不是实时市值

3. `GET /api/ai_insights`（`?refresh=1` 强制重算）
```
{ok, available, cached, date, items:[{type,title,text}]}
```
- 不可用：`{ok:false, available:false, reason, items:[]}`
  当前真实 reason = 「智谱 LLM 未启用（设置→抖音/信息雷达 配置里的 llm 开关）」
  → 此时显示明确说明与启用路径，**不要显示假洞察**
- 展示 3 条卡片（量化机会 / 行为诊断 / 市场情绪），标 cached 与日期，
  并注明「LLM 生成，非投资建议，需自行核实」

4. `GET /api/recs_hitrate`
```
{ok, available, runs, stability_pct,
 latest:{date, top3:[{key,name,score}]}, history:[同结构]}
```
- 样本不足：`{ok:true, available:false, reason, runs:[...]}`
  当前真实状态 = 仅 1 次记录，**此处必须优雅降级**，说明
  「每月 1 日自动回测后累积，满 2 次才能算稳定性」
- 术语铁律：这是 **Top3 策略留存率 / 稳定性**，**不是荐股命中率**，
  绝不能写成「命中率」「胜率」。展示历史每次 Top3 名单 + 留存率

5. `GET /api/sector_temperature`
```
{ok, available, date, source,
 items:[{name,code,signal_pct,flow,status}]}
```
- 不可用：`{ok:false, available:false, reason, items:[]}`
- **字段真实含义**：`signal_pct` = 申万一级行业**当日涨跌幅(%)**，
  `flow` = **主力净流入(亿元)**，数据源 = 数据宝申万一级（与情绪页
  「收盘复盘·行业热力网格」**同一份** `sector_rotation_latest.json`）。
  后端注释里「轮动强度/资金流强度」的说法不准确，以本条为准。
- **避免重复实现是硬要求**：不要再做一张涨跌/净额表（热力网格已有）。
  请改做**横截面相对位置 + 量价配合**这种新增信息：
  - 对 31 个行业分别算 `signal_pct` 的横截面分位 `pctRank`(0~100)
    与 `flow` 的横截面分位 `flowRank`(0~100)（升序排名 / (n-1) × 100）
  - 按 50 分位划四象限：
    `量价共振`(双高) / `价强钱弱`(价高钱低，派发风险) /
    `资金潜伏`(价低钱高) / `量价齐弱`(双低)
  - 每行业给两条分位条（用 --fs-* 字号、var(--token) 配色）+ 绝对涨跌/净额小字
  - 按四象限分组展示，突出 `价强钱弱` 与 `资金潜伏` 两类背离
  - 明确标注：「与收盘复盘热力网格同源，此处为横截面相对位置与量价配合，
    非重复展示绝对涨跌；不构成趋势判断」
  - `status` 字段可忽略不用

6. `GET /api/news_feed`
```
{ok, available, items:[{title,time,src}]}
```
- 不可用：`{ok:true, available:false, reason, items:[]}`
  当前云服务器 IP 被限流，reason = 「资讯源暂不可达…本机刷新可补齐；
  当前先用博主情报替代」→ 此时**必须**给出降级说明 +
  一个「去看博主情报」按钮（`data-v86-act="goto-blog"`，调 `switchTab("blog")`）
- 标题是纯文本，用 esc()；**没有 url 字段，不要编造链接**

7. `GET /api/stock_factors`
```
{ok, available, items:[{code,name,pe_pct,pb,momentum_20d_pct}]}
```
- 任一字段可能为 null → 显示 `[暂缺]`，**不要用 0 填充**
- `momentum_20d_pct` 已是百分数数值，用 fmtPctNum
- 展示：逐票 PE 历史分位 / PB / 20 日动量；注明分位来自
  `stock_valuation.json`、动量来自腾讯前复权日线

8. 大盘趋势结构面板 —— **零新增请求，直接复用 `state.market`**
```
state.market = {ok, available,
  index:{name,code,price,ma200,ma60,ma20,dev_pct,above,bars},
  state:"healthy"|"danger",
  breadth_state:"多头"|"空头",
  breadth_cross:"golden"|"death"|"hold",
  position_advice, reason, updated_at, source}
```
- 若 `state.market` 不存在或 `available:false`，回退 `apiGet("/api/market_state")`
- 展示 MA20 / MA60 / MA200 三个数值 + 现价 + 多空状态 +
  金叉/死叉/延续标记 + 仓位建议
- 必须注明：「趋势结构层，腾讯前复权日线；与盘中情绪指数不同源，
  不可并列比较或相加」
- 不要重复渲染今日页已有的「健康/危险」结论，这里只补**均线数值与交叉状态**

### 4.7 前端硬性规范（项目铁律，违反则 A 无法合并）
- CSS **禁止裸 hex**，所有颜色一律 `var(--token)`。可用令牌：
  `--up`(涨红) `--down`(跌绿) `--flat` `--muted` `--text` `--text-2`
  `--info-bg` `--card` `--border` `--primary` `--warn` `--warn-text`
  `--warn-bg` `--dot` `--surface` `--danger-bg` `--amber`
- **涨红跌绿**是 A 股惯例，`--up`/`--down` 永不覆写；用 `cls()` 上色
- 字号只用 `--fs-sm / --fs-md / --fs-lg / --fs-2xl`，**禁裸 px 字号、禁 !important**
- 可复用类：`.panel .empty .sub-line .hint .chip .alloc-btn .alloc-tbl
  .tbl-wrap .tbl-sticky .rec-warn .count .row-between .up .down .flat .muted .num`
  **不存在** `.ok-chip / .warn-chip / .cool-chip`，不要用
- 所有服务端文本用 `esc()`；空态用 `<div class="empty">…</div>`
- **不得**输出 `<script>` / `<style>` 标签（构建契约 script=4 / style=3）
- **不得**新增 `view-*`、导航项、页签（20 个视图固定）
- **不得**修改 `state` 结构、不得覆盖桌面既有 DOM、不得改其它模块函数
- 文件必须是**纯 JS 内容**（不含 html/head/body 包裹），A 会把它作为一个
  `<script>` 片段拼进单文件 PWA

### 4.8 降级总原则
每个面板都要能独立处理：`available:false` / 请求异常 / 空数组 / 字段为 null。
一律「明确说明原因 + 恢复路径 + 保留上一版」，**绝不编数、绝不用 0 或旧值填充**。

## 五、你怎么上传（重要）

`handoff/` 目录需要你创建。请**不要**用仓库里的 `sync_ai_archive.py`
（它跳过子目录）。用下面任一方式：

方式 A — GitHub Contents API（推荐，需 PAT，`Contents: read and write`）：
```
PUT https://api.github.com/repos/rgck1/ai-archive/contents/handoff/v86_panels.js
Authorization: Bearer <PAT>
Content-Type: application/json

{"message":"v86: B panels","branch":"main","content":"<文件内容的 base64>"}
```
- 若文件已存在，先 GET 该路径拿 `sha`，请求体里带上 `"sha":"..."` 才能覆盖
- 三个文件分别 PUT：`v86_panels.js`、`v86_summary.md`、`STATUS.md`
- 也可先 PUT 一个 `handoff/README.md` 把交换协议写进去（可选）

方式 B — git：
```
git clone https://github.com/rgck1/ai-archive.git
mkdir -p handoff && 写入三个文件
git add handoff/ && git commit -m "v86: B deliverables" && git push origin main
```

**PAT 需要用户给你**。如果没有写权限，就先把三个文件写到本地并明确告诉用户
「需要 Contents 读写权限的 PAT 才能上传」，不要假装已上传。

## 六、B-T2 总结文档要求（面向用户，中文）

写 `handoff/v86_summary.md`，包含且只包含三部分：
1. **已实现清单**：按「保留借鉴 / 可合并复用 / 明确不做」三类列出，
   每条注明落在哪个已有视图（不新增导航）；区分「后端已上线」与「前端待 A 集成」
2. **数据降级说明**：智谱 LLM 未启用、资讯源云 IP 限流、Top3 稳定性样本不足、
   行业快照日期与口径、黑名单/VaR 的估算口径与局限
3. **需要用户拍板的决策项**：列出选项与影响，**不替用户决定**。至少覆盖：
   - 是否启用智谱 LLM（密钥放哪、每日缓存是否可接受）
   - 资讯源是否换源 / 加代理 / 干脆下线该面板
   - 「行业温度」保留独立面板还是并入收盘复盘热力网格
   - Top3 稳定性累积周期是否维持每月
   - 范式边界确认：打板 / 2:30 入场 / 预判买卖价 / 模拟盘 / 成长体系 / 留言板
     等个股短线范式**不做**（与用户「跟组合 + 回测」路线冲突）
   - 未单独接线的 `/api/*` 接口是否保留

写作要求：只写可明确识别的事实，不臆测、不新增用户没提过的维度；
明确区分「已实现」与「待确认」；不喊单、不写成投资建议。

## 七、完成后

在 `STATUS.md` 里写：完成时间、三个文件是否都已上传成功（或卡在哪一步）、
你的自检结果（是否遵守 4.7 全部铁律、8 个面板是否都有降级分支）、
以及任何需要 A 或用户答复的问题。

A 会通过公开 raw 链接读取你的产出，先本地合并跑全套契约测试，通过后才部署。
如 A 有问题，会由用户转达或写进仓库 `handoff/`（届时 A 会有写权限）。

===== 复制结束 =====
