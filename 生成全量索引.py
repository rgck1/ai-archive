# -*- coding: utf-8 -*-
"""
生成 ai-archive 全量索引 MASTER_INDEX.md

用途：把仓库里散落的 90+ 个文件，整理成一份「按问题找文件」的入口地图。
特点：纯标准库、可反复运行、每次自动覆盖旧索引，不会重复堆积。

运行方式（复制下面整行到命令行回车）：
python "D:/我的工作台/02.输出区/ai-archive/生成全量索引.py"
"""

import os
import re
import glob
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "MASTER_INDEX.md")

# ---------- 场景导航：按「我现在要解决什么问题」找文件 ----------
# 规则：每条= (问题, [文件/通配路径列表])。路径相对仓库根目录。
# 新增场景直接往这个列表加一行即可。
SCENES = [
    ("换一台电脑或新开一个会话，让 AI 快速认识我",
     ["README.md", "about-me.md", "writing-style.md", "rules.md", "projects.md", "接入指南.md"]),
    ("把档案仓库推送到 GitHub 或重新同步",
     ["发布说明.md"]),
    ("查某位博主的战法定义、原始口播和回测结论",
     ["invest-workbench/全博主战法_清单与定义.*",
      "invest-workbench/全博主战法大摸底与回测_2026-11-16.html",
      "invest-workbench/花臂博士5张图_*",
      "invest-workbench/凯心N字战法_*",
      "invest-workbench/博主战法补充研究_*"]),
    ("把订阅博主笔记接入第二大脑、评估素材价值",
     ["invest-workbench/财经投资45位_第二大脑对接评估_*",
      "invest-workbench/财经45位对接P0落地交付_*",
      "invest-workbench/订阅博主分类与笔记素材价值评估_*",
      "invest-workbench/订阅博主笔记熔断补拉说明_*",
      "invest-workbench/得到大脑*",
      "invest-workbench/得到关注*"]),
    ("查情报源、企微推送规则、组合与策略跟踪",
     ["invest-workbench/情报源*",
      "invest-workbench/信息雷达企微推送_*",
      "invest-workbench/近一周领涨组合_*"]),
    ("查工作台改动历史、性能评测、架构对标",
     ["invest-workbench/投资工作台改动总表_*",
      "invest-workbench/投资工作台架构性能评测_*",
      "invest-workbench/工作台性能优化实施交付_*"]),
    ("恢复一个中断的任务",
     ["task-archives/*/RECOVER.md", "task-archives/*/CONTEXT.md"]),
    ("做 A/B 双智能体交接、找给 B 的指令",
     ["handoff/README.md", "handoff/给B的指令*", "handoff/v86_*"]),
    ("重跑某个脚本或核验（回测、净值、推送、抽帧）",
     ["invest-workbench/*.py"]),
    ("看博主战法视频的抽帧画面索引",
     ["invest-workbench/战法视频抽帧/索引.html",
      "invest-workbench/战法视频抽帧/全量抽帧解析索引.html"]),
]


def title_of(path):
    """从文件里提取一行标题，失败则用文件名。"""
    name = os.path.basename(path)
    ext = os.path.splitext(name)[1].lower()
    try:
        if ext in (".md", ".py"):
            with open(path, encoding="utf-8") as f:
                lines = f.readlines()
            if ext == ".md":
                for s in lines:
                    s = s.strip()
                    if s.startswith("# "):
                        return s[2:].strip()[:70]
            else:
                for s in lines[:6]:
                    s = s.strip()
                    if s.startswith("#"):
                        t = s.lstrip("#*- ").strip()
                        if t and not t.startswith("coding"):
                            return t[:70]
                for i, s in enumerate(lines[:6]):
                    if s.strip().startswith('"""'):
                        for nxt in lines[i + 1:i + 6]:
                            nxt = nxt.strip()
                            if nxt and not nxt.startswith('"""'):
                                return nxt[:70]
                        break
        if ext in (".html", ".htm"):
            with open(path, encoding="utf-8") as f:
                head = f.read(8000)
            m = re.search(r"<title>(.*?)</title>", head, re.I | re.S)
            if m:
                return re.sub(r"\s+", " ", m.group(1)).strip()[:70]
    except Exception:
        pass
    return name


def size_of(path):
    n = os.path.getsize(path)
    return "%.0f KB" % (n / 1024) if n >= 1024 else "%d B" % n


def expand(patterns):
    """把通配路径展开成实际存在的相对文件列表（去重、保序）。"""
    seen, out = set(), []
    for pat in patterns:
        full = os.path.join(BASE, pat.replace("/", os.sep))
        for p in glob.glob(full):
            if not os.path.isfile(p):
                continue
            rel = os.path.relpath(p, BASE).replace(os.sep, "/")
            if rel in seen:
                continue
            seen.add(rel)
            out.append(rel)
    return out


