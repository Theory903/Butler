"""LangChain AI SDK adapter for unified provider abstraction."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, AsyncIterator
from dataclasses import dataclass
from pydantic import SecretStr

from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
try:
    from langchain_google_vertexai import ChatVertexAI
except ImportError:
    ChatVertexAI = None  # Optional dependency
try:
    from langchain_groq import ChatGroq
except ImportError:
    ChatGroq = None  # Optional dependency
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from .openclaw_layer.provider_registry import ProviderRegistry, ProviderSpec
from .openclaw_layer.credential_pool import CredentialPool, Credential
from .openclaw_layer.observability import (
    ProviderObservability,
    log_provider_request,
    log_provider_response,
)
from .openclaw_layer.cost_tracker import CostTracker


@dataclass
class LangChainAdapterConfig:
    """Configuration for the LangChain adapter."""
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: int = 120


class LangChainProviderAdapter:
    """Adapter for creating LangChain models from provider specs and credentials."""
    
    def __init__(
        self,
        provider_registry: ProviderRegistry,
        credential_pool: CredentialPool,
        observability: Optional[ProviderObservability] = None,
        cost_tracker: Optional[CostTracker] = None,
        config: LangChainAdapterConfig = LangChainAdapterConfig(),
    ):
        self.provider_registry = provider_registry
        self.credential_pool = credential_pool
        self.observability = observability or ProviderObservability()
        self.cost_tracker = cost_tracker or CostTracker()
        self.config = config
    
    def create_langchain_model(
        self,
        provider_name: str,
        model: Optional[str] = None,
        credential: Optional[Credential] = None,
    ) -> BaseChatModel:
        """Create a LangChain model instance for the given provider."""
        provider_spec = self.provider_registry.get_provider(provider_name)
        if not provider_spec:
            raise ValueError(f"Provider not found: {provider_name}")
        
        model_name = model or provider_spec.default_model
        if not model_name:
            raise ValueError(f"No model specified and no default model for provider: {provider_name}")
        
        api_key = SecretStr(credential.key) if credential and credential.key else None
        
        # Create model based on provider type
        if "openai" in provider_name.lower() or "gpt" in provider_name.lower():
            return ChatOpenAI(
                model=model_name,
                api_key=api_key,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                timeout=self.config.timeout,
            )
        elif "anthropic" in provider_name.lower() or "claude" in provider_name.lower():
            return ChatAnthropic(
                model_name=model_name,
                api_key=api_key or None,
                temperature=self.config.temperature,
                max_tokens_to_sample=self.config.max_tokens,
                timeout=self.config.timeout,
                stop=None,
            )
        elif "groq" in provider_name.lower():
            if ChatGroq is None:
                raise ValueError("langchain-groq not installed")
            return ChatGroq(
                model=model_name,
                api_key=api_key,
                temperature=self.config.temperature,
                timeout=self.config.timeout,
            )
        elif "vertex" in provider_name.lower() or "gemini" in provider_name.lower():
            if ChatVertexAI is None:
                raise ValueError("langchain-google-vertexai not installed")
            # Vertex AI uses Google Cloud credentials, not API key
            return ChatVertexAI(
                model=model_name,
                temperature=self.config.temperature,
                max_output_tokens=self.config.max_tokens,
                timeout=self.config.timeout,
            )
        else:
            raise ValueError(f"Unsupported provider: {provider_name}")
    
    async def execute_generate_text(
        self,
        provider_name: str,
        prompt: str,
        model: Optional[str] = None,
        system_message: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Execute a text generation request using LangChain."""
        # Get credential from pool
        credential = self.credential_pool.get_next_credential(provider_name)
        
        # Log request start
        metrics = log_provider_request(
            provider=provider_name,
            model=model or "unknown",
            credential_id=credential.id if credential else None,
            observability=self.observability,
        )
        
        try:
            # Create LangChain model
            langchain_model = self.create_langchain_model(
                provider_name,
                model,
                credential,
            )
            
            # Build messages
            messages: List[BaseMessage] = []
            if system_message:
                messages.append(SystemMessage(content=system_message))
            messages.append(HumanMessage(content=prompt))
            
            # Execute request
            response = await langchain_model.ainvoke(messages)
            
            # Extract text
            result = response.content if hasattr(response, 'content') else str(response)
            if isinstance(result, list):
                result = "".join(str(item) for item in result)
            
            # Mark credential success
            if credential:
                self.credential_pool.mark_credential_success(credential.id)
            
            # Track cost (placeholder - LangChain doesn't provide token counts directly)
            if self.cost_tracker.enabled:
                self.cost_tracker.track_request(
                    provider=provider_name,
                    model=model or "unknown",
                    input_tokens=len(prompt.split()),
                    output_tokens=len(result.split()),
                    credential_id=credential.id if credential else None,
                )
            
            # Log response
            log_provider_response(
                metrics=metrics,
                success=True,
                input_tokens=len(prompt.split()),
                output_tokens=len(result.split()),
                observability=self.observability,
            )
            
            return result
            
        except Exception as e:
            # Mark credential failure
            if credential:
                self.credential_pool.mark_credential_failed(credential.id)
            
            # Log error
            log_provider_response(
                metrics=metrics,
                success=False,
                error_message=str(e),
                observability=self.observability,
            )
            
            raise
    
    async def execute_stream_text(
        self,
        provider_name: str,
        prompt: str,
        model: Optional[str] = None,
        system_message: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """Execute a streaming text generation request using LangChain."""
        # Get credential from pool
        credential = self.credential_pool.get_next_credential(provider_name)
        
        # Log request start
        metrics = log_provider_request(
            provider=provider_name,
            model=model or "unknown",
            credential_id=credential.id if credential else None,
            observability=self.observability,
        )
        
        try:
            # Create LangChain model directly with streaming
            provider_spec = self.provider_registry.get_provider(provider_name)
            if not provider_spec:
                raise ValueError(f"Provider not found: {provider_name}")
            
            model_name = model or provider_spec.default_model
            if not model_name:
                raise ValueError(f"No model specified and no default model for provider: {provider_name}")
            
            api_key = SecretStr(credential.key) if credential and credential.key else None
            
            # Create model based on provider type with streaming enabled
            if "openai" in provider_name.lower() or "gpt" in provider_name.lower():
                langchain_model = ChatOpenAI(
                    model=model_name,
                    api_key=api_key,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                    timeout=self.config.timeout,
                    streaming=True,
                )
            elif "anthropic" in provider_name.lower() or "claude" in provider_name.lower():
                langchain_model = ChatAnthropic(
                    model_name=model_name,
                    api_key=api_key,
                    temperature=self.config.temperature,
                    max_tokens_to_sample=self.config.max_tokens,
                    timeout=self.config.timeout,
                    stop=None,
                )
            elif "groq" in provider_name.lower():
                if ChatGroq is None:
                    raise ValueError("langchain-groq not installed")
                langchain_model = ChatGroq(
                    model=model_name,
                    api_key=api_key,
                    temperature=self.config.temperature,
                    timeout=self.config.timeout,
                )
            elif "vertex" in provider_name.lower() or "gemini" in provider_name.lower():
                if ChatVertexAI is None:
                    raise ValueError("langchain-google-vertexai not installed")
                langchain_model = ChatVertexAI(
                    model=model_name,
                    temperature=self.config.temperature,
                    max_output_tokens=self.config.max_tokens,
                    timeout=self.config.timeout,
                )
            else:
                raise ValueError(f"Unsupported provider: {provider_name}")
            
            # Build messages
            messages: List[BaseMessage] = []
            if system_message:
                messages.append(SystemMessage(content=system_message))
            messages.append(HumanMessage(content=prompt))
            
            # Stream response
            full_response = ""
            async for chunk in langchain_model.astream(messages):
                chunk_text = chunk.content if hasattr(chunk, 'content') else str(chunk)
                if isinstance(chunk_text, list):
                    chunk_text = "".join(str(item) for item in chunk_text)
                full_response += chunk_text
                yield chunk_text
            
            # Mark credential success
            if credential:
                self.credential_pool.mark_credential_success(credential.id)
            
            # Track cost
            if self.cost_tracker.enabled:
                self.cost_tracker.track_request(
                    provider=provider_name,
                    model=model or "unknown",
                    input_tokens=len(prompt.split()),
                    output_tokens=len(full_response.split()),
                    credential_id=credential.id if credential else None,
                )
            
            # Log response
            log_provider_response(
                metrics=metrics,
                success=True,
                input_tokens=len(prompt.split()),
                output_tokens=len(full_response.split()),
                observability=self.observability,
            )
            
        except Exception as e:
            # Mark credential failure
            if credential:
                self.credential_pool.mark_credential_failed(credential.id)
            
            # Log error
            log_provider_response(
                metrics=metrics,
                success=False,
                error_message=str(e),
                observability=self.observability,
            )
            
            raise


def create_langchain_adapter(
    provider_registry: Optional[ProviderRegistry] = None,
    credential_pool: Optional[CredentialPool] = None,
    observability: Optional[ProviderObservability] = None,
    cost_tracker: Optional[CostTracker] = None,
    config: Optional[LangChainAdapterConfig] = None,
) -> LangChainProviderAdapter:
    """Create a LangChain adapter with default components."""
    from .openclaw_layer.provider_registry import create_default_registry
    
    return LangChainProviderAdapter(
        provider_registry=provider_registry or create_default_registry(),
        credential_pool=credential_pool or CredentialPool(),
        observability=observability,
        cost_tracker=cost_tracker,
        config=config or LangChainAdapterConfig(),
    )
