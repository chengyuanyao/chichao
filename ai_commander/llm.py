#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""可选的 LLM 顾问：纯标准库 HTTP，跑在后台线程里。

**绝不能在 tick 里等 LLM。** `tick_bots` 是在 `room_lock(room)` 里跑的 20Hz
模拟的一部分，一次网络往返几秒钟，等回来整局都卡住了。所以这里的分工是：

    主循环（持锁）  : 生成一份很小的战场快照，塞给顾问，立刻读走上一次的结论
    顾问线程（无锁）: 慢慢调 LLM，解析出指令，覆盖到自己的槽位上

调不通、超时、返回的 JSON 不合法——统统当作"这次没有建议"，AI 继续按
`templates.py` 的固定模板打。所以没有 API Key 也是完整可玩的。
"""

from __future__ import print_function

import json
import threading
import time
import urllib.request as urlrequest

DEFAULT_TIMEOUT = 25.0
DEFAULT_MAX_TOKENS = 700

# 连续这么久没人喂快照，顾问线程就自己收摊。
# 不能指望外面显式 stop()：`tick_game` 在 status != "playing" 时第一行就
# return，房间一打完 `tick_bots` 再也不会被调用，任何写在那里的清理都跑不到。
IDLE_EXIT_SECONDS = 300.0

SYSTEM_PROMPT = """你是即时战略游戏《赤潮：钢铁前线》里一名 AI 玩家的参谋。
你不做微操，只决定"造什么兵、造什么楼、什么时候压"。

实际伤害 = 基础伤害 × 伤害类型对护甲类的倍率。护甲类有五种：
infantry(步兵) / light(轻甲) / heavy(重甲) / structure(建筑) / arcane(魔导)。
秘法会除采集单位外全是魔导甲；钢铁军团的载具是重甲、步兵是步兵甲。
注意穿甲(ap)对重甲 ×2.10 但对魔导甲只有 ×1.00——打秘法会别堆坦克歼击车。

只回一个 JSON 对象，不要任何解释文字、不要代码块围栏：
{"army_mix": {"兵种id": 权重整数, ...},
 "build_order": ["建筑id", ...],
 "attack_at": 整数, "harvesters": 整数, "max_turrets": 整数,
 "note": "一句话理由"}
