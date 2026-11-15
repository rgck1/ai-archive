# handoff/ — A / B 仓库交换协议（v86）

建立时间：2026-11-15
GitHub 仓库：https://github.com/rgck1/ai-archive （public，分支 `main`）

## 2026-11-15 01:20 更新：今晚改走资料库，GitHub 明天再弄

用户拍板：GitHub 今晚不方便就先上传资料库。已落地：

| 资料库文件 | node_id | 链接 |
|---|---|---|
| `v86_B任务包_资料库版.md` | `0UCIsN6jBL0RKxQYJe5ElQ` | https://www.workbuddy.cn/space/d/0UCIsN6jBL0RKxQYJe5ElQ |
| `v86_AB交换协议_资料库版.md` | `sdpMxoEbV9GgiPC70lEWSp` | https://www.workbuddy.cn/space/d/sdpMxoEbV9GgiPC70lEWSp |

- **B 只需读第一份**（`v86_B任务包_资料库版.md`），自包含全部技术契约，不依赖仓库里
  任何待建文件；第二份是交换协议背景，可选。
- **B 交付**：`v86_B_panels.js` / `v86_B_summary.md` / `v86_B_STATUS.md`，
  自己上传回资料库，文件名统一带 `v86_B_` 前缀，A 从资料库读回。
- **GitHub 明天补**：需要 PAT（Contents 读写）。A 今晚不写 GitHub。
- 本地 `v86_B_instructions.md` 与 `给B的指令_可复制.txt` 是 GitHub 版存档，
  内容已被资料库版覆盖，仅留作历史。

以下为原 GitHub 交换协议（明天恢复时用）：

## 为什么要这个目录

用户 2026-11-15 指示：A 的免费额度吃紧，把可独立交付的部分分给 B；B 做完自行上传；
A 与 B 在仓库里交换信息，不再靠会话转述。

## 读写能力（如实记录，勿假设）

| 角色 | 读 | 写 |
|---|---|---|
| A | 公开 raw 链接 / GitHub 公开 API | **当前不可用**：本机 `GH_TOKEN` 为空，且 `D:/我的工作台/02.输出区/ai-archive` 不是 git 仓库 |
| B | 公开 raw 链接 | 需自备 GitHub 凭据（PAT 或已登录的 git），用户侧提供 |

因此当前可行的交换是 **B 上传 → A 公开读**；A→B 的信息一次性写进「给 B 的指令」。
若后续需要 A 也往仓库写，需用户提供一次性 PAT（用完吊销）或代贴 A 的段落。

## 固定路径与命名

- 所有交换文件放 `handoff/`，文件名小写英文，UTF-8 / LF。
- 公开读法：`https://raw.githubusercontent.com/rgck1/ai-archive/main/handoff/<文件名>`
- 目录清单（GitHub Contents API，无需 token）：
  `https://api.github.com/repos/rgck1/ai-archive/contents/handoff`

| 文件 | 谁写 | 内容 |
|---|---|---|
| `v86_panels.js` | B | 8 个面板的渲染 + 加载代码（B-T1 产出） |
| `v86_summary.md` | B | 交付总结与待确认事项初稿（B-T2 产出） |
| `STATUS.md` | B | B 的进度、已完成项、遗留问题 |
| `v86_B_instructions.md` | B | **B 把收到的指令原文存一份**，使仓库自带完整任务说明与契约，A 可公开读回核对 |

> 2026-11-15 核实：A 侧无 `GH_TOKEN`、无 git credential helper、无凭据文件，
> 且本地目录不是 git 仓库 → **A 确实无法上传**。因此 `handoff/` 由 B 首次创建，
> A→B 的全部技术输入一次性写进「给 B 的指令」正文，不依赖仓库里任何待建文件。

## 红线

- 仓库是**公开**的：禁止写入任何密钥、口令、Cookie、token、服务器内网地址、
  第三方网页账号密码、`.session_secret` 内容。
- B **不得**修改仓库根目录 5 个画像文件（README/about-me/writing-style/rules/projects），
  **不得**动 `invest-workbench/`，**不得**改 `handoff/v86_contract.md`。
- B 只写 `handoff/` 下自己的 3 个文件；发现冲突以本文件为准。
- A 不假设 B 能访问本机 `D:/我的工作台/...` 路径或 TAT/服务器凭据。

## 任务分工（2026-11-15）

### B（独立交付，上传仓库）
- **B-T1**：产出 `handoff/v86_panels.js` —— 8 个面板的完整加载 / 渲染 / 降级代码，
  按契约调用已上线的 v86 接口，导出 3 个全局入口函数。
- **B-T2**：产出 `handoff/v86_summary.md` —— 面向用户的交付总结与待拍板事项初稿。

### A（本机 + 服务器，强耦合，不外分）
- 3 个 view 的面板 HTML 骨架插入、新建 `30-script/21-v86.html` 并注册 manifest、
  `switchTab` 派发、state / bind 接入。
- 构建 `build_frontend.py --verify` + `test_frontend_build.py`（29 项）+
  内联 JS `node --check`。
- `sw.js` bump 到 v87；部署 `index.html` + `sw.js`；线上 HTTP / TAT 核验。
- 合并 B 的 JS、最终回归、在 B 初稿基础上出最终交付总结。
- 后端 `api_market_state` 已增强；`api_sector_temperature` 保留但前端主路径改为
  复用已加载的 `_srData`，不重复请求（见契约）。

## 验收

- A 用公开 raw 链接读到 B 的 3 个文件后，先在**本地**合并并跑全套契约测试，
  不通过则不部署，并把具体问题写进给用户的反馈里。
- B 的 JS 不得引入 `<script>` / `<style>` 标签、不得新增 view-* 或导航项。
