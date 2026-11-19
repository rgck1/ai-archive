# -*- coding: utf-8 -*-
"""公共抓取限流/熔断底座（P1，借鉴 xueqiu-mcp + snowball-monitor，2026-11-19）。

给雪球 / 东财 / 腾讯三条抓取共用，统一：
  - MIN_REQUEST_INTERVAL=1000ms + 500ms 随机抖动（防高频风控）
  - 429 指数退避；400/401/403 判定为鉴权/硬拒，不重试（越试封越久）
  - 连续失败 5 次熔断 5 分钟（circuit breaker）
  - RemoteDisconnected / 连接被重置 → 立即熔断并抛源切换信号（东财云 IP 场景）

设计原则：
  - 纯标准库、无第三方依赖、无全局可变状态散落；每个逻辑源一个 GuardedFetch 实例。
  - 不强制替换现有抓取代码；提供 guarded_call() 包装任意 callable，逐步接入。
  - 状态只在进程内存（重启即复位），不落盘——熔断是短时保护，不需要持久化。
"""
import random
import time

MIN_INTERVAL = 1.0      # 秒：两次请求最小间隔
JITTER = 0.5            # 秒：额外随机抖动
MAX_FAILS = 5           # 连续失败阈值
BREAK_SECONDS = 300     # 熔断时长（5 分钟）
RETRY_429_MAX = 3       # 429 最多退避次数

# 这些异常文本出现即判「源已封」，立即熔断、不重试、交调用方切源
HARD_BLOCK_MARKS = ("remotedisconnected", "connection reset", "connection aborted",
                    "connection forcibly closed", "timed out", "proxyerror")


class CircuitOpen(Exception):
    """熔断中：调用方应改用备用源（如东财熔断切腾讯）。"""
    pass


class HardBlock(Exception):
    """硬拒/风控：鉴权失效或连接被重置，禁止重试，调用方应切源或提示更新 Cookie。"""
    def __init__(self, msg, status=None):
        super().__init__(msg)
        self.status = status


def _is_auth_error(exc):
    """400/401/403 判为鉴权/硬拒（含异常携带的 status 或文本里的 HTTP 码）。"""
    status = getattr(exc, "status", None) or getattr(exc, "code", None)
    if status in (400, 401, 403):
        return True
    s = str(exc).lower()
    return any(("http %d" % c) in s or (" %d " % c) in s or ("code %d" % c) in s
               for c in (400, 401, 403))


def _is_hard_block(exc):
    s = str(exc).lower()
    return any(m in s for m in HARD_BLOCK_MARKS)


class GuardedFetch:
    """单个逻辑源的限流+熔断守卫。线程内使用（不保证跨线程安全，抓取脚本多为单线程）。"""

    def __init__(self, name, min_interval=MIN_INTERVAL, jitter=JITTER,
                 max_fails=MAX_FAILS, break_seconds=BREAK_SECONDS):
        self.name = name
        self.min_interval = min_interval
        self.jitter = jitter
        self.max_fails = max_fails
        self.break_seconds = break_seconds
        self._last_call = 0.0
        self._fails = 0
        self._open_until = 0.0
        self.stats = {"calls": 0, "ok": 0, "fail": 0, "blocked": 0,
                      "circuits": 0, "retries_429": 0}

    def _wait_slot(self):
        now = time.time()
        target = self._last_call + self.min_interval + random.uniform(0, self.jitter)
        if now < target:
            time.sleep(target - now)

    def _note_ok(self):
        self._fails = 0
        self.stats["ok"] += 1

    def _note_fail(self, exc):
        self._fails += 1
        self.stats["fail"] += 1
        if _is_hard_block(exc) or self._fails >= self.max_fails:
            self._open_until = time.time() + self.break_seconds
            self.stats["circuits"] += 1
            raise CircuitOpen("%s 熔断 %ds（连续失败 %d / 硬拒）: %s" % (
                self.name, self.break_seconds, self._fails, str(exc)[:80]))

    def call(self, fn, *args, _allow_429=True, **kwargs):
        """在守卫下调用 fn(*args, **kwargs)，返回结果。

        429 → 指数退避重试（最多 3 次）；400/401/403 → HardBlock 不重试；
        连接重置/RemoteDisconnected → 立即 CircuitOpen；连续失败达阈值 → 熔断。
        """
        if time.time() < self._open_until:
            self.stats["blocked"] += 1
            raise CircuitOpen("%s 熔断中，剩余 %.0fs，请切备用源" % (
                self.name, self._open_until - time.time()))
        attempts429 = 0
        while True:
            self._wait_slot()
            self._last_call = time.time()
            self.stats["calls"] += 1
            try:
                out = fn(*args, **kwargs)
                self._note_ok()
                return out
            except Exception as e:
                status = getattr(e, "status", None) or getattr(e, "code", None)
                if status == 429 or "429" in str(e):
                    if _allow_429 and attempts429 < RETRY_429_MAX:
                        attempts429 += 1
                        self.stats["retries_429"] += 1
                        time.sleep(min(2 ** attempts429, 16))
                        continue
                    self._note_fail(e)
                    raise
                if _is_auth_error(e) or _is_hard_block(e):
                    self._note_fail(e)
                    raise HardBlock(str(e)[:120], status=status)
                self._note_fail(e)
                raise

    def snapshot(self):
        return {"name": self.name, "fails": self._fails,
                "open_for": max(0.0, self._open_until - time.time()),
                **self.stats}


# 全局单例（按逻辑源），供多脚本 import 共享同一熔断状态
_sources = {}


def get(source):
    """get('xueqiu'|'eastmoney'|'tencent') -> GuardedFetch（进程内单例）。"""
    if source not in _sources:
        _sources[source] = GuardedFetch(source)
    return _sources[source]


if __name__ == "__main__":
    # 自测：模拟 429 退避、连续失败熔断、鉴权不重试
    g = GuardedFetch("selftest", min_interval=0, jitter=0, max_fails=3, break_seconds=1)
    calls = {"n": 0}
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("429 too many requests")
        return "ok"
    print("429 retry ->", g.call(flaky), "retries=", g.stats["retries_429"])
    g2 = GuardedFetch("auth", min_interval=0, jitter=0)
    try:
        g2.call(lambda: (_ for _ in ()).throw(RuntimeError("HTTP 403 Forbidden")))
    except HardBlock as e:
        print("403 -> HardBlock, no retry, calls=", g2.stats["calls"])
    g3 = GuardedFetch("brk", min_interval=0, jitter=0, max_fails=2, break_seconds=1)
    for _ in range(2):
        try: g3.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        except Exception: pass
    print("after 2 fails, snapshot=", g3.snapshot())
    try:
        g3.call(lambda: "should not run")
    except CircuitOpen as e:
        print("circuit open ->", str(e)[:60])
