# 任务恢复卡：20261123-task-archive-resume

生成时间：2026-11-23T00:25:00+08:00

## 一键恢复命令（复制整段发给新智能体）

```text
请从公开仓库 https://github.com/rgck1/ai-archive 恢复任务 20261123-task-archive-resume，并接着上次进度继续：

1. 先读以下公开 raw 链接对齐我的协作偏好：
   https://raw.githubusercontent.com/rgck1/ai-archive/main/README.md
   https://raw.githubusercontent.com/rgck1/ai-archive/main/about-me.md
   https://raw.githubusercontent.com/rgck1/ai-archive/main/writing-style.md
   https://raw.githubusercontent.com/rgck1/ai-archive/main/rules.md
   https://raw.githubusercontent.com/rgck1/ai-archive/main/projects.md

2. 再读归档清单：
   https://raw.githubusercontent.com/rgck1/ai-archive/main/task-archives/20261123-task-archive-resume/MANIFEST.json

3. 按清单中每个 path 逐个读取下面地址，并写到本机工作区，保持相对路径不变：
   https://raw.githubusercontent.com/rgck1/ai-archive/main/task-archives/20261123-task-archive-resume/<文件路径>

   若你能运行 Python，可先取回校验脚本：
   https://raw.githubusercontent.com/rgck1/ai-archive/main/task-archives/20261123-task-archive-resume/files/skills/task-resume/scripts/fetch_task.py
   保存到本机后执行：
   python "<脚本本机路径>" "https://raw.githubusercontent.com/rgck1/ai-archive/main/task-archives/20261123-task-archive-resume" "<本机目标目录>"
   看到 ALL_MATCH = True 才表示完整拉取。

4. 依次读 CONTEXT.md、STATUS.md、TASKS.md、DESIGN.md，按 TASKS.md 重建待办及状态。

5. 从 STATUS.md 的「下一步」开始执行。不要重做已完成事项，不要臆测未记录的信息。

6. 若你能访问我的 WorkBuddy 资料库，搜索「任务归档 20261123-task-archive-resume」取恢复卡作交叉校验；GitHub 为权威源。

全程中文沟通。你完成新进度后，按同样格式重新归档，供下一位智能体接续。
```

## 必须保存与恢复的关键内容

| 类别 | 归档位置 | 恢复动作 |
| --- | --- | --- |
| 项目文件 | `files/` | 按清单原样落盘，保持相对路径 |
| 配置约定 | `config/README.md` | 读取路径、仓库、同步脚本约定；凭据一律重新提供 |
| 上下文记录 | `CONTEXT.md` | 完整读入，作为任务目标与红线依据 |
| 进度状态 | `STATUS.md` | 认领完成、进行中、阻塞，从下一步继续 |
| 待办事项 | `TASKS.md` | 用待办工具逐条重建 ID 与状态 |
| 资料索引 | `materials/README.md` | 按标题与链接重新取用，不依赖本机原路径 |
| 校验清单 | `MANIFEST.json` | 逐文件 sha256 校验，全部一致才继续 |
| 恢复命令 | `RECOVER.md` | 原样可用，不依赖预装技能 |
