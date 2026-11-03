"""Provider-agnostic worker backend for Sluice.

One small client speaking OpenAI-compatible chat completions. No platform,
no server, no telemetry. Keys come from environment only, never from the
repo, never from a file in the repo.

Configuration (environment):
  SLUICE_BASE_URL   OpenAI-compatible base URL, e.g. http://localhost:11434/v1
  SLUICE_MODEL      Model id to call, e.g. a mini-class model id, or a
                    Meta contributor-tier id. No default is guessed: if
                    SLUICE_MODEL is unset, this module refuses to call.
  SLUICE_API_KEY    API key. Provider fallbacks, in order, are checked
                    only if SLUICE_API_KEY is unset:
                      OPENAI_API_KEY, GEMINI_API_KEY, GOOGLE_API_KEY,
                      META_MODEL_API_KEY
  SLUICE_PROVIDER   Informational only (openai, gemini, ollama, meta,
                    custom). It selects the base-URL fallback when
                    SLUICE_BASE_URL is unset, except for meta/custom,
                    where the base URL must be set explicitly because
                    this tool does not guess a provider endpoint.
  SLUICE_PRICE_INPUT_PER_1M / SLUICE_PRICE_OUTPUT_PER_1M
                    Optional prices in dollars per 1M tokens. If unset,
                    worker dollars are None (unknown), never 0. A caller
                    that knows its provider's rates (for example the
                    Meta contributor tier at $0.10 input / $0.20 output
                    per 1M tokens, as documented in the README) sets
                    these explicitly.
  SLUICE_API_STYLE    "chat" (default, OpenAI-compatible chat
                    completions) or "responses" (Responses API shape,
                    as used by the Meta Model API: POST {base}/responses
                    with input messages and output_text parts).
  SLUICE_MAX_OUTPUT_TOKENS
                    Optional output cap. Set for live runs so a runaway
                    summary cannot blow a budget cap.

This module uses only the Python standard library, so the plugin has no
pip dependencies to install.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

PROVIDER_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "ollama": "http://localhost:11434/v1",
    # "meta" and "custom" deliberately have no guessed base URL.
}

PROVIDER_KEY_VARS = {
    "openai": ("OPENAI_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "ollama": (),
    "meta": ("META_MODEL_API_KEY",),
    "custom": (),
}

BULK_READ_SYSTEM = (
    "You are a file summarizer for a coding agent. Answer ONLY the question "
    "asked, from ONLY the files given. Output structured bullets. Put exact "
    "names, types, and line numbers first. Include nothing unasked: no full "
    "file dumps, no unrelated code, no explanation of your process. If the "
    "question cannot be answered from the files, say so in one line and "
    "stop. Never invent an identifier, a type, or a line number."
)

CODE_WRITE_SYSTEM = (
    "You are a code writer for a coding agent. Output code ONLY: no prose, "
    "no explanation, no markdown fences, no commentary before or after the "
    "code. The code will be written straight to disk and the coordinator "
    "will never see it, so it must be complete and self-contained for the "
    "spec and reference given. Do not debug, do not make architecture "
    "decisions, do not write safety-critical code, and do not edit based "
    "on a summary: if the spec or reference is insufficient, output a "
    "single comment line stating what is missing instead of guessing."
)

EXCLUSIONS = (
    "no debugging, no architecture decisions, no safety-critical code, "
    "no edits based on summaries"
)


class WorkerError(Exception):
    """Raised when the worker cannot be configured or the call fails."""


def resolve_config() -> dict:
    provider = (os.environ.get("SLUICE_PROVIDER") or "custom").strip().lower()
    base_url = os.environ.get("SLUICE_BASE_URL")
    if not base_url:
        base_url = PROVIDER_BASE_URLS.get(provider)
    model = os.environ.get("SLUICE_MODEL")
    if not base_url:
        raise WorkerError(
            "SLUICE_BASE_URL is not set and provider "
            f"'{provider}' has no built-in base URL. Set SLUICE_BASE_URL "
            "explicitly (for a Meta contributor-tier worker, set it to "
            "your provider's OpenAI-compatible endpoint)."
        )
    if not model:
        raise WorkerError(
            "SLUICE_MODEL is not set. Set it to the worker model id you "
            "want to pay for (for example a mini-class model, Gemini "
            "Flash, a local Ollama model, or a Meta contributor-tier id)."
        )
    api_key = os.environ.get("SLUICE_API_KEY")
    if not api_key:
        for var in PROVIDER_KEY_VARS.get(provider, ()):
            api_key = os.environ.get(var)
            if api_key:
                break
    if not api_key and provider not in ("ollama",):
        # Ollama on localhost normally needs no key; everything else does.
        # Fall back to the generic vars before refusing, so a user with
        # only META_MODEL_API_KEY set and SLUICE_PROVIDER unset still works.
        for var in ("OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "META_MODEL_API_KEY"):
            api_key = os.environ.get(var)
            if api_key:
                break
    if not api_key and provider != "ollama":
        raise WorkerError(
            "No worker API key found. Set SLUICE_API_KEY (or the "
            "provider's key variable) in the environment. Keys are never "
            "read from the repo."
        )
    price_in = os.environ.get("SLUICE_PRICE_INPUT_PER_1M")
    price_out = os.environ.get("SLUICE_PRICE_OUTPUT_PER_1M")
    api_style = (os.environ.get("SLUICE_API_STYLE") or "chat").strip().lower()
    if api_style not in ("chat", "responses"):
        raise WorkerError(f"SLUICE_API_STYLE must be 'chat' or 'responses', got '{api_style}'.")
    max_out = os.environ.get("SLUICE_MAX_OUTPUT_TOKENS")
    return {
        "provider": provider,
        "base_url": base_url.rstrip("/"),
        "model": model,
        "api_key": api_key or "",
        "price_input_per_1m": float(price_in) if price_in else None,
        "price_output_per_1m": float(price_out) if price_out else None,
        "api_style": api_style,
        "max_output_tokens": int(max_out) if max_out else None,
    }


def call_worker(system: str, user: str, *, config: dict | None = None, timeout: int = 120) -> dict:
    """Call the configured worker. Returns text + measured usage.

    The returned token counts come from the provider's `usage` field:
    they are measured, not estimated. Dollars are computed only when
    prices were supplied; otherwise dollars is None (unknown).
    """
    cfg = config or resolve_config()
    if cfg.get("api_style") == "responses":
        body_in = {
            "model": cfg["model"],
            "input": [
                {"type": "message", "role": "system", "content": [{"type": "input_text", "text": system}]},
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": user}]},
            ],
            "stream": False,
            "temperature": 0,
            "reasoning": {"effort": "low"},
        }
        if cfg.get("max_output_tokens"):
            body_in["max_output_tokens"] = cfg["max_output_tokens"]
        endpoint = cfg["base_url"] + "/responses"
    else:
        body_in = {
            "model": cfg["model"],
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
        }
        if cfg.get("max_output_tokens"):
            body_in["max_tokens"] = cfg["max_output_tokens"]
        endpoint = cfg["base_url"] + "/chat/completions"
    payload = json.dumps(body_in).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg['api_key']}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise WorkerError(f"Worker HTTP {exc.code}: {detail}") from exc
    except OSError as exc:
        raise WorkerError(f"Worker request failed: {exc}") from exc
    if cfg.get("api_style") == "responses":
        parts = []
        for item in body.get("output") or []:
            for part in item.get("content") or []:
                if part.get("type") == "output_text" and part.get("text"):
                    parts.append(part["text"])
        text = "".join(parts).strip()
        if not text:
            raise WorkerError(f"Unexpected worker response shape: {str(body)[:500]}")
    else:
        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise WorkerError(f"Unexpected worker response shape: {str(body)[:500]}") from exc
    usage = body.get("usage") or {}
    # Chat completions use prompt/completion tokens; the Responses API
    # uses input/output tokens for the same quantities. Normalise both
    # here, otherwise a Responses call reports null usage (a bug found
    # in the first live run, where summaries were correct but worker
    # tokens and dollars came back null).
    prompt_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
    completion_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
    if not isinstance(prompt_tokens, int):
        prompt_tokens = None
    if not isinstance(completion_tokens, int):
        completion_tokens = None
    worker_tokens = None
    if isinstance(prompt_tokens, int) and isinstance(completion_tokens, int):
        worker_tokens = prompt_tokens + completion_tokens
    dollars = None
    if (
        isinstance(prompt_tokens, int)
        and isinstance(completion_tokens, int)
        and cfg["price_input_per_1m"] is not None
        and cfg["price_output_per_1m"] is not None
    ):
        dollars = (
            prompt_tokens * cfg["price_input_per_1m"] / 1_000_000
            + completion_tokens * cfg["price_output_per_1m"] / 1_000_000
        )
    return {
        "text": text,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "worker_tokens": worker_tokens,
        "worker_dollars": dollars,
        "model": cfg["model"],
        "provider": cfg["provider"],
        "api_style": cfg.get("api_style", "chat"),
    }
