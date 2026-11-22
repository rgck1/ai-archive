# 上下文记录：20261123-task-archive-resume

生成时间：2026-11-23T00:20:00+08:00

## 1. 任务目标

在 WorkBuddy 中实现可复用的任务归档命令，把当前任务的项目文件、配置、上下文记录、进度状态、待办事项和资料完整归档到资料库并同步到 GitHub；随后给出一条可直接复制执行的恢复/继续命令，让免费额度耗尽后在另一台电脑上的另一个智能体能够从资料库和 GitHub 拉取完整内容并接着当前进度继续。完成判定：两个命令均通过结构校验、归档包完成 GitHub 逐文件校验、资料库有可读恢复卡、恢复命令无需预装技能即可使用。

## 2. 用户明确提出的要求（可明确识别）

| 要求 | 用户原话要点 |
| --- | --- |
| 归档范围 | 项目文件、配置、上下文记录、进度状态、待办事项和资料 |
| 归档目标 | 完整归档到资料库，并同步到 GitHub |
| 恢复场景 | 免费额度用完、另一台电脑、另一个智能体 |
| 恢复动作 | 从资料库和 GitHub 拉取完整内容，接着当前进度继续 |
| 命令质量 | 清晰、可复用、明确必须保存和恢复的关键内容 |
| 沟通方式 | 全程中文；先给结论再给理由；命令给完整可复制版本 |
| 实现原则 | 有成熟开源方案就复用；从第一性原理出发；做一轮对抗式审查 |

## 3. 助手实现选择（非用户拍板，可回退）

| 选择 | 理由 | 回退方式 |
| --- | --- | --- |
| 用两条 Skill 实现斜杠命令 | WorkBuddy 中命令的标准形态就是 Skill | 可直接删掉技能目录 |
| GitHub 为权威源、资料库为镜像 | 公开 raw 链接跨机器可达，资料库依赖同一账号 | 恢复时以资料库为主亦可 |
| MANIFEST.json 加 sha256 校验 | 恢复方能确认没有拉漏或拉坏 | 可改为逐个文件人工读取 |
| 任务 ID 用日期加英文短名 | 便于排序且避免中文路径编码问题 | 可改成任意唯一字符串 |

用户尚未就上述实现选择单独拍板，恢复方如需调整应先询问用户。

## 4. 约束与红线

1. 公开仓库禁止写入令牌、口令、Cookie、服务器地址、第三方账号密码。
2. 不臆测用户没提过的规则；区分「用户明确要求」与「助手实现选择」。
3. 不出现「不是……而是」句式，不使用破折号；中文沟通。
4. 同步与校验必须实际运行，禁止凭文件存在推断成功。
5. 恢复命令必须自包含，不假设新机器已安装本技能。

## 5. 用户协作偏好指针

恢复方先读以下五个文件对齐偏好：

- https://raw.githubusercontent.com/rgck1/ai-archive/main/README.md
- https://raw.githubusercontent.com/rgck1/ai-archive/main/about-me.md
- https://raw.githubusercontent.com/rgck1/ai-archive/main/writing-style.md
- https://raw.githubusercontent.com/rgck1/ai-archive/main/rules.md
- https://raw.githubusercontent.com/rgck1/ai-archive/main/projects.md

## 6. 关键文件位置（信息性，新机器路径会不同）

| 用途 | 原机器位置 | 归档内相对位置 |
| --- | --- | --- |
| 归档命令 | `C:/Users/RG/.workbuddy/skills/task-archive/` | `files/skills/task-archive/` |
| 恢复命令 | `C:/Users/RG/.workbuddy/skills/task-resume/` | `files/skills/task-resume/` |
| 归档源目录 | `D:/我的工作台/02.输出区/ai-archive/task-archives/` | 本目录 |
| GitHub 同步脚本 | `D:/我的工作台/工作台联动/sync_ai_archive_auto.py` | `config/README.md` 有说明 |
| GH 凭据文件 | `D:/我的工作台/.github_cred.json` | 不归档，仅记录需重新提供 |

## 7. 不宜带入新会话的内容

- 本机 GH 凭据文件内容与令牌值，一律不归档。
- 工具调用的原始响应与推理过程，不作为任务事实。
