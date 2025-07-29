import os
import base64
import tempfile
import logging
import asyncio

from dotenv import load_dotenv
import fitz  # PyMuPDF
from openai import OpenAI

from worker.services.ocr_services import ocr_openai_vision
from worker.services.tasks_service import handle_tasks

load_dotenv()
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY environment variable")

client = OpenAI(api_key=OPENAI_KEY)
logger = logging.getLogger(__name__)

def sync_ocr(path_or_url: str) -> str:
    """
    Выполняет OCR через OpenAI Vision.
    Поддерживает URL, локальные JPG/PNG и PDF (конвертация первой страницы).
    Возвращает распознанный текст или пустую строку.
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
                    {"type": "text", "text": "Извлеките весь текст (русский, цифры, формулы) из этого изображения."},
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

async def handle_ocr_and_generate(task: dict) -> dict:
    """
    Берёт base64-изображение из task["file_data"], выполняет OCR,
    добавляет ваш caption из task["prompt"], формирует final_prompt,
    а затем вызывает handle_tasks для генерации PDF.
    Возвращает результат handle_tasks с добавленным полем "prompt".
    """
    user_id     = task.get("user_id")
    student_id  = task.get("student_id")
    user_prompt = (task.get("prompt") or "").strip()

    # 1) Декодируем файл
    try:
        data = base64.b64decode(task["file_data"])
    except Exception as e:
        logger.error("OCR+Gen: ошибка декодирования: %s", e)
        return {"type": "error", "user_id": user_id, "message": "Ошибка обработки файла."}

    # 2) Сохраняем в temp-файл
    suffix = os.path.splitext(task.get("file_name", ""))[1] or ".jpg"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(data)
    tmp.close()

    # 3) Запускаем OCR
    try:
        ocr_text = (await ocr_openai_vision(tmp.name) or "").strip()
    except Exception:
        logger.exception("OCR+Gen: ошибка OCR")
        os.remove(tmp.name)
        return {"type": "error", "user_id": user_id, "message": "Ошибка OCR."}
    finally:
        if os.path.exists(tmp.name):
            os.remove(tmp.name)

    if not ocr_text:
        return {"type": "error", "user_id": user_id, "message": "Не удалось распознать текст."}

    # 4) Формируем финальный prompt
    final_prompt = f"{user_prompt}\n\n{ocr_text}" if user_prompt else ocr_text

    # 5) Вызываем генерацию заданий
    gen_task = {
        "type": "generate_tasks",
        "user_id": user_id,
        "student_id": student_id,
        "prompt": final_prompt
    }
    result = await handle_tasks(gen_task)

    # 6) Добавляем prompt в ответ, чтобы main.py мог его показать
    result["prompt"] = final_prompt
    return result