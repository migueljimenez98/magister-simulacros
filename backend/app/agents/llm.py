"""Provider-agnostic LLM agent factory.

Every node that needs an LLM call goes through here. The trick is that any
endpoint that speaks the OpenAI Chat Completions wire format works as a drop-in
— OpenAI itself, Gemini via its OpenAI-compatible endpoint, vLLM serving
Gemma 3 locally, Anthropic via a translating proxy, etc. The factory takes
a config row (one per logical role: auditor, coach, composer) and returns a
ready-to-run `agents.Agent`.

LLMConfig rows live in the `llm_configs` table — change the model used by a
node with one UPDATE, no redeploy.

Falls back to settings.default_llm_* when no row exists for a name (useful
in dev / first boot before migrations are seeded).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from agents import Agent, ModelSettings, Runner
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from openai import AsyncOpenAI

from ..core.config import settings


@dataclass(frozen=True)
class LLMConfig:
    name: str                       # logical role: "auditor", "coach", "composer"
    provider: str                   # "openai" | "google" | "anthropic" | "vllm" | ...
    model: str                      # model id at the provider
    base_url: str | None = None     # OpenAI-compatible endpoint
    api_key: str | None = None
    # Bajado de 0.3 → 0.0 (2026-05-05): el auditor venía dando scores
    # inestables (1/5 vs 5/5 sobre el mismo input). Para una rúbrica con
    # cita literal obligatoria queremos máxima reproducibilidad. Si el
    # coach acaba demasiado robótico, sube SOLO el del coach a 0.2 vía
    # llm_configs (Fase 4) sin tocar este default.
    temperature: float = 0.0
    max_tokens: int | None = None


def _bootstrap_default(name: str) -> LLMConfig:
    return LLMConfig(
        name=name,
        provider=settings.default_llm_provider,
        model=settings.default_llm_model,
        base_url=settings.default_llm_base_url,
        api_key=settings.default_llm_api_key,
    )


# In-process cache. Reload by clearing this dict (or restarting the process)
# after editing llm_configs from the admin UI.
_clients: dict[str, AsyncOpenAI] = {}


def _client_for(cfg: LLMConfig) -> AsyncOpenAI:
    key = f"{cfg.base_url}|{cfg.api_key}"
    cli = _clients.get(key)
    if cli is None:
        cli = AsyncOpenAI(base_url=cfg.base_url, api_key=cfg.api_key)
        _clients[key] = cli
    return cli


def make_agent(
    cfg: LLMConfig,
    *,
    instructions: str,
    tools: list | None = None,
    output_type: type | None = None,
) -> Agent:
    """Build an Agents-SDK Agent bound to the configured provider.

    Pass `output_type` for structured output (Pydantic model) — recommended
    for the auditor so we get typed scores instead of parsing markdown.

    `cfg.temperature` and `cfg.max_tokens` get applied via `ModelSettings`
    so changes to the LLMConfig actually reach the API call (the previous
    version of this function silently ignored them, which is why bumping
    cfg.temperature did nothing — see the 2026-05-05 reproducibility fix).
    """
    client = _client_for(cfg)
    model = OpenAIChatCompletionsModel(model=cfg.model, openai_client=client)
    settings_kwargs: dict[str, Any] = {"temperature": cfg.temperature}
    if cfg.max_tokens is not None:
        settings_kwargs["max_tokens"] = cfg.max_tokens
    model_settings = ModelSettings(**settings_kwargs)
    kwargs: dict = {
        "name": cfg.name,
        "instructions": instructions,
        "model": model,
        "model_settings": model_settings,
    }
    if tools:
        kwargs["tools"] = tools
    if output_type is not None:
        kwargs["output_type"] = output_type
    return Agent(**kwargs)


async def load_config(name: str) -> LLMConfig:
    """Resolve an LLM config by logical name. TODO Fase 4: read from DB,
    fall back to bootstrap default if missing. For now always returns the
    bootstrap so the graph can run end-to-end against the default endpoint."""
    return _bootstrap_default(name)


# ── Process-wide LLM concurrency cap ────────────────────────────────────────
# Every score_param fans out N rules in parallel; with 25-30 rules per
# analysis × multiple analyses dispatched by the poller, OpenAI's TPM/RPM
# limits get blown easily. This semaphore caps how many LLM round-trips
# are in flight from this process. The poller's drip-dispatch cap (2
# concurrent analyses) and the CRM semaphore are independent — this one
# only governs Runner.run() calls.
#
# Tunable via env later; 8 in flight at OpenAI's default tier (~3500 RPM)
# leaves comfortable headroom even if every call takes 5s.
_LLM_CONCURRENCY = 8
_llm_semaphore: asyncio.Semaphore | None = None


def _get_llm_semaphore() -> asyncio.Semaphore:
    global _llm_semaphore
    if _llm_semaphore is None:
        _llm_semaphore = asyncio.Semaphore(_LLM_CONCURRENCY)
    return _llm_semaphore


async def bounded_run(agent: Agent, prompt: str) -> Any:
    """Drop-in replacement for `Runner.run(agent, prompt)` that respects
    the process-wide LLM concurrency cap. Use this from auditor / coach /
    composer instead of calling Runner.run directly."""
    sem = _get_llm_semaphore()
    async with sem:
        return await Runner.run(agent, prompt)
