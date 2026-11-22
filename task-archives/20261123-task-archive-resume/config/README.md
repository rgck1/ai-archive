# 非敏感配置约定

本文件只记录可安全公开的约定，不含任何凭据值。

## 仓库与同步

| 项目 | 值 |
| --- | --- |
| GitHub 仓库 | `https://github.com/rgck1/ai-archive`，public，分支 main |
| 本机同步脚本 | `D:/我的工作台/工作台联动/sync_ai_archive_auto.py` |
| 同步命令 | `python "D:/我的工作台/工作台联动/sync_ai_archive_auto.py"` |
| 校验通过标志 | 输出中出现 `ALL_MATCH = True` |
| 凭据位置 | 原机器 `D:/我的工作台/.github_cred.json`，不归档 |

## 目录约定

| 用途 | 原机器路径 |
| --- | --- |
| 默认输出区 | `D:/我的工作台/02.输出区` |
| 归档源目录 | `D:/我的工作台/02.输出区/ai-archive/task-archives` |
| 技能目录 | `C:/Users/RG/.workbuddy/skills` |

新机器路径不同属正常现象，恢复时按清单相对路径落盘即可。

## 命令清单

| 命令 | 作用 |
| --- | --- |
| `/task-archive` | 归档当前任务到资料库与 GitHub，并生成恢复命令 |
| `/task-resume <任务ID>` | 从 GitHub 拉取归档包、校验、重建待办并续接 |

若新机器的 WorkBuddy 尚未识别这两条命令，可把 `files/skills/` 下的目录复制到该机器的技能目录后重新载入。

## 凭据策略

1. 公开仓库只读无需令牌。
2. 新机器要继续推送时，由用户重新提供具备 Contents 读写权限的令牌。
3. 令牌不写入任何归档文件、资料库产物或聊天回复。