所有字段都可以省略，省略就沿用现有设定。army_mix 最多 4 个兵种，
只能用"可用兵种"里列出的 id。"""


def _is_private_host(host):
    host = (host or "").lower()
    if host in ("localhost", "127.0.0.1", "::1"):
        return True
    parts = host.split(".")
    if len(parts) == 4 and all(part.isdigit() for part in parts):
        a, b = int(parts[0]), int(parts[1])
        return a == 10 or a == 127 or (a == 192 and b == 168) or (a == 172 and 16 <= b <= 31)
    return False


class LLMClient(object):
    """OpenAI 兼容 / Anthropic 两种后端，够用就行。"""

    def __init__(self, provider, base_url, api_key, model,
                 timeout=DEFAULT_TIMEOUT, max_tokens=DEFAULT_MAX_TOKENS):
        self.provider = (provider or "openai").strip().lower()
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.model = model or ""
        self.timeout = float(timeout)
        self.max_tokens = int(max_tokens)
        # 内网端点被系统代理劫持时不会报错，只会挂死到超时，排查很贵。
        # 私网地址一律直连。
        try:
            host = self.base_url.split("//", 1)[-1].split("/", 1)[0].split(":")[0]
        except Exception:
            host = ""
        if _is_private_host(host):
            self._opener = urlrequest.build_opener(urlrequest.ProxyHandler({}))
        else:
            self._opener = urlrequest.build_opener()

    # ------------------------------------------------------------------
    def _post(self, url, payload, headers):
        body = json.dumps(payload).encode("utf-8")
        request = urlrequest.Request(url, data=body)
        request.add_header("Content-Type", "application/json")
        for key, value in headers.items():
            request.add_header(key, value)
        handle = self._opener.open(request, timeout=self.timeout)
        try:
            raw = handle.read().decode("utf-8", "replace")
        finally:
            handle.close()
        return json.loads(raw)

    def ask(self, user_text):
        """返回模型正文字符串；任何失败都抛异常，由调用方吞掉。"""
        if self.provider == "anthropic":
            url = (self.base_url or "https://api.anthropic.com") + "/v1/messages"
            payload = {
                "model": self.model, "max_tokens": self.max_tokens,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_text}],
            }
            data = self._post(url, payload, {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            })
            chunks = []
            for block in data.get("content") or []:
                if block.get("type") == "text":
                    chunks.append(block.get("text") or "")
            return "".join(chunks)

        base = self.base_url or "https://api.openai.com/v1"
        if not base.endswith("/v1") and "/v1" not in base:
            base += "/v1"
        payload = {
            "model": self.model, "max_tokens": self.max_tokens, "temperature": 0.3,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
        }
        data = self._post(base + "/chat/completions", payload,
                          {"Authorization": "Bearer " + self.api_key})
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("响应里没有 choices")
        return (choices[0].get("message") or {}).get("content") or ""

    def probe(self):
        """开局探活，返回 None 表示可用，否则返回失败原因。"""
        try:
            self.ask("回一个空 JSON 对象 {}")
            return None
        except Exception as exc:
            return "%s: %s" % (type(exc).__name__, exc)


# ---------------------------------------------------------------- 指令解析
def parse_directive(text, allowed_units, allowed_structures):
    """从模型正文里抠出 JSON 指令，并按可用清单过滤。返回 None 表示不可用。"""
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None

    out = {}
    mix = data.get("army_mix")
    if isinstance(mix, dict):
        clean = {}
        for kind, weight in mix.items():
            if kind in allowed_units:
                try:
                    value = int(weight)
                except (TypeError, ValueError):
                    continue
                if value > 0:
                    clean[kind] = min(9, value)
        if clean:
            out["army_mix"] = clean
    build = data.get("build_order")
    if isinstance(build, list):
        clean_build = [item for item in build
                       if isinstance(item, str) and item in allowed_structures]
        if clean_build:
            out["build_order"] = clean_build[:12]
    # attack_at 上限刻意压到 60：模型很容易顺口给个 200，那等于叫 AI 永远
    # 别出门，一局就这么耗死了。60 个战斗单位已经是满编，够保守了。
    for key, low, high in (("attack_at", 0, 60), ("harvesters", 2, 9),
                           ("max_turrets", 0, 6)):
        if key in data:
            try:
                out[key] = max(low, min(high, int(data[key])))
            except (TypeError, ValueError):
                pass
    if isinstance(data.get("note"), str):
        out["note"] = data["note"][:160]
    return out or None


# ---------------------------------------------------------------- 顾问线程
class Advisor(object):
    """一个 bot 一个顾问。主循环只碰 submit()/take()，两者都不阻塞。"""

    _gate = threading.Semaphore(2)      # 全局最多两个在飞的请求，别打爆端点

    def __init__(self, client, interval=45.0, log=None):
        self.client = client
        self.interval = float(interval)
        self.log = log or (lambda *a: None)
        self._lock = threading.Lock()
        self._pending = None            # 待发送的快照
        self._directive = None          # 最近一次可用指令
        self._directive_at = 0.0
        self._last_error = None
        self._busy = False
        self._next_at = 0.0
        self._last_submit = time.time()
        self._alive = True
        self._thread = threading.Thread(target=self._run)
        self._thread.daemon = True
        self._thread.start()

    def stop(self):
        with self._lock:
            self._alive = False

    def alive(self):
        with self._lock:
            return self._alive

    # -------- 主循环侧（持锁调用，必须瞬间返回）--------
    def wants(self):
        """这一跳顾问收不收快照。

        主循环据此决定要不要拼那段战场快照——拼一次要跑两趟 rank_units 再
        拼一大串字符串，而且是在 room_lock 里跑的。绝大多数 tick 都还在
        间隔冷却里，拼了也是白拼。
        """
        with self._lock:
            return (self._alive and not self._busy
                    and time.time() >= self._next_at)

    def submit(self, snapshot):
        now = time.time()
        with self._lock:
            if not self._alive or self._busy or now < self._next_at:
                return False
            self._pending = snapshot
            self._busy = True
            self._next_at = now + self.interval
            self._last_submit = now
            return True

    def take(self, max_age=180.0):
        with self._lock:
            if self._directive is None:
                return None
            if time.time() - self._directive_at > max_age:
                return None
            return dict(self._directive)

    def status(self):
        with self._lock:
            if self._last_error:
                return "LLM 失败：" + self._last_error
            if self._directive is None:
                return "LLM 尚无建议"
            return "LLM 建议 %.0fs 前" % (time.time() - self._directive_at)

    # -------- 顾问线程侧 --------
    def _run(self):
        while self._alive:
            with self._lock:
                snapshot = self._pending
                self._pending = None
                idle_for = time.time() - self._last_submit
            if snapshot is None:
                if idle_for > IDLE_EXIT_SECONDS:
                    # 这一局已经不喂快照了（打完、房间被回收、或这个 bot 被
                    # 淘汰）。没人来 stop 我们，只能自己退出，否则每打一局
                    # 就留下一个 4Hz 空转的线程直到进程结束。
                    with self._lock:
                        self._alive = False
                        self._busy = False
                    break
                time.sleep(0.25)
                with self._lock:
                    if self._pending is None:
                        self._busy = False
                continue
            directive = None
            error = None
            with Advisor._gate:
                try:
                    text = self.client.ask(snapshot["prompt"])
                    directive = parse_directive(
                        text, snapshot["units"], snapshot["structures"])
                    if directive is None:
                        error = "返回内容里没有可用的 JSON 指令"
                except Exception as exc:               # noqa: BLE001 - 任何失败都降级
                    error = "%s: %s" % (type(exc).__name__, exc)
            with self._lock:
                self._busy = False
                self._last_error = error
                if directive is not None:
                    self._directive = directive
                    self._directive_at = time.time()
            if error:
                self.log("[AI-LLM] %s（本轮继续按固定模板打）" % error)
            elif directive:
                self.log("[AI-LLM] %s -> %s" % (
                    snapshot.get("who", "?"),
                    directive.get("note") or json.dumps(
                        directive.get("army_mix") or {}, ensure_ascii=False)))
