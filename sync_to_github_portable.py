"""便携版 GitHub 同步脚本，供另一台设备写回新进度使用。

设计要点：
  1. 令牌优先从环境变量 GITHUB_TOKEN 读取，其次从凭据文件读取
  2. 凭据文件格式与本机一致，字段为 token owner repo branch
  3. 源目录通过命令行参数指定，不硬编码任何路径
  4. 令牌只显示前 4 位，不写入日志、不进入输出内容
  5. 推送后重新拉取远端做逐字节核对，全部一致才输出 ALL_MATCH = True

用法：
  python sync_to_github_portable.py <要推送的目录> --cred <凭据文件>
  python sync_to_github_portable.py <要推送的目录> --verify --cred <凭据文件>
  python sync_to_github_portable.py <要推送的目录> --dry-run --cred <凭据文件>
"""
import os
import sys
import json
import base64
import hashlib
import argparse
import urllib.request
import urllib.error
from urllib.parse import quote

DEFAULT_CRED = os.path.join(os.path.expanduser("~"), ".github_cred.json")
SKIP_DIRS = {".git", "__pycache__", ".obsidian"}


def load_cred(args):
    cred = {}
    cred_path = os.path.abspath(os.path.expanduser(args.cred))
    if os.path.exists(cred_path):
        with open(cred_path, encoding="utf-8-sig") as f:
            cred = json.load(f)
    env_token = os.environ.get("GITHUB_TOKEN", "").strip()
    token = env_token or str(cred.get("token") or "").strip()
    if not token:
        sys.exit("ERROR: 未找到令牌。请设置环境变量 GITHUB_TOKEN，或写入凭据文件：" + cred_path)
    return {
        "token": token,
        "owner": args.owner or cred.get("owner") or "rgck1",
        "repo": args.repo or cred.get("repo") or "ai-archive",
        "branch": args.branch or cred.get("branch") or "main",
        "cred_path": cred_path,
    }


def blob_sha(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def main():
    p = argparse.ArgumentParser(description="推送本地目录到 GitHub 仓库并逐字节核对")
    p.add_argument("source", help="要推送的本地目录")
    p.add_argument("--cred", default=DEFAULT_CRED, help="凭据文件路径")
    p.add_argument("--owner", default=None, help="仓库所有者，默认 rgck1")
    p.add_argument("--repo", default=None, help="仓库名，默认 ai-archive")
    p.add_argument("--branch", default=None, help="分支，默认 main")
    p.add_argument("--prefix", default="", help="仓库内目标子目录，用于隔离新进度，避免覆盖原归档")
    p.add_argument("--verify", action="store_true", help="只核对，不推送")
    p.add_argument("--dry-run", action="store_true", help="只列出待推送文件")
    args = p.parse_args()

    source = os.path.abspath(os.path.expanduser(args.source))
    if not os.path.isdir(source):
        sys.exit("ERROR: 源目录不存在：" + source)

    c = load_cred(args)
    base = "https://api.github.com/repos/%s/%s/contents" % (c["owner"], c["repo"])
    head = {
        "Authorization": "Bearer " + c["token"],
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "wb-portable-sync",
    }

    def req(url, method="GET", body=None):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        r = urllib.request.Request(url, data=data, headers=head, method=method)
        with urllib.request.urlopen(r, timeout=45) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8", "replace"))

    prefix = (args.prefix or "").strip("/")

    def in_repo(rel):
        return (prefix + "/" + rel) if prefix else rel

    def list_remote(path=""):
        url_path = in_repo(path)
        url = base + (("/" + quote(url_path)) if url_path else "")
        try:
            _, items = req(url)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {}
            raise
        out = {}
        for it in items if isinstance(items, list) else []:
            name = it.get("name") or ""
            rel = (path + "/" + name) if path else name
            if it.get("type") == "file":
                out[rel] = it.get("sha")
            elif it.get("type") == "dir":
                out.update(list_remote(rel))
        return out

    try:
        remote = list_remote()
    except urllib.error.HTTPError as e:
        sys.exit("ERROR: 读取仓库失败，HTTP %d。请检查令牌是否有效、是否授权该仓库。" % e.code)
    except Exception as e:
        sys.exit("ERROR: 网络请求失败：%s" % e)

    local = {}
    for root, dirs, files in os.walk(source):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in files:
            if fn.startswith("."):
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, source).replace("\\", "/")
            with open(full, "rb") as f:
                local[rel] = f.read()

    to_push = [rel for rel, data in local.items() if blob_sha(data) != remote.get(rel)]
    token_source = "环境变量 GITHUB_TOKEN" if os.environ.get("GITHUB_TOKEN", "").strip() else "凭据文件"
    print("令牌来源=%s  令牌前4位=%s***" % (token_source, c["token"][:4]))
    print("仓库=%s/%s  分支=%s  目标子目录=%s" % (c["owner"], c["repo"], c["branch"], prefix or "根目录"))
    print("远端文件=%d  本地文件=%d  待推送=%d" % (len(remote), len(local), len(to_push)))

    if args.dry_run:
        for rel in sorted(to_push):
            print("  WOULD PUSH", rel)
        print("DRY-RUN 完成，未推送")
        return

    if not args.verify:
        ok = fail = 0
        for rel in sorted(to_push):
            body = {
                "message": "resume sync " + rel,
                "content": base64.b64encode(local[rel]).decode("ascii"),
                "branch": c["branch"],
            }
            if rel in remote:
                body["sha"] = remote[rel]
            try:
                req(base + "/" + quote(in_repo(rel)), "PUT", body)
                ok += 1
                print("  OK  ", ("upd " if rel in remote else "new "), rel)
            except urllib.error.HTTPError as e:
                fail += 1
                print("  FAIL", rel, e.code, e.read().decode("utf-8", "replace")[:120])
        print("推送完成 ok=%d fail=%d" % (ok, fail))

    final = list_remote()
    mism = [rel for rel, data in sorted(local.items()) if blob_sha(data) != final.get(rel)]
    print("核对: %d/%d 一致" % (len(local) - len(mism), len(local)))
    for rel in mism:
        print("  MISMATCH", rel)
    print("ALL_MATCH =", not mism)
    if mism:
        sys.exit(2)


if __name__ == "__main__":
    main()