def all_files():
    out = []
    for root, dirs, files in os.walk(BASE):
        dirs.sort()
        for fn in sorted(files):
            if fn == "MASTER_INDEX.md":
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, BASE).replace(os.sep, "/")
            out.append(rel)
    return out


def group_manifest(files):
    """按目录+类型分组，生成全量清单。"""
    groups = {}
    for rel in files:
        top = rel.split("/")[0]
        ext = os.path.splitext(rel)[1].lower()
        if "/" not in rel:
            g = "根目录 · 协作核心档案"
        elif top == "handoff":
            g = "handoff/ · 双智能体交接协议"
        elif top == "task-archives":
            g = "task-archives/ · 任务归档与恢复"
        elif top == "invest-workbench":
            sub = rel.split("/")[1] if len(rel.split("/")) > 1 else ""
            if sub == "战法视频抽帧":
                g = "invest-workbench/战法视频抽帧/ · 视频抽帧素材"
            elif ext == ".py":
                g = "invest-workbench/ · 脚本工具"
            elif ext == ".json":
                g = "invest-workbench/ · 数据与回测结果"
            else:
                g = "invest-workbench/ · 报告与交付"
        else:
            g = "其他"
        groups.setdefault(g, []).append(rel)

    order = ["根目录 · 协作核心档案",
             "invest-workbench/ · 报告与交付",
             "invest-workbench/ · 脚本工具",
             "invest-workbench/ · 数据与回测结果",
             "invest-workbench/战法视频抽帧/ · 视频抽帧素材",
             "handoff/ · 双智能体交接协议",
             "task-archives/ · 任务归档与恢复",
             "其他"]
    lines = []
    for g in order + sorted(k for k in groups if k not in order):
        if g not in groups:
            continue
        rels = groups[g]
        lines.append("### %s（%d 个）" % (g, len(rels)))
        lines.append("")
        lines.append("| 文件 | 一句话说明 | 大小 |")
        lines.append("| --- | --- | --- |")
        for rel in rels:
            t = title_of(os.path.join(BASE, rel.replace("/", os.sep))).replace("|", "/")
            lines.append("| `%s` | %s | %s |" % (rel, t, size_of(os.path.join(BASE, rel.replace("/", os.sep)))))
        lines.append("")
    return "\n".join(lines)


def main():
    files = all_files()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    doc = []
    doc.append("# MASTER_INDEX · ai-archive 全量索引")
    doc.append("")
    doc.append("> 这是本仓库的唯一入口地图。换 AI、换电脑、开新会话时，先读本文件，再按下面的场景跳到具体文件。")
    doc.append("> 本文件由 `生成全量索引.py` 自动生成，新增或删除文件后重跑一次脚本即可，不要手工编辑本文件。")
    doc.append("")
    doc.append("**生成时间：** %s　　**收录文件：** %d 个" % (now, len(files)))
    doc.append("")
    doc.append("## 一、我现在要解决什么问题？（场景导航）")
    doc.append("")
    doc.append("| 问题 | 去看这些文件 |")
    doc.append("| --- | --- |")
    for q, pats in SCENES:
        rels = expand(pats)
        cell = "、".join("`%s`" % r for r in rels[:8]) if rels else "（暂无匹配文件）"
        doc.append("| %s | %s |" % (q, cell))
    doc.append("")
    doc.append("> 场景导航是人工维护的语义层。遇到新场景，在 `生成全量索引.py` 顶部的 `SCENES` 列表加一行再重跑。")
    doc.append("")
    doc.append("## 二、新会话必读（5 件套）")
    doc.append("")
    doc.append("按顺序读：`about-me.md` → `writing-style.md` → `rules.md` → `projects.md` → `MASTER_INDEX.md`（本文件）。")
    doc.append("读完用一句话说明已对齐协作偏好，再执行任务。")
    doc.append("")
    doc.append("## 三、维护约定（让库越用越准）")
    doc.append("")
    doc.append("1. **新增文件重跑索引**：把整行命令贴到命令行运行，本文件自动刷新，无需手工改。")
    doc.append("   ```")
    doc.append("   python \"D:/我的工作台/02.输出区/ai-archive/生成全量索引.py\"")
    doc.append("   ```")
    doc.append("2. **产出回流**：每次任务产出结论后，把一句话结论追加到 `projects.md` 对应项目下，并补日期。")
    doc.append("3. **只记可识别规则**：不臆测、不新增用户没提过的维度。")
    doc.append("4. **敏感信息脱敏**：健康、路径等精确细节不写进公开可见内容。")
    doc.append("")
    doc.append("## 四、全量文件清单")
    doc.append("")
    doc.append(group_manifest(files))

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(doc) + "\n")

    print("OK 已生成：%s" % OUT)
    print("收录文件：%d 个，场景导航：%d 条" % (len(files), len(SCENES)))


if __name__ == "__main__":
    main()
