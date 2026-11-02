import asyncio
import json

import httpx
import pytest

from workstation.config import Config
from workstation.llm import OllamaProvider, strip_think
from workstation.schemas import RiskOutput


def fixture_transport(contents=None, models=None):
    calls = []
    outputs = iter(contents or ['{"verdict":"approve","reasons":"Sound qualitative evidence"}'])

    def handle(request):
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": models
                    if models is not None
                    else [
                        {"name": "llama3.1:8b", "digest": "abc"},
                        {"name": "qwen2.5:7b", "digest": "def"},
                    ]
                },
            )
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"done": True, "message": {"content": next(outputs)}})

    return httpx.MockTransport(handle), calls


def invoke(config=None, contents=None, payload=None):
    transport, calls = fixture_transport(contents)
    provider = OllamaProvider(config or Config(), transport=transport)

    async def run():
        await provider.health()
        return await provider.generate("risk", "Review supplied data", payload or {}, RiskOutput)

    return asyncio.run(run()), calls


def test_ollama_contract_and_think_removal():
    result, calls = invoke(
        contents=[
            '<think>private chain</think>{"verdict":"approve",'
            '"reasons":"<think>secret</think>Evidence reconciles"}'
        ]
    )
    assert result.reasons == "Evidence reconciles"
    assert calls[0]["options"] == {
        "num_ctx": 16384,
        "temperature": 0,
        "seed": 42,
        "num_predict": 1536,
    }
    assert calls[0]["format"] == RiskOutput.model_json_schema()
    assert calls[0]["keep_alive"] == "5m"
    assert len(calls[0]["messages"]) == 2


@pytest.mark.parametrize("text", ["<think>unfinished", "content </think>"])
def test_malformed_reasoning_rejected(text):
    with pytest.raises(ValueError, match="Unclosed"):
        strip_think(text)


def test_context_overflow():
    with pytest.raises(ValueError, match="num_ctx"):
        invoke(config=Config(num_ctx=512), payload={"filing": "x" * 2000})


def test_output_retry_and_exhaustion():
    result, calls = invoke(contents=["not json", '{"verdict":"approve","reasons":"Checked"}'])
    assert result.verdict == "approve" and len(calls) == 2
    with pytest.raises(ValueError, match="Malformed structured"):
        invoke(contents=["no", "no", "no"])


def test_budget():
    with pytest.raises(ValueError, match="Token budget"):
        invoke(config=Config(token_budget=128))


def test_missing_models_exact_commands():
    transport, _ = fixture_transport(models=[])
    with pytest.raises(ValueError, match="ollama pull llama3.1:8b"):
        asyncio.run(OllamaProvider(Config(), transport).health())


def test_unreachable_server_clean_error():
    def unavailable(request):
        raise httpx.ConnectError("offline")

    with pytest.raises(ValueError, match="ollama serve"):
        asyncio.run(OllamaProvider(Config(), httpx.MockTransport(unavailable)).health())


def test_wall_clock_budget():
    transport, _ = fixture_transport()
    p = OllamaProvider(Config(), transport)
    p.deadline = 0
    with pytest.raises(ValueError, match="Wall-clock"):
        asyncio.run(p.generate("risk", "review", {}, RiskOutput))


def test_digest_change_fails_closed():
    transport, _ = fixture_transport()
    p = OllamaProvider(Config(), transport)

    async def run():
        await p.health()
        p.digests["qwen2.5:7b"] = "old-digest"
        await p.generate("risk", "review", {}, RiskOutput)

    with pytest.raises(ValueError, match="digest changed"):
        asyncio.run(run())
