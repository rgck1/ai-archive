"""从 GitHub 公开仓库拉取任务归档包并按 MANIFEST 逐文件校验（仅标准库）。

用法（完整可复制）：
  python "fetch_task.py" "https://raw.githubusercontent.com/rgck1/ai-archive/main/task-archives/任务ID" "本机目标目录"

说明：
  - 脚本会先下载 raw_base/MANIFEST.json，再按清单逐个下载文件
  - 每个文件校验 sha256，全部一致才输出 ALL_MATCH = True
  - 目标目录不存在会自动创建；已存在的文件会被覆盖为归档版本
"""
import os
import sys
import json
import hashlib
import urllib.request
import urllib.error
from urllib.parse import quote


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def fetch(raw_base, rel):
    url = raw_base + "/" + quote(rel)
    req = urllib.request.Request(url, headers={"User-Agent": "wb-task-resume"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def main():
    if len(sys.argv) < 3:
        sys.exit("用法: python fetch_task.py <raw_base> <target_dir>")
    raw_base = sys.argv[1].rstrip("/")
    target = os.path.abspath(sys.argv[2])

    try:
        manifest_data = fetch(raw_base, "MANIFEST.json")
        manifest = json.loads(manifest_data.decode("utf-8"))
    except Exception as e:
        sys.exit("ERROR: 读取 MANIFEST.json 失败: %s" % e)

    print("任务ID:", manifest.get("task_id"))
    print("标题:", manifest.get("title"))
    print("清单文件数:", manifest.get("file_count"))
    print("拉取自:", raw_base)

    ok = 0
    bad = []
    for item in manifest.get("files", []):
        rel = item["path"]
        try:
            data = fetch(raw_base, rel)
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
