---
name: task-archive
description: 将当前 WorkBuddy 任务的项目文件、脱敏配置、上下文记录、进度状态、待办事项和资料完整打包，上传到 WorkBuddy 资料库并同步到 GitHub 公开仓库 ai-archive，最后生成一条可复制的跨机器恢复命令。用户要求归档任务、跨电脑交接、备份进度、免费额度用完前留底、把当前进度存档时，应使用本技能。
agent_created: true
---

# 任务归档

## 用途

把只存在于会话中的任务状态物化为可移植归档包。归档包同时落在三个位置：本机源目录、WorkBuddy 资料库、GitHub 公开仓库。GitHub 是权威源，任何机器凭公开 raw 链接可读；资料库是镜像与可读副本。

## 固定路径（不要改）

| 项目 | 值 |
| --- | --- |
| 技能目录 | `C:/Users/RG/.workbuddy/skills/` |
| 归档源目录 | `D:/我的工作台/02.输出区/ai-archive/task-archives/` |
| GitHub 仓库 | `https://github.com/rgck1/ai-archive`（public，分支 main） |
| raw 基址 | `https://raw.githubusercontent.com/rgck1/ai-archive/main/` |
| 同步脚本 | `D:/我的工作台/工作台联动/sync_ai_archive_auto.py` |
| 清单生成脚本 | `C:/Users/RG/.workbuddy/skills/task-archive/scripts/pack_task.py` |
| 凭据文件 | `D:/我的工作台/.github_cred.json`（绝不进入归档包、资料库产物或回复） |

## 归档包结构

```
task-archives/<任务ID>/
  MANIFEST.json          机器可读清单：路径 + sha256 + 字节数 + raw 基址
  CONTEXT.md             任务目标、已定决策、约束红线、用户偏好指针
  STATUS.md              完成、进行中、阻塞、下一步（下一步必须可执行）
  TASKS.md               待办逐条快照：ID、状态、内容、依赖
  RECOVER.md             恢复命令与步骤（复制粘贴即可用）
  DESIGN.md              第一性原理分析与对抗式审查记录
  SKIPPED.md             因体积或脱敏被跳过的文件及原因
  config/README.md       非敏感配置约定，禁止复制任何凭据
  materials/README.md    资料索引：文档标题与链接，不写密钥
  files/                 项目文件、交付物、技能副本，保留相对路径
```

## 流程

### 第 1 步：确定任务 ID 与目标目录

ID 规则为 `YYYYMMDD-英文短名`，例如 `20261123-task-archive-resume`。目标目录为归档源目录下以该 ID 命名的子目录。目录已存在时走增量更新，不另建重复目录。

### 第 2 步：写四份核心文档

按 `assets/` 下的模板写出 `CONTEXT.md`、`STATUS.md`、`TASKS.md`、`RECOVER.md`。要点：

1. `CONTEXT.md` 必须写清任务目标、用户已明确拍板的决策、不可逾越的红线、关键文件位置，并指向 `https://github.com/rgck1/ai-archive` 的五个核心偏好文件（README、about-me、writing-style、rules、projects）。
2. `STATUS.md` 的「下一步」必须是可直接执行的动作，不能写「继续处理」这类空话。
3. `TASKS.md` 逐条保留任务 ID 与状态，恢复方据此重建待办。
4. `RECOVER.md` 使用模板原样填充任务 ID，不要改写其中的 raw 链接结构。

### 第 3 步：收集文件

1. 项目文件按原相对路径复制到 `files/`。
2. 跳过 `.git`、`node_modules`、`__pycache__`、`.venv`、`dist`、`build`，跳过大于 5 MB 的二进制文件，跳过的条目写入 `SKIPPED.md`。
3. 禁止复制 `.github_cred.json`、`.env`、`*.token`、`*.key`、含 token 或密码的 mcp 配置。`config/README.md` 只写非敏感约定。
4. 把本技能目录 `C:/Users/RG/.workbuddy/skills/task-archive/` 与 `task-resume/` 整份复制到 `files/skills/` 下，让归档包自带可安装的命令。
5. 写 `DESIGN.md`，记录本次任务的第一性原理判断与对抗式审查结论，包括发现的风险与对应缓解措施。

### 第 4 步：生成清单

执行以下完整命令，把尖括号占位替换为实际值：

```bash
python "C:/Users/RG/.workbuddy/skills/task-archive/scripts/pack_task.py" "D:/我的工作台/02.输出区/ai-archive/task-archives/<任务ID>" --task-id "<任务ID>" --title "<任务标题>" --workspace "<工作区绝对路径>"
```

输出出现 `ALL_MATCH_READY = True` 才继续。

### 第 5 步：同步 GitHub

```bash
python "D:/我的工作台/工作台联动/sync_ai_archive_auto.py"
```

必须看到 `ALL_MATCH = True`。出现 `MISMATCH` 或推送失败时停止并如实报告，不得声称已同步。

### 第 6 步：上传资料库

用资料库上传能力上传两个文件：

1. 恢复卡 `D:/我的工作台/02.输出区/恢复卡_<任务ID>.md`，面向人阅读，不含本地路径与密钥。
2. 完整归档包 `D:/我的工作台/02.输出区/归档包_<任务ID>.zip`，由归档目录压缩而成。

上传成功后在回复中写明落点链接。

### 第 7 步：输出恢复命令

把 `RECOVER.md` 中的「一键恢复命令」原样贴给用户，并说明必须保存与恢复的关键内容清单。不得只给概念说明而不给可复制命令。

## 硬约束

1. 公开仓库禁止写入令牌、口令、Cookie、服务器地址、第三方账号密码。
2. 清单生成与 GitHub 校验都必须实际运行，禁止凭文件存在推断成功。
3. 恢复命令必须自包含，不能假设新机器已安装本技能。
4. 全程使用中文回复。
