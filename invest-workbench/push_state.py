# -*- coding: utf-8 -*-
"""推送幂等与失败留痕：按内容 SHA 去重，避免同 SHA 重复推送；失败写队列便于重放。

两个推送脚本（净值 / 持仓）共用。设计：
- state/<name>.json 记 {last_ok_sha, last_ok_at, last_scope, history:[...]}；
- should_push(name, sha) -> True/False：同 SHA 已成功推过则跳过（除非 force）；
- mark_ok / mark_fail 写状态；失败进 retry 队列，供下次或人工重放；
- 纯本地文件，不改服务器端合并逻辑（服务器端本就是按 date/code 覆盖，天然幂等）。
"""
import os
import json
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(HERE, "push_state")


def _path(name):
    return os.path.join(STATE_DIR, name + ".json")


def _load(name):
    try:
        return json.load(open(_path(name), encoding="utf-8"))
    except Exception:
        return {"last_ok_sha": None, "history": []}


def _save(name, st):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = _path(name) + ".tmp"
        json.dump(st, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        os.replace(tmp, _path(name))
    except Exception:
        pass


def should_push(name, sha, force=False, limit_history=30):
    st = _load(name)
    if (not force) and st.get("last_ok_sha") == sha:
        return False, "同 SHA 已成功推送过（%s），跳过" % st.get("last_ok_at", "?")
    return True, ""


def mark_ok(name, sha, scope=None):
    st = _load(name)
    st["last_ok_sha"] = sha
    st["last_ok_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if scope is not None:
        st["last_scope"] = scope
    h = st.setdefault("history", [])
    h.insert(0, {"sha": sha, "at": st["last_ok_at"], "scope": scope, "result": "ok"})
    st["history"] = h[:30]
    st.pop("pending_retry", None)
    _save(name, st)


def mark_fail(name, sha, reason, scope=None):
    st = _load(name)
    h = st.setdefault("history", [])
    h.insert(0, {"sha": sha,
                 "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 "scope": scope, "result": "fail", "reason": str(reason)[:200]})
    st["history"] = h[:30]
    st["pending_retry"] = {"sha": sha, "scope": scope, "reason": str(reason)[:200]}
    _save(name, st)


def pending(name):
    return _load(name).get("pending_retry")


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == "status":
        for n in ("nav", "holdings"):
            st = _load(n)
            print(n, "last_ok=", st.get("last_ok_sha"), "@", st.get("last_ok_at"),
                  "pending=", bool(st.get("pending_retry")))
