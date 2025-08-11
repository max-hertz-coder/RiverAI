import asyncio
import logging
import random
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI
from worker import config

logger = logging.getLogger(__name__)

_PREFERRED_MODELS: List[str] = ["gpt-5", "gpt-5-mini", "gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]


def _pick_key() -> str:
    if not config.OPENAI_API_KEYS:
        raise RuntimeError("OPENAI_API_KEYS не настроены")
    key = random.choice(config.OPENAI_API_KEYS).strip()
    if not key or len(key) < 10:
        raise RuntimeError("Недействительный OpenAI ключ")
    logger.info("🔧 Выбран OpenAI ключ: ****%s (из %d)", key[-4:], len(config.OPENAI_API_KEYS))
    return key


async def _call_chat_completion(
    client: AsyncOpenAI,
    messages: List[Dict[str, str]],
    model: str,
    temperature: float,
    max_tokens: int,
) -> Dict[str, Any]:
    resp = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    text = (resp.choices[0].message.content or "").strip()
    usage = resp.usage or None
    return {
        "text": text,
        "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
        "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
    }


async def chat_with_gpt(
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 1000,
    model: Optional[str] = None,
    max_retries: int = 3,
) -> Dict[str, Any]:
    if not messages:
        raise ValueError("messages пуст")

    models_chain = [model] + _PREFERRED_MODELS if model else list(_PREFERRED_MODELS)

    last_exc: Optional[Exception] = None
    for mdl in models_chain:
        if not mdl:
            continue
        for attempt in range(1, max_retries + 1):
            key = _pick_key()
            client = AsyncOpenAI(api_key=key)
            try:
                logger.info("🧠 GPT call: model=%s, attempt=%d/%d, last_user='%s...'",
                            mdl, attempt, max_retries, (messages[-1].get("content") or "")[:60])
                result = await _call_chat_completion(client, messages, mdl, temperature, max_tokens)
                logger.info(
                    "✅ GPT ok (model=%s) tokens: prompt=%d, completion=%d, total=%d",
                    mdl, result["prompt_tokens"], result["completion_tokens"], result["total_tokens"]
                )
                return result
            except Exception as e:
                last_exc = e
                delay = min(2 ** (attempt - 1), 8) + random.uniform(0, 0.5)
                logger.warning("⚠️ GPT error (model=%s, attempt=%d): %s; retry in %.1fs", mdl, attempt, e, delay)
                await asyncio.sleep(delay)
                continue

        logger.warning("↪️ Переключаюсь на модель пониженного приоритета: %s", mdl)

    logger.exception("🔴 Все попытки вызова GPT исчерпаны")
    if last_exc:
        raise last_exc
    raise RuntimeError("Не удалось получить ответ от GPT")