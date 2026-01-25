"""
Patient Safety Monitor - LLM Client

Unified interface for LLM providers (Claude, OpenAI).
Handles API calls, retries, rate limiting, and cost tracking.

Usage:
    from analysis.llm_client import LLMClientFactory, LLMConfig
    
    config = LLMConfig(temperature=0.3, max_tokens=4096)
    client = LLMClientFactory.create_default()
    
    response = await client.complete(
        system_prompt="You are a medical analyst.",
        user_prompt="Analyze this finding...",
        config=config,
    )
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Type

from config.settings import get_settings


logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class LLMConfig:
    """Configuration for an LLM request."""
    
    temperature: float = 0.3
    max_tokens: int = 4096
    timeout_seconds: int = 120
    max_retries: int = 3
    
    # Stop sequences (optional)
    stop_sequences: list[str] = field(default_factory=list)
    
    # Response format hints
    json_mode: bool = False


@dataclass
class LLMResponse:
    """Response from an LLM call."""
    
    # Content
    content: str
    
    # Usage tracking
    tokens_input: int = 0
    tokens_output: int = 0
    
    # Cost tracking (in USD)
    cost_usd: float = 0.0
    
    # Metadata
    model: str = ""
    provider: str = ""
    latency_seconds: float = 0.0
    
    # Raw response for debugging
    raw_response: Optional[dict] = None
    
    @property
    def total_tokens(self) -> int:
        """Total tokens used."""
        return self.tokens_input + self.tokens_output


# =============================================================================
# Base Client
# =============================================================================

class BaseLLMClient(ABC):
    """
    Abstract base class for LLM clients.
    
    Provides:
        - Unified interface across providers
        - Retry logic with exponential backoff
        - Cost tracking
        - Request logging
    """
    
    # Cost per 1K tokens (input, output) - updated as needed
    COST_PER_1K_INPUT: float = 0.0
    COST_PER_1K_OUTPUT: float = 0.0
    
    def __init__(self, api_key: str, model: str):
        """
        Initialize the client.
        
        Args:
            api_key: API key for the provider
            model: Model identifier to use
        """
        self.api_key = api_key
        self.model = model
        self.logger = logging.getLogger(f"llm.{self.__class__.__name__}")
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name."""
        pass
    
    @abstractmethod
    async def _call_api(
        self,
        system_prompt: str,
        user_prompt: str,
        config: LLMConfig,
    ) -> dict:
        """
        Make the actual API call.
        
        Args:
            system_prompt: System message
            user_prompt: User message
            config: Request configuration
            
        Returns:
            Raw API response
        """
        pass
    
    @abstractmethod
    def _parse_response(self, raw_response: dict) -> tuple[str, int, int]:
        """
        Parse the API response.
        
        Args:
            raw_response: Raw API response
            
        Returns:
            Tuple of (content, input_tokens, output_tokens)
        """
        pass
    
    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        config: Optional[LLMConfig] = None,
    ) -> LLMResponse:
        """
        Complete a prompt with retries.
        
        Args:
            system_prompt: System message setting context
            user_prompt: User message with the actual request
            config: Optional request configuration
            
        Returns:
            LLMResponse with content and metadata
        """
        config = config or LLMConfig()
        start_time = time.time()
        
        self.logger.debug(
            "Starting LLM request",
            extra={
                "model": self.model,
                "temperature": config.temperature,
                "max_tokens": config.max_tokens,
            },
        )
        
        last_error: Optional[Exception] = None
        
        for attempt in range(config.max_retries):
            try:
                raw_response = await self._call_api(
                    system_prompt,
                    user_prompt,
                    config,
                )
                
                content, tokens_in, tokens_out = self._parse_response(raw_response)
                latency = time.time() - start_time
                
                # Calculate cost
                cost = self._calculate_cost(tokens_in, tokens_out)
                
                self.logger.info(
                    "LLM request completed",
                    extra={
                        "model": self.model,
                        "tokens_input": tokens_in,
                        "tokens_output": tokens_out,
                        "cost_usd": cost,
                        "latency_seconds": latency,
                    },
                )
                
                return LLMResponse(
                    content=content,
                    tokens_input=tokens_in,
                    tokens_output=tokens_out,
                    cost_usd=cost,
                    model=self.model,
                    provider=self.provider_name,
                    latency_seconds=latency,
                    raw_response=raw_response,
                )
                
            except Exception as e:
                last_error = e
                wait_time = 2 ** attempt
                
                self.logger.warning(
                    f"LLM request failed, attempt {attempt + 1}/{config.max_retries}",
                    extra={
                        "error": str(e),
                        "wait_seconds": wait_time,
                    },
                )
                
                if attempt < config.max_retries - 1:
                    await asyncio.sleep(wait_time)
        
        # All retries exhausted
        self.logger.error(
            "LLM request failed after all retries",
            extra={"error": str(last_error)},
        )
        raise last_error
    
    def _calculate_cost(self, tokens_input: int, tokens_output: int) -> float:
        """Calculate cost in USD."""
        input_cost = (tokens_input / 1000) * self.COST_PER_1K_INPUT
        output_cost = (tokens_output / 1000) * self.COST_PER_1K_OUTPUT
        return round(input_cost + output_cost, 6)


# =============================================================================
# Claude Client
# =============================================================================

