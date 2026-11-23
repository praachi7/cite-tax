"""Language-model client for Phase D: Groq's free tier over its OpenAI-compatible HTTP API.

* Every response is cached on disk (build/llm_cache/), keyed by model, messages and settings.
  Re-running an evaluation costs no quota and gives identical results.
* On a rate limit (HTTP 429) it waits for Groq's retry-after and tries again.
* temperature 0, so repeated uncached calls also agree as far as the provider allows.
* The key comes from GROQ_API_KEY (read from .env); it is never logged.

The LLM never computes tax and never picks the law version; it only drafts wording and judges
whether a passage supports a sentence. Anything with the `complete_json` method can stand in for it
(the tests use a fake).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Protocol

import httpx

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "build" / "llm_cache"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = os.environ.get("CITETAX_LLM_MODEL", "openai/gpt-oss-120b")


class LLM(Protocol):
    model: str

    def complete_json(self, system: str, user: str, max_tokens: int = 1500) -> dict: ...


class LLMError(RuntimeError):
    pass


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:  # python-dotenv is optional when the variables are already set
        pass


def parse_json(text: str) -> dict:
    """The model is asked for one JSON object; tolerate code fences or text around it."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise LLMError(f"no JSON object in model output: {text[:200]!r}")
    return json.loads(text[start:end + 1])


class GroqLLM:
    def __init__(self, model: str = DEFAULT_MODEL, api_key: str | None = None, cache: bool = True,
                 max_retries: int = 6, reasoning_effort: str | None = "low"):
        _load_env()
        self.model = model
        self._key = api_key or os.environ.get("GROQ_API_KEY", "")
        if not self._key:
            raise LLMError("GROQ_API_KEY is not set; copy .env.example to .env and add the key")
        self.cache = cache
        self.max_retries = max_retries
        self.reasoning_effort = reasoning_effort if model.startswith("openai/gpt-oss") else None
        self.calls = 0          # uncached requests sent
        self.cache_hits = 0

    def _body(self, system: str, user: str, max_tokens: int) -> dict:
        body = {"model": self.model, "temperature": 0, "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort
        return body

    def complete_json(self, system: str, user: str, max_tokens: int = 1500) -> dict:
        body = self._body(system, user, max_tokens)
        key = hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf8")).hexdigest()
        path = CACHE_DIR / f"{key}.json"
        if self.cache and path.exists():
            self.cache_hits += 1
            return json.loads(path.read_text(encoding="utf8"))["parsed"]
        text = self._post(body)
        parsed = parse_json(text)
        if self.cache:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"model": self.model, "raw": text, "parsed": parsed}, ensure_ascii=False),
                            encoding="utf8")
        return parsed

    def _post(self, body: dict) -> str:
        for attempt in range(self.max_retries + 1):
            try:
                r = httpx.post(GROQ_URL, json=body, timeout=120,
                               headers={"Authorization": f"Bearer {self._key}"})
            except httpx.HTTPError as e:
                if attempt == self.max_retries:
                    raise LLMError(f"network error talking to Groq: {e}") from e
                time.sleep(2 ** attempt)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                wait = float(r.headers.get("retry-after") or 2 ** attempt)
                if attempt == self.max_retries:
                    raise LLMError(f"Groq returned {r.status_code} after {attempt + 1} tries: {r.text[:200]}")
                time.sleep(min(wait, 90) + 0.5)
                continue
            if r.status_code != 200:
                raise LLMError(f"Groq returned {r.status_code}: {r.text[:300]}")
            self.calls += 1
            return r.json()["choices"][0]["message"]["content"] or ""
        raise LLMError("unreachable")
