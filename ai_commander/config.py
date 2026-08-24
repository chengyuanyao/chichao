#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""运行配置与 LLM 凭据。

API Key 一律由使用者自己提供，仓库里不留任何密钥。四个来源，优先级从高到低：

    1. 命令行参数（start.py --key/--base/--model/...）
    2. 环境变量 AI_LLM_KEY / AI_LLM_BASE / AI_LLM_MODEL / AI_LLM_PROVIDER
    3. 本地文件 ai_commander/llm.json（可从 llm.example.json 复制，已 gitignore）
    4. 启动时交互式询问（直接回车＝不接 LLM，走固定模板）
"""

from __future__ import print_function

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CREDENTIAL_FILE = os.path.join(HERE, "llm.json")

MODES = ("all", "first", "off")

DEFAULT_INTERVAL = 45.0


class Settings(object):
    def __init__(self):
        self.mode = "all"          # 哪些 bot 换新大脑：all / first / off
        self.provider = "openai"   # openai（含各种兼容端点）| anthropic
        self.base_url = ""
        self.api_key = ""
        self.model = ""
        self.interval = DEFAULT_INTERVAL
        self.verbose = True

    # ------------------------------------------------------------------
    def llm_enabled(self):
        return bool(self.api_key and self.model)

    def describe(self):
        if not self.llm_enabled():
            return "AI 指挥官：固定模板模式（没有配置 LLM）"
        return "AI 指挥官：LLM 模式 provider=%s model=%s 间隔=%.0fs" % (
            self.provider, self.model, self.interval)

    def make_client(self):
        if not self.llm_enabled():
            return None
        from ai_commander.llm import LLMClient
        return LLMClient(self.provider, self.base_url, self.api_key, self.model)

    # ------------------------------------------------------------------
    def load_file(self, path=CREDENTIAL_FILE):
        if not os.path.exists(path):
            return False
        try:
            with open(path, "r") as handle:
                data = json.load(handle)
        except (ValueError, IOError):
            return False
        self.provider = data.get("provider") or self.provider
        self.base_url = data.get("base_url") or self.base_url
        self.api_key = data.get("api_key") or self.api_key
        self.model = data.get("model") or self.model
        try:
            self.interval = float(data.get("interval") or self.interval)
        except (TypeError, ValueError):
            pass
        return True

    def save_file(self, path=CREDENTIAL_FILE):
        payload = {"provider": self.provider, "base_url": self.base_url,
                   "api_key": self.api_key, "model": self.model,
                   "interval": self.interval}
        with open(path, "w") as handle:
            json.dump(payload, handle, indent=2)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    def load_env(self):
        self.mode = (os.environ.get("AI_COMMANDER") or self.mode).strip().lower()
        if self.mode not in MODES:
            self.mode = "all"
        self.provider = (os.environ.get("AI_LLM_PROVIDER")
                         or self.provider).strip().lower()
        self.base_url = os.environ.get("AI_LLM_BASE") or self.base_url
        self.api_key = os.environ.get("AI_LLM_KEY") or self.api_key
        self.model = os.environ.get("AI_LLM_MODEL") or self.model
        raw = os.environ.get("AI_LLM_INTERVAL")
        if raw:
            try:
                self.interval = max(10.0, float(raw))
            except ValueError:
                pass
        if os.environ.get("AI_QUIET"):
            self.verbose = False


# ---------------------------------------------------------------- 交互输入
def prompt_for_llm(settings):
    """在终端里问 API Key。直接回车＝不接 LLM，AI 走固定模板。"""
    print("")
    print("-" * 58)
    print("  AI 指挥官 · LLM 接入（可选）")
    print("  直接回车跳过：AI 会按内置的固定模板出兵，完全可玩。")
    print("-" * 58)
    key = input("  API Key（回车跳过）: ").strip()
    if not key:
        print("  已跳过，使用固定模板模式。")
        return settings
    settings.api_key = key

    provider = input("  后端 [openai/anthropic]（默认 openai）: ").strip().lower()
    settings.provider = provider if provider in ("openai", "anthropic") else "openai"

    if settings.provider == "anthropic":
        default_base = "https://api.anthropic.com"
        default_model = "claude-sonnet-5"
    else:
        default_base = "https://api.openai.com/v1"
        default_model = ""
    base = input("  接口地址（默认 %s）: " % default_base).strip()
    settings.base_url = base or default_base
    model = input("  模型名%s: " % ("（默认 %s）" % default_model if default_model else "")).strip()
    settings.model = model or default_model
    if not settings.model:
        print("  没填模型名，改用固定模板模式。")
        settings.api_key = ""
        return settings

    raw = input("  多久问一次 LLM（秒，默认 %d）: " % int(DEFAULT_INTERVAL)).strip()
    if raw:
        try:
            settings.interval = max(10.0, float(raw))
        except ValueError:
            pass

    if input("  记住这些设置到 ai_commander/llm.json？[y/N] ").strip().lower() == "y":
        try:
            settings.save_file()
            print("  已保存（该文件已在 .gitignore 里，不会进版本库）。")
        except IOError as exc:
            print("  保存失败：%s" % exc)
    return settings


def load(interactive=True):
    settings = Settings()
    settings.load_file()
    settings.load_env()
    if interactive and not settings.llm_enabled():
        prompt_for_llm(settings)
    return settings
