from abc import ABC, abstractmethod
import json
import logging
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class AIProvider(ABC):
    @abstractmethod
    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        pass


class GroqProvider(AIProvider):
    def __init__(self):
        from groq import AsyncGroq
        settings = get_settings()
        self.client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        self.model = "qwen/qwen3.6-27b"

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=1000,
        )
        return response.choices[0].message.content


class MistralProvider(AIProvider):
    def __init__(self):
        from mistralai import Mistral
        settings = get_settings()
        self.client = Mistral(api_key=settings.MISTRAL_API_KEY)
        self.model = "open-mistral-7b"

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        response = await self.client.chat.complete_async(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=1000,
        )
        return response.choices[0].message.content


class AIProviderService:
    def __init__(self):
        self._providers = {}
        self._provider_order = []

    def _lazy_init(self, name: str) -> AIProvider:
        if name == "groq" and name not in self._providers:
            self._providers[name] = GroqProvider()
        elif name == "mistral" and name not in self._providers:
            self._providers[name] = MistralProvider()
        return self._providers.get(name)

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        primary: str = "mistral",
        fallback: str = "groq",
    ) -> dict:
        for provider_name in [primary, fallback]:
            try:
                provider = self._lazy_init(provider_name)
                if provider is None:
                    logger.warning(f"Provider {provider_name} not configured, skipping")
                    continue
                result = await provider.generate(system_prompt, user_prompt)
                return {"provider": provider_name, "response": result, "success": True}
            except Exception as e:
                logger.error(f"Provider {provider_name} failed: {e}")
                continue
        return {"provider": None, "response": None, "success": False, "error": "All providers failed"}


def parse_ai_signal_response(response_text: str) -> dict:
    try:
        text = response_text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            parts = text.split("```")
            if len(parts) >= 3:
                text = parts[1].strip()
                if text.startswith("json\n"):
                    text = text[5:]
                elif text.startswith("json"):
                    text = text[4:]
        return json.loads(text)
    except json.JSONDecodeError:
        for line in response_text.split("\n"):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return {"raw_response": response_text, "parse_error": True}
