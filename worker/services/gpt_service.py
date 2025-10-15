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

# Быстрая и доступная цепочка (исключили у тебя неработающий gpt-5-turbo)
PREFERRED_MODELS: List[str] = [
    "gpt-4-turbo",  # быстрый и стабильный для текста
    "gpt-4o",       # универсал (vision/текст)
    "gpt-5-mini",   # быстрый/дешёвый, но требует особых параметров
    "gpt-5",        # как fallback; у тебя бывает пустая генерация/401
]

def _collect_keys() -> List[str]:
    keys: List[str] = []

    # из config
    if getattr(config, "OPENAI_API_KEYS", None):
        try:
            for k in list(config.OPENAI_API_KEYS):
                k = (k or "").strip()
                if k:
                    keys.append(k)
        except Exception:
            pass
    if getattr(config, "OPENAI_API_KEY", None):
        k = (config.OPENAI_API_KEY or "").strip()
        if k:
            keys.append(k)

    # из окружения
    env_multi = os.getenv("OPENAI_API_KEYS", "")
    if env_multi:
        keys += [x.strip() for x in env_multi.replace("\n", ",").split(",") if x.strip()]
    env_one = os.getenv("OPENAI_API_KEY", "")
    if env_one:
        keys.append(env_one.strip())

    keys = [k for k in keys if k and len(k) > 20]
    # de-dup, preserve order
    return list(dict.fromkeys(keys))

def _pick_key() -> str:
    keys = _collect_keys()
    if not keys:
        raise RuntimeError("OPENAI_API_KEY(S) не настроены")
    key = random.choice(keys)
    logger.info("🔧 OpenAI ключ выбран: ****%s (всего=%d)", key[-4:], len(keys))
    return key

async def _chat_create_with_timeout(client: AsyncOpenAI, timeout: float, **kwargs) -> Any:
    # Жёсткий таймаут запроса, чтобы не зависать на минуту+
    return await asyncio.wait_for(client.chat.completions.create(**kwargs), timeout=timeout)

async def _call_chat_completion(
    client: AsyncOpenAI,
    messages: List[Dict[str, str]],
    model: str,
    temperature: float,
    max_tokens: int,
    *,
    request_timeout: float = 55.0,
) -> Dict[str, Any]:
    """
    Универсальный вызов Chat Completions.
    Особенности API (по актуальным докам Chat Completions): для некоторых семейств
    используется параметр `max_completion_tokens` вместо `max_tokens`. Мы это
    учитываем для всех моделей, начинающихся с 'gpt-5' (и mini). :contentReference[oaicite:1]{index=1}
    """
    if model.startswith("gpt-5"):
        # для gpt-5/mini — строго temperature=1.0 и max_completion_tokens
        temperature = 1.0
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

    resp = await _chat_create_with_timeout(client, request_timeout, **kwargs)
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
    request_timeout: float = 55.0,
) -> Dict[str, Any]:
    """
    Универсальный вызов GPT с ретраями и фолбэками.
    Пустой текст → ошибка → ретрай → переход на следующую модель.
    Используем модели из оф. линеек GPT-4 Turbo и GPT-4o (стабильно поддерживаются). :contentReference[oaicite:2]{index=2}
    """
    if not messages:
        raise ValueError("messages пуст")

    # Цепочка моделей: явная → приоритетная
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
                result = await _call_chat_completion(
                    client, messages, mdl, temperature, max_tokens, request_timeout=request_timeout
                )
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
                emsg = str(e)
                # если модель реально недоступна — скипаем её
                if "model_not_found" in emsg or "does not exist" in emsg:
                    logger.warning("⛔ Модель недоступна: %s — пропускаю", mdl)
                    break
                last_exc = e
                delay = min(2 ** (attempt - 1), 8) + random.uniform(0, 0.4)
                logger.warning("⚠️ GPT error (model=%s, attempt=%d): %s; retry in %.1fs", mdl, attempt, emsg, delay)
                await asyncio.sleep(delay)

        logger.warning("↪️ Перехожу на следующую модель после неудач: %s", mdl)

    logger.exception("🔴 Все попытки вызова GPT исчерпаны")
    if last_exc:
        raise last_exc
    raise RuntimeError("Не удалось получить непустой ответ от GPT")
