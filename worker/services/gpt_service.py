import asyncio
import logging
import random
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from worker import config

logger = logging.getLogger(__name__)

# Порядок предпочтения моделей (сверху — приоритетнее)
PREFERRED_MODELS: List[str] = [
    "gpt-5-mini",
    "gpt-5",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-3.5-turbo",
]


def _pick_key() -> str:
    """Берём случайный ключ из списка, иначе основной из env."""
    # Поддержка как списка ключей в конфиге, так и одиночного
    keys = []
    if getattr(config, "OPENAI_API_KEYS", None):
        keys.extend([k.strip() for k in config.OPENAI_API_KEYS if k.strip()])
    if getattr(config, "OPENAI_API_KEY", None):
        keys.append(config.OPENAI_API_KEY.strip())

    keys = [k for k in keys if k and len(k) > 10]
    if not keys:
        raise RuntimeError("OPENAI_API_KEY(S) не настроены")

    key = random.choice(keys)
    logger.info("🔧 Выбран OpenAI ключ: ****%s (всего доступно: %d)", key[-4:], len(keys))
    return key


async def _call_chat_completion(
    client: AsyncOpenAI,
    messages: List[Dict[str, str]],
    model: str,
    temperature: float,
    max_tokens: int,
) -> Dict[str, Any]:
    """
    Общий вызов Chat Completions.
    Для моделей семейства gpt-5 используем ограничения API:
    - temperature = 1.0
    - max_completion_tokens вместо max_tokens
    """
    if model.startswith("gpt-5"):
        temperature = 1.0  # fix для gpt-5/mini
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

    # В старом/новом SDK content может быть пустым, а полезная нагрузка уехать в tools и т.п.
    # Нас интересует обычный текст:
    text = (resp.choices[0].message.content or "").strip()
    usage = resp.usage or None

    return {
        "text": text,
        "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
        "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
        "raw": resp,  # оставим на случай отладки
    }


async def chat_with_gpt(
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 1200,
    model: Optional[str] = None,
    max_retries: int = 3,
) -> Dict[str, Any]:
    """
    Универсальный вызов GPT с ретраями и автоматическим переходом на другие модели.
    ВАЖНО: теперь «пустой текст» считаем неуспехом → будет ретрай/фолбэк.
    """
    if not messages:
        raise ValueError("messages пуст")

    # Готовим цепочку моделей
    models_chain: List[str] = []
    if model:
        models_chain.append(model)
    for m in PREFERRED_MODELS:
        if m not in models_chain:
            models_chain.append(m)

    last_exc: Optional[Exception] = None

    for mdl in models_chain:
        for attempt in range(1, max_retries + 1):
            key = _pick_key()
            client = AsyncOpenAI(api_key=key)
            try:
                logger.info(
                    "🧠 GPT call: model=%s, attempt=%d/%d, last_user='%s...'",
                    mdl, attempt, max_retries, (messages[-1].get("content") or "")[:120]
                )
                result = await _call_chat_completion(client, messages, mdl, temperature, max_tokens)
                txt = (result.get("text") or "").strip()

                if not txt:
                    # ⚠️ Пустой ответ — считаем ошибкой и пробуем ещё/другую модель
                    logger.warning("⚠️ GPT пустой ответ (model=%s, attempt=%d) — считаю неуспехом.", mdl, attempt)
                    raise RuntimeError("empty_completion")

                logger.info(
                    "✅ GPT ok (model=%s) tokens: prompt=%d, completion=%d, total=%d, preview='%s...'",
                    mdl,
                    result["prompt_tokens"],
                    result["completion_tokens"],
                    result["total_tokens"],
                    txt[:80].replace("\n", " "),
                )
                return result

            except Exception as e:
                last_exc = e
                # экспоненциальная пауза
                delay = min(2 ** (attempt - 1), 8) + random.uniform(0, 0.5)
                logger.warning(
                    "⚠️ GPT error (model=%s, attempt=%d): %s; retry in %.1fs",
                    mdl, attempt, str(e), delay
                )
                await asyncio.sleep(delay)

        logger.warning("↪️ Перехожу на следующую модель (после неудач): %s", mdl)

    logger.exception("🔴 Все попытки вызова GPT исчерпаны")
    if last_exc:
        raise last_exc
    raise RuntimeError("Не удалось получить непустой ответ от GPT")
