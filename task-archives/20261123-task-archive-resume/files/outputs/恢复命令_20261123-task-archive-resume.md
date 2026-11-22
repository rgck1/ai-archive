# 任务归档与跨机器恢复命令

归档任务 ID：`20261123-task-archive-resume`

## 结论

已新增两条 WorkBuddy 命令并完成当前任务的完整归档。`/task-archive` 负责把任务现场打包到资料库与 GitHub，`/task-resume` 负责在新机器上还原并续接。GitHub 公开仓库是权威源，资料库是可读镜像。免费额度用完后，把下面整段命令复制给另一台电脑上的新智能体即可接着做。

## 一键恢复命令（复制整段）

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

## 可直接复制运行的完整命令（取回校验脚本并拉取）

第 1 条，取回脚本，把目标目录换成你本机想放脚本的位置：

```bash
python -c "import urllib.request;u='https://raw.githubusercontent.com/rgck1/ai-archive/main/task-archives/20261123-task-archive-resume/files/skills/task-resume/scripts/fetch_task.py';open('fetch_task.py','wb').write(urllib.request.urlopen(u,timeout=60).read())"
```

第 2 条，拉取并校验全部归档文件：

```bash
python "fetch_task.py" "https://raw.githubusercontent.com/rgck1/ai-archive/main/task-archives/20261123-task-archive-resume" "D:/恢复的任务归档/20261123-task-archive-resume"
```

两条命令的输出都要看到 `ALL_MATCH = True`。出现 `MISMATCH` 就停止，不要基于残缺内容续接。

## 必须保存与恢复的关键内容

| 类别 | 归档位置 | 恢复动作 |
| --- | --- | --- |
| 项目文件 | `files/` | 按清单原样落盘，保持相对路径 |
| 配置约定 | `config/README.md` | 读取路径、仓库、同步脚本约定；凭据重新提供 |
| 上下文记录 | `CONTEXT.md` | 完整读入，作为任务目标与红线依据 |
| 进度状态 | `STATUS.md` | 认领完成、进行中、阻塞，从下一步继续 |
| 待办事项 | `TASKS.md` | 用待办工具逐条重建 ID 与状态 |
| 资料索引 | `materials/README.md` | 按标题与链接重新取用，不依赖本机原路径 |
| 校验清单 | `MANIFEST.json` | 逐文件 sha256 校验，全部一致才继续 |
| 恢复命令 | `RECOVER.md` | 原样可用，不依赖预装技能 |

## 新命令的用法

| 命令 | 作用 |
| --- | --- |
| `/task-archive` | 归档当前任务到资料库与 GitHub，并生成恢复命令 |
| `/task-resume <任务ID>` | 从 GitHub 拉取归档包、校验、重建待办并续接 |

新机器若尚未识别这两条命令，把归档包内 `files/skills/` 下的 `task-archive`、`task-resume` 两个目录复制到该机器技能目录后重新载入即可。

## 安全边界

公开仓库禁止写入令牌、口令、Cookie、服务器地址与第三方账号密码。归档包内不含任何凭据。新机器要继续推送时，由用户重新提供具备 Contents 读写权限的令牌。
