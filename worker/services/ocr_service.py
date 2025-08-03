import os
import base64
import asyncio
import logging
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

async def handle_ocr(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    Обработчик задачи OCR.
    Принимает task с полями: task_id, file_path (путь к файлу) или image_url (URL изображения)
    Возвращает распознанный текст.
    """
    task_id = task.get("task_id")
    file_path = task.get("file_path")
    image_url = task.get("image_url")
    
    logger.info(f"🔧 Обрабатываем задачу OCR: task_id={task_id}")
    
    if not task_id:
        logger.error("❌ Отсутствует task_id в задаче OCR")
        return {"type": "error", "message": "Отсутствует task_id."}
    
    if not file_path and not image_url:
        logger.error("❌ Нет файла или URL для OCR")
        return {"type": "error", "message": "Нет файла или URL для OCR."}
    
    try:
        logger.info(f"🔧 Выполняем OCR: task_id={task_id}")
        
        # Выполняем OCR
        if image_url:
            text = await ocr_openai_vision(image_url)
        else:
            text = await ocr_openai_vision(file_path)
        
        logger.info(f"✅ OCR завершен: task_id={task_id}, text_length={len(text)}")
        
        return {
            "type": "ocr",
            "task_id": task_id,
            "text": text,
            "file_path": file_path,
            "image_url": image_url
        }
        
    except Exception as e:
        logger.exception(f"❌ Ошибка в handle_ocr для task_id={task_id}: {e}")
        return {
            "type": "error",
            "task_id": task_id,
            "message": f"Ошибка при OCR: {str(e)}"
        }

async def handle_ocr_and_generate(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    Обработчик задачи OCR + генерация заданий.
    Принимает task с полями: task_id, file_path (путь к файлу) или image_url (URL изображения)
    Возвращает распознанный текст и сгенерированные задания.
    """
    task_id = task.get("task_id")
    file_path = task.get("file_path")
    image_url = task.get("image_url")
    
    logger.info(f"🔧 Обрабатываем задачу OCR + генерация: task_id={task_id}")
    
    if not task_id:
        logger.error("❌ Отсутствует task_id в задаче OCR + генерация")
        return {"type": "error", "message": "Отсутствует task_id."}
    
    if not file_path and not image_url:
        logger.error("❌ Нет файла или URL для OCR")
        return {"type": "error", "message": "Нет файла или URL для OCR."}
    
    try:
        logger.info(f"🔧 Выполняем OCR: task_id={task_id}")
        
        # Выполняем OCR
        if image_url:
            text = await ocr_openai_vision(image_url)
        else:
            text = await ocr_openai_vision(file_path)
        
        if not text:
            logger.warning(f"OCR не вернул текст для task_id={task_id}")
            return {
                "type": "error",
                "task_id": task_id,
                "message": "Не удалось распознать текст из изображения."
            }
        
        logger.info(f"✅ OCR завершен: task_id={task_id}, text_length={len(text)}")
        
        # Генерируем задания на основе распознанного текста
        from .generation_service import generate_raw_tasks
        raw_tasks = await generate_raw_tasks(text)
        
        logger.info(f"✅ Генерация завершена: task_id={task_id}, tasks_length={len(raw_tasks)}")
        
        return {
            "type": "ocr_and_generate",
            "task_id": task_id,
            "ocr_text": text,
            "raw_tasks": raw_tasks,
            "file_path": file_path,
            "image_url": image_url
        }
        
    except Exception as e:
        logger.exception(f"❌ Ошибка в handle_ocr_and_generate для task_id={task_id}: {e}")
        return {
            "type": "error",
            "task_id": task_id,
            "message": f"Ошибка при OCR + генерации: {str(e)}"
        }