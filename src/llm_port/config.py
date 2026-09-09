"""Provider selection and client configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .errors import ConfigurationError

__all__ = ["Provider", "LLMConfig", "RetryPolicy"]


class Provider(StrEnum):
    """Supported provider adapters."""

    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    SARVAM = "sarvam"
    OPENAI = "openai"
    OLLAMA = "ollama"
    LMSTUDIO = "lmstudio"


#: Default endpoint per provider. ``LLMConfig.base_url`` overrides these.
DEFAULT_BASE_URLS: dict[Provider, str] = {
    Provider.ANTHROPIC: "https://api.anthropic.com/v1",
    Provider.GEMINI: "https://generativelanguage.googleapis.com/v1beta",
    Provider.SARVAM: "https://api.sarvam.ai/v1",
    Provider.OPENAI: "https://api.openai.com/v1",
    Provider.OLLAMA: "http://localhost:11434/v1",
    Provider.LMSTUDIO: "http://localhost:1234/v1",
}

#: Environment variable consulted for each provider's credential.
DEFAULT_API_KEY_ENV: dict[Provider, str] = {
    Provider.ANTHROPIC: "ANTHROPIC_API_KEY",
    Provider.GEMINI: "GEMINI_API_KEY",
    Provider.SARVAM: "SARVAM_API_KEY",
    Provider.OPENAI: "OPENAI_API_KEY",
    Provider.OLLAMA: "OLLAMA_API_KEY",
    Provider.LMSTUDIO: "LMSTUDIO_API_KEY",
}

#: Providers that run locally and therefore need no credential.
LOCAL_PROVIDERS = frozenset({Provider.OLLAMA, Provider.LMSTUDIO})


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Bounded retry behavior for transport and 429/5xx failures.

    Attributes:
        max_attempts: Total attempts including the first. ``1`` disables retries.
        initial_backoff: Seconds to wait before the second attempt.
        backoff_multiplier: Growth factor applied to each subsequent wait.
        max_backoff: Ceiling on any single wait.
        jitter: Fraction of each wait randomized, to spread retry storms.
    """

    max_attempts: int = 3
    initial_backoff: float = 0.5
    backoff_multiplier: float = 2.0
    max_backoff: float = 30.0
    jitter: float = 0.2

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ConfigurationError("max_attempts must be at least 1")
        if not 0.0 <= self.jitter <= 1.0:
            raise ConfigurationError("jitter must be between 0.0 and 1.0")


@dataclass(frozen=True, slots=True)
class LLMConfig:
    """Everything the client needs to talk to one model.

    Attributes:
        provider: Which adapter to use.
        model_name: Provider-specific model identifier.
        api_key: Credential. Falls back to the provider's environment variable.
        base_url: Endpoint override, required for non-default local ports.
        timeout: Per-request timeout in seconds.
        max_tokens: Cap on generated tokens.
        temperature: Sampling temperature, or ``None`` for the provider default.
        top_p: Nucleus sampling cutoff, or ``None`` for the provider default.
        stop: Stop sequences.
        retry: Transport-level retry policy.
        tool_repair_attempts: How many corrective round trips the conformance
            layer may spend fixing an invalid tool call before raising.
        recover_text_tool_calls: Parse tool calls out of plain text when the
            provider emitted none structurally.
        strict_tools: Reject tool calls that violate their declared schema
            instead of passing them through unvalidated.
        constrained_decoding: Ask the provider to enforce the tool schema during
            decoding where supported. Ignored by providers that cannot.
        extra_headers: Additional headers merged into every request.
        extra_body: Additional top-level fields merged into every request body.
    """

    provider: Provider
    model_name: str
    api_key: str | None = None
    base_url: str | None = None
    timeout: float = 60.0
    max_tokens: int = 4096
    temperature: float | None = None
    top_p: float | None = None
    stop: tuple[str, ...] = ()
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    tool_repair_attempts: int = 1
    recover_text_tool_calls: bool = True
    strict_tools: bool = True
    constrained_decoding: bool = False
    extra_headers: dict[str, str] = field(default_factory=dict)
    extra_body: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.model_name:
            raise ConfigurationError("model_name is required")
        if self.max_tokens < 1:
            raise ConfigurationError("max_tokens must be positive")
        if self.timeout <= 0:
            raise ConfigurationError("timeout must be positive")
        if self.tool_repair_attempts < 0:
            raise ConfigurationError("tool_repair_attempts cannot be negative")

    @property
    def resolved_base_url(self) -> str:
        return (self.base_url or DEFAULT_BASE_URLS[self.provider]).rstrip("/")

    def resolve_api_key(self) -> str | None:
        """Return the credential, reading the environment when none was given.

        Local providers may legitimately have no credential; hosted providers
        raise :class:`ConfigurationError` when none can be found.
        """
        key = self.api_key or os.environ.get(DEFAULT_API_KEY_ENV[self.provider])
        if not key and self.provider not in LOCAL_PROVIDERS:
            raise ConfigurationError(
                f"no API key for {self.provider}: pass api_key= or set "
                f"{DEFAULT_API_KEY_ENV[self.provider]}"
            )
        return key
