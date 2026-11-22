"""从 GitHub 公开仓库拉取任务归档包并按 MANIFEST 逐文件校验（仅标准库）。

用法（完整可复制）：
  python "fetch_task.py" "https://raw.githubusercontent.com/rgck1/ai-archive/main/task-archives/任务ID" "本机目标目录"

可选参数（raw 域名被网络策略拦截时启用 API 回退）：
  --repo rgck1/ai-archive --bundle "task-archives/任务ID" --branch main

行为：
  - 先下载 raw_base/MANIFEST.json，再按清单逐个下载文件
  - raw 失败时自动回退到 GitHub Contents API（公开读，无需令牌）
  - 每个文件校验 sha256，全部一致才输出 ALL_MATCH = True
"""
import os
import sys
import json
import time
import base64
import hashlib
import urllib.request
import urllib.error
from urllib.parse import quote

UA = {"User-Agent": "wb-task-resume"}


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def get_bytes(url):
    last = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except Exception as e:
            last = e
            if attempt == 0:
                time.sleep(1)
    raise last


def api_fetch(repo, bundle, branch, rel):
    path = (bundle + "/" + rel).strip("/")
    url = "https://api.github.com/repos/%s/contents/%s?ref=%s" % (
        repo, quote(path, safe="/"), branch)
    obj = json.loads(get_bytes(url).decode("utf-8"))
    if obj.get("encoding") != "base64" or "content" not in obj:
        raise RuntimeError("API 未返回 base64 内容")
    return base64.b64decode(obj["content"])


def main():
    if len(sys.argv) < 3:
        sys.exit("用法: python fetch_task.py <raw_base> <target_dir> [--repo owner/repo] [--bundle path] [--branch main]")
    raw_base = sys.argv[1].rstrip("/")
    target = os.path.abspath(sys.argv[2])
    extra = sys.argv[3:]
    def opt(name, default=""):
        return extra[extra.index(name) + 1] if name in extra and extra.index(name) + 1 < len(extra) else default

    repo = opt("--repo", "rgck1/ai-archive")
    branch = opt("--branch", "main")
    bundle = opt("--bundle", "")

    try:
        manifest_data = get_bytes(raw_base + "/MANIFEST.json")
        manifest = json.loads(manifest_data.decode("utf-8"))
    except Exception as e:
        if not bundle:
            sys.exit("ERROR: 读取 MANIFEST.json 失败: %s（可加 --repo 与 --bundle 走 API 回退）" % e)
        try:
            manifest_data = api_fetch(repo, bundle, branch, "MANIFEST.json")
            manifest = json.loads(manifest_data.decode("utf-8"))
        except Exception as e2:
            sys.exit("ERROR: raw 与 API 均读取清单失败: %s / %s" % (e, e2))

    repo = manifest.get("github_repo", repo)
    branch = manifest.get("github_branch", branch)
    bundle = manifest.get("bundle_path", bundle or raw_base.split("/main/")[-1])

    print("任务ID:", manifest.get("task_id"))
    print("标题:", manifest.get("title"))
    print("清单文件数:", manifest.get("file_count"))
    print("拉取自:", raw_base)

    ok = 0
    bad = []
    for item in manifest.get("files", []):
        rel = item["path"]
        try:
            try:
                data = get_bytes(raw_base + "/" + quote(rel))
            except Exception:
                data = api_fetch(repo, bundle, branch, rel)
        except Exception as e:
            bad.append((rel, "下载失败 " + str(e)))
            print("  FAIL", rel, str(e)[:80])
            continue
        if sha256_bytes(data) != item.get("sha256"):
            bad.append((rel, "sha256 不一致"))
            print("  FAIL", rel, "sha256 不一致")
            continue
        dest = os.path.join(target, *rel.split("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(data)
        ok += 1
        print("  OK  ", rel)

    with open(os.path.join(target, "MANIFEST.json"), "wb") as f:
        f.write(manifest_data)

    print("完成: %d/%d" % (ok, manifest.get("file_count", 0)))
    for rel, why in bad:
        print("  MISMATCH", rel, why)
    print("ALL_MATCH =", not bad)
    sys.exit(0 if not bad else 1)


if __name__ == "__main__":
    main()
