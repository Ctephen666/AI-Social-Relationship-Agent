from __future__ import annotations

import re


class IntentRouter:
    """Fast deterministic routing before any LLM call."""

    _spark = re.compile(r"(?:扫描|检查|查看|续|维护).{0,5}(?:火花|抖音)|(?:火花|抖音).{0,5}(?:扫描|检查|查看|维护)")
    _renew = re.compile(r"(?:续(?:一下|个)?火花|抖音.{0,4}续(?:一下|个)?火花|给.{0,8}(?:发消息|续火花)|(?:所有人|全部好友).{0,8}(?:续火花|发消息))")
    _report = re.compile(r"(?:最近|上次|最新).{0,5}(?:火花|扫描).{0,5}(?:结果|报告)")

    def route(self, text: str) -> tuple[str, dict]:
        compact = re.sub(r"[\s，。！？,.!?]", "", text)
        if compact in {"帮助", "你会什么", "你能做什么", "功能"}:
            return "system.help", {}
        if self._report.search(compact):
            return "spark_scan.latest", {}
        if self._renew.search(compact):
            return "spark_renew.prepare", {"max_pages": 100}
        if self._spark.search(compact):
            return "spark_scan.scan", {"max_pages": 30}
        if compact in {"打开设置", "设置", "系统设置"}:
            return "system.settings", {}
        return "conversation", {}
