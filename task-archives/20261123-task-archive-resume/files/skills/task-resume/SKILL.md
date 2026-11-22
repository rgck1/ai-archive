---
name: task-resume
description: 从 GitHub 公开仓库 ai-archive 的 task-archives 目录拉取指定任务的完整归档包，按 MANIFEST 逐文件校验后重建上下文与待办，并从上次进度继续执行。用户要求恢复任务、续接任务、换电脑继续、新智能体接手、免费额度用完后接着做时，应使用本技能。
agent_created: true
---

# 任务恢复

## 用途

在另一台电脑、另一个会话、另一个智能体中，从公开仓库还原任务现场。恢复过程不依赖原机器的会话状态，也不假设本机已安装任何技能。

## 输入

用户提供任务 ID，例如 `20261123-task-archive-resume`，或直接给出归档目录的 raw 链接。用户未给 ID 时，先列出 `https://github.com/rgck1/ai-archive` 仓库 `task-archives/` 下的目录让用户选择，不要自行挑一个。

## 固定地址

| 项目 | 值 |
| --- | --- |
| raw 基址 | `https://raw.githubusercontent.com/rgck1/ai-archive/main/task-archives/<任务ID>` |
| 偏好文件 | `https://raw.githubusercontent.com/rgck1/ai-archive/main/` 下的 README.md、about-me.md、writing-style.md、rules.md、projects.md |
| 校验脚本 | `<raw 基址>/files/skills/task-resume/scripts/fetch_task.py` |

## 流程

### 第 1 步：对齐用户偏好

先用 raw 链接依次读五个核心偏好文件，之后全程按其中的规则协作。

### 第 2 步：取回校验脚本

把尖括号占位替换为实际任务 ID 后执行：

```bash
python -c "import urllib.request;u='https://raw.githubusercontent.com/rgck1/ai-archive/main/task-archives/<任务ID>/files/skills/task-resume/scripts/fetch_task.py';open('fetch_task.py','wb').write(urllib.request.urlopen(u,timeout=60).read())"
```

### 第 3 步：拉取并校验全部文件

```bash
python "fetch_task.py" "https://raw.githubusercontent.com/rgck1/ai-archive/main/task-archives/<任务ID>" "<本机目标目录>"
```

必须看到 `ALL_MATCH = True`。出现 `MISMATCH` 时停止，不要基于残缺内容续接。若 raw 域名被网络策略拦截，在同一命令末尾追加 API 回退参数：`--repo rgck1/ai-archive --bundle "task-archives/<任务ID>" --branch main`。若本机没有 Python，改为按 MANIFEST.json 中的 path 列表逐个读取 raw 链接并落盘，保持相对路径不变。

### 第 4 步：重建任务现场

1. 读 `CONTEXT.md`，把任务目标、已定决策、约束红线视为既有事实。
2. 读 `STATUS.md`，认领已完成、进行中、阻塞三类事项。
3. 读 `TASKS.md`，用待办工具逐条重建任务 ID 与状态。
4. 读 `DESIGN.md`，了解上次做过哪些对抗式审查，避免重复踩坑。
5. 读 `materials/README.md`，按标题与链接重新取用资料，不依赖本机原路径。

### 第 5 步：交叉校验

若可访问 WorkBuddy 资料库，搜索「任务归档 <任务ID>」读取恢复卡，与 GitHub 版本比对。GitHub 为权威源，资料库版本用于人读与交叉核对。

### 第 6 步：从下一步继续

只执行 `STATUS.md` 中「下一步」列出的动作。不要重做已完成事项。遇到阻塞项先询问用户，不替用户拍板。

## 硬约束

1. 不得编造归档中没有的信息。缺什么就明确说缺什么。
2. 令牌、口令、Cookie 一律不从归档恢复，需要时请用户重新提供。
3. 全程中文沟通，先给结论再给理由。
4. 新进度完成后按同样格式重新归档，供下一位智能体接续。
