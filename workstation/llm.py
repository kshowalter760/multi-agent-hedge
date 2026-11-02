import asyncio
import json
import re
import time
from typing import Protocol

import httpx
from pydantic import BaseModel, ValidationError

from .config import Config


def strip_think(text: str) -> str:
    text = re.sub(r"<think\b[^>]*>.*?</think\s*>", "", text, flags=re.S | re.I)
    if re.search(r"</?think\b", text, re.I):
        raise ValueError("Unclosed reasoning block")
    return text.strip()


def clean_strings(value):
    if isinstance(value, str):
        return strip_think(value)
    if isinstance(value, dict):
        return {k: clean_strings(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean_strings(v) for v in value]
    return value


def estimate_tokens(text: str) -> int:
    # Conservative byte-per-token ceiling plus template overhead; may reject prompts that fit.
    return len(text.encode("utf-8")) + 256


class LLMProvider(Protocol):
    digests: dict[str, str]

    async def health(self) -> None: ...
    async def generate(self, agent: str, system: str, payload: dict, schema: type[BaseModel]): ...


class OllamaProvider:
    def __init__(self, config: Config, transport=None):
        self.config = config
        self.transport = transport
        self.digests = {}
        self.semaphore = asyncio.Semaphore(config.concurrency)
        self.remaining = config.token_budget
        self.deadline = time.monotonic() + config.wall_clock_seconds

    def models(self):
        names = [self.config.analyst.model, self.config.risk.model, self.config.pm.model]
        if self.config.senior_approval_enabled:
            names.append(self.config.senior.model)
        return set(names)

    async def tags(self) -> dict:
        async with httpx.AsyncClient(
            base_url=self.config.ollama_host,
            timeout=min(30, self.config.timeout_seconds),
            transport=self.transport,
        ) as client:
            response = await client.get("/api/tags")
            response.raise_for_status()
            models = response.json()["models"]
        return {
            m["name"]: m["digest"]
            for m in models
            if not m.get("remote_host") and not m.get("remote_model") and m.get("digest")
        }

    async def health(self):
        try:
            available = await self.tags()
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise ValueError(
                f"Ollama unavailable at {self.config.ollama_host}; run ollama serve"
            ) from exc
        missing = self.models() - available.keys()
        if missing:
            raise ValueError(
                "Missing local models. Run:\n"
                + "\n".join(f"ollama pull {m}" for m in sorted(missing))
            )
        self.digests = {m: available[m] for m in self.models()}

    async def generate(self, agent, system, payload, schema):
        remaining_time = self.deadline - time.monotonic()
        if remaining_time <= 0:
            raise ValueError("Wall-clock budget exhausted")
        try:
            return await asyncio.wait_for(
                self._generate(agent, system, payload, schema), timeout=remaining_time
            )
        except TimeoutError as exc:
            raise ValueError("Wall-clock budget exhausted") from exc

    async def _generate(self, agent, system, payload, schema):
        config = self.config
        model = getattr(config, agent).model
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        schema_json = schema.model_json_schema()
        estimate = estimate_tokens(system + encoded + json.dumps(schema_json))
        if estimate + config.max_output_tokens > config.num_ctx:
            raise ValueError(
                "Prompt exceeds num_ctx with output reserve; shorten inputs or raise num_ctx"
            )
        async with self.semaphore:
            async with httpx.AsyncClient(
                base_url=config.ollama_host,
                timeout=config.timeout_seconds,
                transport=self.transport,
            ) as client:
                for _ in range(config.retries + 1):
                    reserve = estimate + config.max_output_tokens
                    if self.remaining < reserve:
                        raise ValueError("Token budget exhausted")
                    self.remaining -= reserve
                    if (await self.tags()).get(model) != self.digests.get(model):
                        raise ValueError("Model digest changed; restart research")
                    response = await client.post(
                        "/api/chat",
                        json={
                            "model": model,
                            "stream": False,
                            "messages": [
                                {"role": "system", "content": system},
                                {"role": "user", "content": encoded},
                            ],
                            "format": schema_json,
                            "keep_alive": config.keep_alive,
                            "options": {
                                "num_ctx": config.num_ctx,
                                "temperature": config.temperature,
                                "seed": config.seed,
                                "num_predict": config.max_output_tokens,
                            },
                        },
                    )
                    response.raise_for_status()
                    result = response.json()
                    if (await self.tags()).get(model) != self.digests[model]:
                        raise ValueError("Model digest changed during generation")
                    if result.get("done_reason") == "length":
                        raise ValueError("Output token limit reached; no partial output accepted")
                    try:
                        raw = strip_think(result["message"]["content"])
                        return schema.model_validate(clean_strings(json.loads(raw)))
                    except (ValidationError, ValueError, KeyError):
                        continue
        raise ValueError("Malformed structured output after limited retries; nothing staged")


class MockProvider:
    """Deterministic offline responses; not an investment recommendation."""

    def __init__(self, config: Config):
        self.config = config
        self.digests = {
            getattr(config, a).model: "mock-sha256-v1" for a in ("analyst", "risk", "pm", "senior")
        }
        self.calls = []

    async def health(self):
        return None

    async def generate(self, agent, system, payload, schema):
        self.calls.append((agent, payload))
        results = {
            "analyst": {
                "assumptions": {
                    "wacc": 0.10,
                    "growth": 0.05,
                    "terminal_growth": 0.02,
                    "fcff_margin": 0.12,
                    "years": 5,
                },
                "narrative": "Revenue is {{data.revenue}}. Cash generation depends on "
                "the explicit margin assumption {{assumption.fcff_margin}}. "
                "This is a synthetic demonstration, with uncertain forecasts.",
            },
            "risk": {
                "verdict": "approve",
                "reasons": "Independent arithmetic reconciles. "
                "Terminal dependence and margin compression remain material risks. "
                "The base valuation is {{calc.fair_value}}.",
            },
            "pm": {
                "action": "buy",
                "weight": 0.05,
                "limit_price": payload.get("financials", {})
                .get("data", {})
                .get("price", {})
                .get("value", 100),
                "narrative": "Propose a limited paper allocation subject to cash and sector caps.",
            },
            "senior": {
                "verdict": "approve",
                "reasons": "Paper workflow reviewed; human review remains preferable.",
            },
        }
        return schema.model_validate(results[agent])
