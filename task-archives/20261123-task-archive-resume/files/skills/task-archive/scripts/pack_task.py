"""为任务归档包生成 MANIFEST.json（仅标准库，UTF-8，中文路径安全）。

用法（完整可复制）：
  python "C:/Users/RG/.workbuddy/skills/task-archive/scripts/pack_task.py" "归档包目录" --task-id "任务ID" --title "任务标题" --workspace "工作区路径"

行为：
  - 遍历归档包目录，逐文件计算 sha256 与字节数
  - 保留已有 MANIFEST.json 中的任务元信息（若再次运行）
  - 输出 ALL_MATCH_READY=True 表示清单已写好，可推送 GitHub
"""
import os
import sys
import json
import hashlib
import argparse
from datetime import datetime, timezone, timedelta

SCHEMA = "workbuddy-task-archive/1"
SKIP_NAMES = {"MANIFEST.json", "Thumbs.db", ".DS_Store"}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle_dir")
    ap.add_argument("--task-id", default="")
    ap.add_argument("--title", default="")
    ap.add_argument("--workspace", default="")
    ap.add_argument("--repo", default="rgck1/ai-archive")
    ap.add_argument("--branch", default="main")
    args = ap.parse_args()

    root = os.path.abspath(args.bundle_dir)
    if not os.path.isdir(root):
        sys.exit("ERROR: 归档包目录不存在: " + root)

    old = {}
    manifest_path = os.path.join(root, "MANIFEST.json")
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, encoding="utf-8") as f:
                old = json.load(f)
        except Exception:
            old = {}

    files = []
    for cur, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(names):
            if name in SKIP_NAMES or name.startswith("."):
                continue
            full = os.path.join(cur, name)
            rel = os.path.relpath(full, root).replace("\\", "/")
            files.append({
                "path": rel,
                "sha256": sha256_file(full),
                "bytes": os.path.getsize(full),
            })

    now = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    task_id = args.task_id or old.get("task_id") or os.path.basename(root)
    bundle_rel = "task-archives/" + task_id
    raw_base = "https://raw.githubusercontent.com/%s/%s/%s" % (
        args.repo, args.branch, bundle_rel)

    manifest = {
        "schema": SCHEMA,
        "task_id": task_id,
        "title": args.title or old.get("title") or task_id,
        "created_at": old.get("created_at") or now,
        "updated_at": now,
        "source_workspace": args.workspace or old.get("source_workspace", ""),
        "github_repo": args.repo,
        "github_branch": args.branch,
        "bundle_path": bundle_rel,
        "raw_base": raw_base,
        "file_count": len(files),
        "total_bytes": sum(f["bytes"] for f in files),
        "files": files,
    }

    with open(manifest_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("任务ID:", task_id)
    print("文件数:", len(files), "总字节:", manifest["total_bytes"])
    print("raw 基址:", raw_base)
    print("ALL_MATCH_READY = True")


if __name__ == "__main__":
    main()
