import os
import base64
import tempfile
import logging
import asyncio

from dotenv import load_dotenv
import fitz  # PyMuPDF
from openai import OpenAI
from common.redis_utils import get_context_by_task_id

load_dotenv()
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY environment variable")

client = OpenAI(api_key=OPENAI_KEY)
logger = logging.getLogger(__name__)


def sync_ocr(path_or_url: str) -> str:
    """
    Выполняет OCR через OpenAI Vision.
    Поддерживает:
      - URL изображений
      - Локальные JPG/PNG файлы
      - PDF-файлы (конвертирует первую страницу в PNG)
    Возвращает текст или пустую строку при отказе.
    """
    if path_or_url.startswith("http"):
        image_data = {"url": path_or_url, "detail": "high"}
    else:
        ext = os.path.splitext(path_or_url)[1].lower()
        if ext == ".pdf":
            doc = fitz.open(path_or_url)
            page = doc.load_page(0)
            pix = page.get_pixmap(dpi=300)
            img_bytes = pix.tobytes("png")
            mime = "png"
        else:
            with open(path_or_url, "rb") as f:
                img_bytes = f.read()
            mime = "jpeg" if ext in (".jpg", ".jpeg") else ext.lstrip(".")
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        data_uri = f"data:image/{mime};base64,{b64}"
        image_data = {"url": data_uri, "detail": "high"}

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text",      "text": "Извлеките весь текст (русский, цифры, формулы) из этого изображения."},
                    {"type": "image_url", "image_url": image_data}
                ]
            }]
        )
        text = resp.choices[0].message.content.strip()
        low = text.lower()
        if "извин" in low or "sorry" in low:
            logger.info("OCR отказ: %r", text)
            return ""
        return text
    except Exception as e:
        logger.exception("Ошибка при OCR: %s", e)
        return ""


async def ocr_openai_vision(path_or_url: str) -> str:
    """Асинхронная обёртка для sync_ocr."""
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
    except Exception as e:
        logger.error("Ошибка base64 декодирования OCR-файла: %s", e)
        return {"type": "error", "message": "Невалидные данные файла."}

    suffix = os.path.splitext(task.get("file_name", "file"))[1] or ".jpg"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(data)
    tmp.close()

    try:
        text = (await ocr_openai_vision(tmp.name) or "").strip()
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