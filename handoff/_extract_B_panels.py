import json, re, io, hashlib, os

base = os.path.dirname(os.path.abspath(__file__))
doc = json.load(io.open(os.path.join(base, "_C_doc_hub.json"), encoding="utf-8"))
c = doc["data"]["content"]
m = re.search(r"<Code[^>]*>(.*?)</Code>", c, re.S)
assert m, "code block not found"

fence = chr(96) * 3
lines = m.group(1).split("\n")
# 文档把代码块整体缩进了 2 个空格，逐行去掉
body = "\n".join(l[2:] if l.startswith("  ") else l for l in lines).strip("\n")
body = re.sub(r"^" + re.escape(fence) + r"js\s*\n", "", body)
body = re.sub(r"\n" + re.escape(fence) + r"\s*$", "", body)

raw = body.encode("utf-8")
print("LINES", len(body.split("\n")))
print("BYTES", len(raw))
print("SHA16", hashlib.sha256(raw).hexdigest()[:16])
print("DOC_SHA16", "c3eddf28e80805b3")
print("MATCH", hashlib.sha256(raw).hexdigest()[:16] == "c3eddf28e80805b3")
out = os.path.join(base, "v86_B_panels_448_权威版.js")
io.open(out, "w", encoding="utf-8", newline="").write(body)
print("WROTE", out)
