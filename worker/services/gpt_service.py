# worker/services/gpt_service.py
from __future__ import annotations

import asyncio
import logging
import os
import random
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI
from worker import config

logger = logging.getLogger(__name__)

# Приоритет моделей для генерации школьных заданий (без gpt-3.5)
PREFERRED_MODELS: List[str] = [
    "gpt-5-turbo",   # быстрый и сильный (если доступен)
    "gpt-4-turbo",   # быстрый 4-й
    "gpt-5",         # fallback: требует max_completion_tokens/temperature=1.0
    "gpt-5-mini",    # ещё один fallback
    "gpt-4o",        # универсальный vision/текст
]

def _collect_keys() -> List[str]:
    """
    Сбор API-ключей из:
      - config.OPENAI_API_KEYS (list/iterable)
      - config.OPENAI_API_KEY
      - переменных окружения OPENAI_API_KEYS / OPENAI_API_KEY
    """
    keys: List[str] = []

    if hasattr(config, "OPENAI_API_KEYS") and config.OPENAI_API_KEYS:
        try:
            for k in list(config.OPENAI_API_KEYS):
                k = (k or "").strip()
                if k:
                    keys.append(k)
        except Exception:
            pass

    if hasattr(config, "OPENAI_API_KEY") and config.OPENAI_API_KEY:
        k = (config.OPENAI_API_KEY or "").strip()
        if k:
            keys.append(k)

    env_multi = os.getenv("OPENAI_API_KEYS", "")
    if env_multi:
        keys += [x.strip() for x in env_multi.replace("\n", ",").split(",") if x.strip()]

    env_one = os.getenv("OPENAI_API_KEY", "")
    if env_one:
        keys.append(env_one.strip())

    # фильтруем мусор
    keys = [k for k in keys if k and len(k) > 20]
    return list(dict.fromkeys(keys))  # de-dup, preserve order

def _pick_key() -> str:
    keys = _collect_keys()
    if not keys:
        raise RuntimeError("OPENAI_API_KEY(S) не настроены")
    key = random.choice(keys)
    logger.info("🔧 OpenAI ключ выбран: ****%s (всего=%d)", key[-4:], len(keys))
    return key

async def _call_chat_completion(
    client: AsyncOpenAI,
    messages: List[Dict[str, str]],
    model: str,
    temperature: float,
    max_tokens: int,
) -> Dict[str, Any]:
    """
    Универсальный вызов Chat Completions.
    Особенности API:
      • для семейств gpt-5*/mini — temperature строго 1.0 и параметр max_completion_tokens
      • для остальных — обычный max_tokens
    """
    if model.startswith("gpt-5"):
        temperature = 1.0  # строго для gpt-5*
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
        }
    else:
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

    resp = await client.chat.completions.create(**kwargs)
    text = (resp.choices[0].message.content or "").strip()
    usage = resp.usage or None

    return {
        "text": text,
        "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
        "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
        "raw": resp,
    }

async def chat_with_gpt(
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 1500,
    model: Optional[str] = None,
    max_retries: int = 3,
) -> Dict[str, Any]:
    """
    Универсальный вызов GPT с ретраями и фолбэками по списку PREFERRED_MODELS.
    Пустой текст — ошибка → ретрай / переход на следующую модель.
    """
    if not messages:
        raise ValueError("messages пуст")

    # формируем цепочку моделей (приоритет — явный model, затем любимые)
    models_chain: List[str] = []
    if model:
        models_chain.append(model)
    for m in PREFERRED_MODELS:
        if m not in models_chain:
            models_chain.append(m)

    last_exc: Optional[Exception] = None

    for mdl in models_chain:
        for attempt in range(1, max_retries + 1):
            client = AsyncOpenAI(api_key=_pick_key())
            try:
                logger.info(
                    "🧠 GPT call: model=%s, attempt=%d/%d, prompt='%s...'",
                    mdl, attempt, max_retries, (messages[-1].get("content") or "")[:120]
                )
                result = await _call_chat_completion(client, messages, mdl, temperature, max_tokens)
                txt = (result.get("text") or "").strip()
                if not txt:
                    raise RuntimeError("empty_completion")

                logger.info(
                    "✅ GPT ok (model=%s) tokens: p=%d c=%d t=%d; preview='%s...'",
                    mdl, result["prompt_tokens"], result["completion_tokens"], result["total_tokens"],
                    txt[:80].replace("\n", " "),
                )
                return result

            except Exception as e:
                last_exc = e
                delay = min(2 ** (attempt - 1), 8) + random.uniform(0, 0.4)
                logger.warning("⚠️ GPT error (model=%s, attempt=%d): %s; retry in %.1fs", mdl, attempt, str(e), delay)
                await asyncio.sleep(delay)

        logger.warning("↪️ Перехожу на следующую модель после неудач: %s", mdl)

    logger.exception("🔴 Все попытки вызова GPT исчерпаны")
    if last_exc:
        raise last_exc
    raise RuntimeError("Не удалось получить непустой ответ от GPT")
