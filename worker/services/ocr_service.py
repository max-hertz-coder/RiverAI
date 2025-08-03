import os
import base64
import asyncio
import logging
import tempfile
from typing import Dict, Any
from dotenv import load_dotenv

import fitz  # PyMuPDF: pip install pymupdf
from openai import OpenAI

load_dotenv()
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY environment variable")

# Инициализация OpenAI клиента
client = OpenAI(api_key=OPENAI_KEY)
logger = logging.getLogger(__name__)

def sync_ocr(path_or_url: str) -> str:
    """
    Выполняет OCR через OpenAI Vision. Поддерживает:
      - URL изображений
      - Локальные JPG/PNG файлы
      - PDF-файлы (конвертирует первую страницу в PNG)

    Возвращает распознанный текст или пустую строку при отказе/ошибке.
    """
    logger.info("Начинаем OCR для: %s", path_or_url)
    
    # Подготовка данных изображения
    if path_or_url.startswith("http"):  # URL
        image_data = {"url": path_or_url, "detail": "high"}
        logger.info("Обрабатываем URL изображения")
    else:
        ext = os.path.splitext(path_or_url)[1].lower()
        logger.info("Обрабатываем локальный файл с расширением: %s", ext)
        
        # PDF → конвертация в PNG
        if ext == ".pdf":
            try:
                logger.info("Конвертируем PDF в PNG")
                doc = fitz.open(path_or_url)
                page = doc.load_page(0)
                pix = page.get_pixmap(dpi=300)
                img_bytes = pix.tobytes("png")
                mime = "png"
                doc.close()
                logger.info("PDF успешно конвертирован, размер: %d байт", len(img_bytes))
            except Exception as e:
                logger.error("Ошибка при обработке PDF: %s", e)
                return ""
        else:
            try:
                with open(path_or_url, "rb") as f:
                    img_bytes = f.read()
                # Определяем MIME по расширению
                mime = "jpeg" if ext in (".jpg", ".jpeg") else ext.lstrip('.')
                logger.info("Файл прочитан, размер: %d байт, MIME: %s", len(img_bytes), mime)
            except Exception as e:
                logger.error("Ошибка при чтении файла: %s", e)
                return ""
        
        # Проверяем размер файла
        if len(img_bytes) > 20 * 1024 * 1024:  # 20MB
            logger.warning("Файл слишком большой: %d байт", len(img_bytes))
            return ""
            
        # Кодируем в base64 и формируем data URI
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        data_uri = f"data:image/{mime};base64,{b64}"
        image_data = {"url": data_uri, "detail": "high"}
        logger.info("Изображение подготовлено для отправки в OpenAI")

    try:
        logger.info("Отправляем запрос в OpenAI Vision API")
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Извлеките весь текст (русский, цифры, формулы) из этого изображения. Если изображение содержит математические формулы, запишите их в текстовом виде. Если изображение не содержит читаемого текста, ответьте 'НЕТЕКСТ'."},
                    {"type": "image_url", "image_url": image_data}
                ]
            }],
            max_tokens=2000,
            temperature=0.0
        )
        text = resp.choices[0].message.content.strip()
        low = text.lower()
        
        logger.info("Получен ответ от OpenAI, длина: %d символов", len(text))
        
        # Проверяем отказ и различные причины
        refusal_keywords = [
            "извин", "sorry", "can't", "cannot", "unable", "not allowed",
            "policy", "guidelines", "inappropriate", "unsafe", "harmful",
            "i'm sorry", "i can't assist", "i cannot assist"
        ]
        
        if any(keyword in low for keyword in refusal_keywords):
            logger.warning("OpenAI отказался обрабатывать изображение")
            return ""
        
        if low == "нетекст" or len(text.strip()) < 10:
            logger.warning("Изображение не содержит читаемого текста")
            return ""
        
        return text
        
    except Exception as e:
        logger.exception("Ошибка при OCR: %s", e)
        return ""

async def ocr_openai_vision(path_or_url: str) -> str:
    """Асинхронная обертка для OCR"""
    return await asyncio.to_thread(sync_ocr, path_or_url)

async def handle_ocr(task: dict) -> dict:
    """
    Сервис для чистого OCR:
    принимает task с полями file_data, file_name, prompt
    возвращает {'type':'ocr', 'text':..., 'prompt':...}
    """
    task_id = task.get("task_id")
    prompt = (task.get("prompt") or "").strip()

    if not task_id:
        return {"type": "error", "message": "Отсутствует task_id."}

    file_data = task.get("file_data")
    if not file_data:
        return {"type": "error", "message": "Нет данных для OCR."}

    try:
        data = base64.b64decode(file_data)
        logger.info(f"🔧 OCR: декодировали файл, размер: {len(data)} байт")
    except Exception as e:
        logger.error("Ошибка base64 декодирования OCR-файла: %s", e)
        return {"type": "error", "message": "Невалидные данные файла."}

    suffix = os.path.splitext(task.get("file_name", "file"))[1] or ".jpg"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(data)
    tmp.close()
    logger.info(f"🔧 OCR: создали временный файл: {tmp.name}")

    try:
        text = (await ocr_openai_vision(tmp.name) or "").strip()
        logger.info(f"🔧 OCR: получили текст, длина: {len(text)} символов")
        if text:
            logger.info(f"🔧 OCR: первые 100 символов: {text[:100]}...")
        else:
            logger.warning("🔧 OCR: получили пустой текст")
    except Exception:
        logger.exception("OCR failure")
        os.remove(tmp.name)
        return {"type": "error", "message": "Ошибка OCR-сервиса."}
    finally:
        if os.path.exists(tmp.name):
            os.remove(tmp.name)

    if not text:
        return {"type": "error", "message": "Не удалось распознать текст."}

    return {
        "type": "ocr",
        "text": text,
        "prompt": prompt
    }

async def handle_ocr_and_generate(task: dict) -> dict:
    """
    Объединённый сервис OCR+генерации:
    - делает OCR через ocr_openai_vision
    - склеивает ваш caption из task['prompt'] с распознанным текстом
    - вызывает handle_tasks для генерации PDF
    - добавляет в ответ поле 'prompt' с финальным запросом
    """
    task_id = task.get("task_id")
    user_prompt = (task.get("prompt") or "").strip()

    if not task_id:
        return {"type": "error", "message": "Отсутствует task_id."}

    # Декодируем файл
    try:
        data = base64.b64decode(task["file_data"])
    except Exception as e:
        logger.error("OCR+Gen: ошибка декодирования: %s", e)
        return {"type": "error", "message": "Ошибка обработки файла."}

    suffix = os.path.splitext(task.get("file_name", ""))[1] or ".jpg"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(data)
    tmp.close()

    try:
        ocr_text = (await ocr_openai_vision(tmp.name) or "").strip()
    except Exception:
        logger.exception("OCR+Gen: ошибка OCR")
        os.remove(tmp.name)
        return {"type": "error", "message": "Ошибка OCR."}
    finally:
        if os.path.exists(tmp.name):
            os.remove(tmp.name)

    if not ocr_text:
        return {"type": "error", "message": "Не удалось распознать текст."}

    final_prompt = f"{user_prompt}\n\n{ocr_text}" if user_prompt else ocr_text

    # Локальный импорт, чтобы не было циклической зависимости
    from worker.services.tasks_service import handle_tasks

    gen_task = {
        "task_id": task_id,
        "type": "generate_tasks",
        "prompt": final_prompt
    }
    result = await handle_tasks(gen_task)

    # Передаём дальше финальный prompt, чтобы воркер его показал
    result["prompt"] = final_prompt
    return result