class ClaudeClient(BaseLLMClient):
    """
    Client for Anthropic's Claude API.
    
    Uses the official Anthropic Python SDK.
    """
    
    # Claude Sonnet 4 pricing (as of Jan 2026)
    COST_PER_1K_INPUT = 0.003
    COST_PER_1K_OUTPUT = 0.015
    
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        """
        Initialize Claude client.
        
        Args:
            api_key: Anthropic API key
            model: Model to use (default: claude-sonnet-4)
        """
        super().__init__(api_key, model)
        self._client = None
    
    @property
    def provider_name(self) -> str:
        return "claude"
    
    def _get_client(self):
        """Get or create the Anthropic client."""
        if self._client is None:
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
        return self._client
    
    async def _call_api(
        self,
        system_prompt: str,
        user_prompt: str,
        config: LLMConfig,
    ) -> dict:
        """Make Claude API call."""
        client = self._get_client()
        
        response = await client.messages.create(
            model=self.model,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ],
            timeout=config.timeout_seconds,
        )
        
        return response.model_dump()
    
    def _parse_response(self, raw_response: dict) -> tuple[str, int, int]:
        """Parse Claude response."""
        content = ""
        for block in raw_response.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")
        
        usage = raw_response.get("usage", {})
        tokens_input = usage.get("input_tokens", 0)
        tokens_output = usage.get("output_tokens", 0)
        
        return content, tokens_input, tokens_output


# =============================================================================
# OpenAI Client
# =============================================================================

class OpenAIClient(BaseLLMClient):
    """
    Client for OpenAI's API.
    
    Uses the official OpenAI Python SDK.
    """
    
    # GPT-5 pricing (placeholder - update as needed)
    COST_PER_1K_INPUT = 0.01
    COST_PER_1K_OUTPUT = 0.03
    
    def __init__(self, api_key: str, model: str = "gpt-5-turbo"):
        """
        Initialize OpenAI client.
        
        Args:
            api_key: OpenAI API key
            model: Model to use (default: gpt-5-turbo)
        """
        super().__init__(api_key, model)
        self._client = None
    
    @property
    def provider_name(self) -> str:
        return "openai"
    
    def _get_client(self):
        """Get or create the OpenAI client."""
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=self.api_key)
        return self._client
    
    async def _call_api(
        self,
        system_prompt: str,
        user_prompt: str,
        config: LLMConfig,
    ) -> dict:
        """Make OpenAI API call."""
        client = self._get_client()
        
        kwargs = {
            "model": self.model,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "timeout": config.timeout_seconds,
        }
        
        if config.json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        
        response = await client.chat.completions.create(**kwargs)
        
        return response.model_dump()
    
    def _parse_response(self, raw_response: dict) -> tuple[str, int, int]:
        """Parse OpenAI response."""
        choices = raw_response.get("choices", [])
        content = ""
        if choices:
            content = choices[0].get("message", {}).get("content", "")
        
        usage = raw_response.get("usage", {})
        tokens_input = usage.get("prompt_tokens", 0)
        tokens_output = usage.get("completion_tokens", 0)
        
        return content, tokens_input, tokens_output


# =============================================================================
# Factory
# =============================================================================

class LLMClientFactory:
    """
    Factory for creating LLM clients.
    
    Creates clients based on configuration settings.
    """
    
    _clients: dict[str, Type[BaseLLMClient]] = {
        "claude": ClaudeClient,
        "openai": OpenAIClient,
    }
    
    @classmethod
    def create(
        cls,
        provider: str,
        api_key: str,
        model: Optional[str] = None,
    ) -> BaseLLMClient:
        """
        Create an LLM client.
        
        Args:
            provider: Provider name (claude or openai)
            api_key: API key
            model: Optional model override
            
        Returns:
            Configured client instance
        """
        provider = provider.lower()
        if provider not in cls._clients:
            raise ValueError(f"Unknown provider: {provider}")
        
        client_class = cls._clients[provider]
        
        if model:
            return client_class(api_key, model)
        return client_class(api_key)
    
    @classmethod
    def create_default(cls) -> BaseLLMClient:
        """
        Create the default client from settings.
        
        Uses the primary provider configured in settings,
        falling back to secondary if primary is unavailable.
        
        Returns:
            Configured client instance
        """
        settings = get_settings()
        
        # Try primary provider
        if settings.llm_primary_provider == "claude" and settings.anthropic_api_key:
            return cls.create(
                "claude",
                settings.anthropic_api_key,
                settings.llm_primary_model,
            )
        
        if settings.llm_primary_provider == "openai" and settings.openai_api_key:
            return cls.create(
                "openai",
                settings.openai_api_key,
                settings.llm_primary_model,
            )
        
        # Fallback
        if settings.anthropic_api_key:
            return cls.create("claude", settings.anthropic_api_key)
        
        if settings.openai_api_key:
            return cls.create("openai", settings.openai_api_key)
        
        raise ValueError("No LLM API keys configured")
    
    @classmethod
    def create_fallback(cls) -> Optional[BaseLLMClient]:
        """
        Create a fallback client for when primary fails.
        
        Returns:
            Fallback client or None if unavailable
        """
        settings = get_settings()
        
        # If primary is Claude, fallback to OpenAI
        if settings.llm_primary_provider == "claude" and settings.openai_api_key:
            return cls.create(
                "openai",
                settings.openai_api_key,
                settings.llm_fallback_model,
            )
        
        # If primary is OpenAI, fallback to Claude
        if settings.llm_primary_provider == "openai" and settings.anthropic_api_key:
            return cls.create(
                "claude",
                settings.anthropic_api_key,
            )
        
        return None


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    "BaseLLMClient",
    "ClaudeClient",
    "OpenAIClient",
    "LLMClientFactory",
    "LLMConfig",
    "LLMResponse",
]
