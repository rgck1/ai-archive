# -*- coding: utf-8 -*-
"""SW 缓存版本工程化：自动 bump + ASSETS 清单完整性校验。

用法：
  python bump_sw.py                 # 递增版本并写入（附变更说明）
  python bump_sw.py --note "说明"   # 同上，追加本次变更原因到版本行的注释链
  python bump_sw.py --dry-run       # 只校验与预览，不写文件

设计边界：
- 只改 `var CACHE = "investdesk-vN";` 中的数字，不动第 9 行的历史变更日志（追溯事实不可删）。
- 校验 ASSETS 里每个静态文件路径对应的本地文件都存在，避免部署后 SW 安装失败。
- 幂等：重复跑不会产生重复 bump（每次基于当前文件里的实际版本 +1）。
"""
import os
import re
import sys
import hashlib
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SW = os.path.join(HERE, "sw.js")
VER_RE = re.compile(r'var CACHE\s*=\s*"investdesk-v(\d+)"\s*;')

# ASSETS 中的 URL -> 本地相对路径（"/" 代表 SPA 外壳 index.html）
ASSET_MAP = {
    "/": "index.html",
    "/factor-picker.html": "factor-picker.html",
    "/manifest.json": "manifest.json",
    "/icon-192.png": "icon-192.png",
    "/icon-512.png": "icon-512.png",
    "/icon-maskable.png": "icon-maskable.png",
    "/apple-touch-icon.png": "apple-touch-icon.png",
}


def check_assets(sw_text):
    """校验 ASSETS 声明的预缓存项都在本地存在，返回 (ok, 明细列表)。"""
    m = re.search(r"var ASSETS\s*=\s*\[(.*?)\]", sw_text, re.S)
    if not m:
        return False, ["未找到 ASSETS 定义"]
    block = m.group(1)
    # 先去掉 // 注释行，避免把注释里的 "/index.html" 误判为声明项
    block = "\n".join(line.split("//")[0] for line in block.splitlines())
    declared = re.findall(r'"(/[^"]*)"', block)
    rows, ok = [], True
    for url in declared:
        local = ASSET_MAP.get(url)
        if local is None:
            rows.append("! %s -> 未登记本地映射（请更新 ASSET_MAP）" % url)
            ok = False
            continue
        p = os.path.join(HERE, local)
        if not os.path.isfile(p):
            rows.append("! %s -> 缺本地文件 %s" % (url, local))
            ok = False
        else:
            rows.append("OK %-24s -> %s (%d B)" % (url, local, os.path.getsize(p)))
    return ok, rows


def main():
    dry = "--dry-run" in sys.argv
    note = ""
    if "--note" in sys.argv:
        i = sys.argv.index("--note")
        if i + 1 < len(sys.argv):
            note = sys.argv[i + 1].strip()

    text = open(SW, encoding="utf-8").read()
    m = VER_RE.search(text)
    if not m:
        print("FAIL: 未找到 CACHE 版本行"); return 2
    old = int(m.group(1))
    new = old + 1

    ok, rows = check_assets(text)
    print("=== ASSETS 完整性 ===")
    for r in rows:
        print(" ", r)
    if not ok:
        print("ABORT: ASSETS 校验未通过，先修预缓存清单再 bump"); return 3

    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    suffix = "   // v%d→v%d：%s（%s）" % (old, new, note or "前端/缓存变更，强制各端重拿新外壳", stamp)
    new_line = 'var CACHE = "investdesk-v%d";%s' % (new, suffix)

    print("\n=== bump 预览 ===")
    print("  旧版本: investdesk-v%d" % old)
    print("  新版本: investdesk-v%d" % new)
    print("  新行:   ", new_line[:150])

    if dry:
        print("\nDRY-RUN 完成（未写入）"); return 0

    new_text = text[:m.start()] + new_line + text[m.end():]
    # 校验只替换了版本行
    if new_text.count('var CACHE =') != text.count('var CACHE ='):
        print("FAIL: CACHE 行数量异常，拒绝写入"); return 4
    open(SW, "w", encoding="utf-8", newline="").write(new_text)
    sha = hashlib.sha256(new_text.encode("utf-8")).hexdigest()[:16]
    print("\nWRITTEN sw.js  investdesk-v%d -> v%d  sha=%s" % (old, new, sha))
    print("下一步：python test_frontend_build.py && python deploy_frontend_now.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
