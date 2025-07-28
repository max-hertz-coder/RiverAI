import base64
import logging
from io import BytesIO

from worker import db, redis_cache
from worker.utils import encryption
from worker.services import gpt_service, latex_service, storage_service
from worker.services.ocr_service import handle_ocr

logging.basicConfig(level=logging.INFO)


def save_report_to_redis(user_id: int, student_id: int, report: str):
    """
    Сохраняет текст отчёта в Redis для возможности последующего уточнения (refine).
    """
    key = f"check:{user_id}:{student_id}"
    client = redis_cache._get_client()
    # Сохраняем отчёт без срока жизни
    return client.set(key, report)


async def handle_check_homework(task: dict) -> dict:
    """
    Обрабатывает задачу проверки домашней работы:
    - Декодирует текст решения или выполняет OCR, если получен файл-изображение.
    - Запрашивает оценку у GPT.
    - Генерирует PDF-отчёт через LaTeX.
    - Сохраняет отчёт в Redis и/или на Яндекс.Диск.
    Возвращает словарь с типом "check" и содержимым отчёта.
    """
    user_id = task.get("user_id")
    student_id = task.get("student_id")
    solution_text = task.get("solution_text") or ""
    file_data = task.get("file_data")
    filename = task.get("filename") or ""

    # Если нет решения в тексте, пытаемся извлечь из файла
    if not solution_text and file_data:
        try:
            raw_bytes = base64.b64decode(file_data)
            # Пробуем как текст
            solution_text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            # Если файл-изображение, запускаем OCR
            ext = filename.split('.')[-1].lower()
            if ext in ("png", "jpg", "jpeg"):  # изображение
                ocr_result = await handle_ocr({
                    "user_id": user_id,
                    "student_id": student_id,
                    "file_data": file_data,
                    "filename": filename
                })
                solution_text = ocr_result.get("text", "")
            else:
                solution_text = ""
        except Exception as e:
            logging.error(f"Ошибка при декодировании файла решения: {e}")
            solution_text = ""

    # Получаем профиль ученика
    student_row = await db.get_student(student_id)
    subject = level = ""
    if student_row:
        subject = encryption.decrypt_str(student_row.get("subject_enc")) if student_row.get("subject_enc") else ""
        level = encryption.decrypt_str(student_row.get("level_enc")) if student_row.get("level_enc") else ""

    # Формируем запрос к GPT
    prompt = (
        f"Проверь решение по предмету '{subject or 'N/A'}', уровень '{level or 'N/A'}'. "
        f"Решение: {solution_text or '(файл)'}\n"
        "Дай пояснения к ошибкам и верным решениям, перечисли результаты по каждому пункту."
    )
    messages = [{"role": "user", "content": prompt}]

    # Выбираем модель в зависимости от плана пользователя
    user = await db.get_user(user_id)
    model = "gpt-3.5-turbo"
    if user and user.get("plan") == "premium":
        model = "gpt-4"

    answer = await gpt_service.ask_gpt(messages, model=model)
    report_text = answer.strip() if answer else "Не удалось получить ответ от GPT."

    # Генерация PDF через LaTeX
    pdf_path = latex_service.generate_report_pdf(report_text)

    file_url = None
    file_b64 = None
    # Пытаемся загрузить на Я.Диск
    if user and user.get("ydisk_token_enc"):
        token = encryption.decrypt_str(user.get("ydisk_token_enc"))
        if token and pdf_path:
            remote_path = f"AI_Tutor/Report_{student_id}.pdf"
            success = await storage_service.upload_to_yadisk(token, pdf_path, remote_path)
            if success:
                file_url = "yadisk"
    # Если не загрузили на Диск — кодируем PDF в base64
    if file_url is None and pdf_path:
        try:
            with open(pdf_path, "rb") as f:
                file_b64 = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            logging.error(f"Ошибка при чтении PDF-файла: {e}")

    # Увеличиваем счётчик использования
    await db.increment_usage(user_id)

    # Сохраняем отчёт в Redis для refine
    await save_report_to_redis(user_id, student_id, report_text)

    # Формируем итоговый результат
    result = {
        "type": "check",
        "user_id": user_id,
        "student_id": student_id,
        "report_text": report_text,
        "file_url": file_url
    }
    if file_b64:
        result["file"] = file_b64
    return result


async def handle_refine_check(task: dict) -> dict:
    """
    Обрабатывает уточнение отчёта (refine):
    - Загружает оригинальный отчёт из Redis
    - Применяет комментарии пользователя через GPT
    - Генерирует обновлённый PDF
    - Возвращает обновлённый отчёт и (по возможности) attachment
    """
    user_id = task.get("user_id")
    student_id = task.get("student_id")
    notes = task.get("notes", "")

    # Получаем сохранённый отчёт
    key = f"check:{user_id}:{student_id}"
    client = redis_cache._get_client()
    raw = await client.get(key)
    if not raw:
        return {"type": "error", "user_id": user_id, "message": "Оригинальный отчёт не найден."}
    last_report = raw.decode("utf-8")

    # Формируем промпт для уточнения
    prompt = (
        f"Вот предыдущий отчёт проверки домашней работы:\n{last_report}\n\n"
        f"Комментарии для уточнения:\n{notes}\n\nОбнови отчёт с учётом этих замечаний."
    )
    messages = [{"role": "user", "content": prompt}]

    # Выбор модели
    user = await db.get_user(user_id)
    model = "gpt-3.5-turbo"
    if user and user.get("plan") == "premium":
        model = "gpt-4"

    updated = await gpt_service.ask_gpt(messages, model=model)
    report_text = updated.strip() if updated else "Не удалось получить обновлённый отчёт."

    # Генерация PDF
    pdf_path = latex_service.generate_report_pdf(report_text)

    file_url = None
    file_b64 = None
    if user and user.get("ydisk_token_enc"):
        token = encryption.decrypt_str(user.get("ydisk_token_enc"))
        if token and pdf_path:
            remote_path = f"AI_Tutor/Report_{student_id}_refined.pdf"
            success = await storage_service.upload_to_yadisk(token, pdf_path, remote_path)
            if success:
                file_url = "yadisk"
    if file_url is None and pdf_path:
        try:
            with open(pdf_path, "rb") as f:
                file_b64 = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            logging.error(f"Ошибка при чтении PDF-файла: {e}")

    await db.increment_usage(user_id)
    await save_report_to_redis(user_id, student_id, report_text)

    result = {
        "type": "check",
        "user_id": user_id,
        "student_id": student_id,
        "report_text": report_text,
        "file_url": file_url
    }
    if file_b64:
        result["file"] = file_b64
    return result
