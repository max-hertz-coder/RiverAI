import os
import httpx
import base64
from io import BytesIO
from datetime import datetime
from zoneinfo import ZoneInfo

from asyncpg.pool import Pool

YANDEX_UPLOAD_URL = "https://cloud-api.yandex.net/v1/disk/resources/upload"


async def get_yandex_token(db_pool: Pool, user_id: int) -> str:
    """
    Получение OAuth-токена Яндекс.Диска из БД
    """
    query = "SELECT yandex_token FROM users WHERE telegram_id = $1"
    async with db_pool.acquire() as conn:
        return await conn.fetchval(query, user_id)


async def save_pdf_to_yandex_disk(
    db_pool: Pool,
    user_id: int,
    pdf_bytes: bytes,
    student_name: str,
    file_type: str
) -> str:
    """
    Сохраняет PDF-файл на Яндекс.Диск.
    Формирует имя: ИмяТип_дата.pdf и возвращает URL для пользователя.
    """
    token = await get_yandex_token(db_pool, user_id)
    if not token:
        raise ValueError("У пользователя нет токена Яндекс.Диска")

    dt_str = datetime.now(ZoneInfo("Europe/Moscow")).strftime("%Y-%m-%d_%H-%M")
    safe_name = student_name.strip().replace(" ", "_")
    filename = f"{safe_name}_{file_type}_{dt_str}.pdf"
    yadisk_path = f"app_files/{filename}"

    # Получаем ссылку на загрузку
    async with httpx.AsyncClient() as client:
        res = await client.get(
            YANDEX_UPLOAD_URL,
            headers={"Authorization": f"OAuth {token}"},
            params={"path": yadisk_path, "overwrite": "true"},
            timeout=15
        )
        res.raise_for_status()
        upload_url = res.json().get("href")

        # Отправляем файл
        put_res = await client.put(upload_url, content=pdf_bytes, timeout=20)
        put_res.raise_for_status()

    return f"https://disk.yandex.ru/client/disk/app_files/{filename}"
