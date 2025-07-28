import asyncio
import base64
import logging
from io import BytesIO
from PIL import Image
import fitz           # PyMuPDF
import pytesseract    # Tesseract OCR

logging.basicConfig(level=logging.INFO)

async def handle_ocr(task: dict) -> dict:
    """
    Распознаёт текст из PDF или изображения (base64 в task['file_data']),
    возвращает:
      { "type":"ocr", "user_id":..., "student_id":..., "text": "...распознанный текст..." }
    """
    user_id = task.get("user_id")
    student_id = task.get("student_id")
    file_data = task.get("file_data", "")
    filename = task.get("filename", "")

    text = ""
    try:
        raw = base64.b64decode(file_data)
        ext = filename.split(".")[-1].lower()

        if ext == "pdf":
            doc = fitz.open(stream=raw, filetype="pdf")
            for page in doc:
                pix = page.get_pixmap()
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                text += pytesseract.image_to_string(img)
        else:
            img = Image.open(BytesIO(raw))
            text = pytesseract.image_to_string(img)

    except Exception as e:
        logging.error(f"OCR error: {e}")
        text = "(не удалось распознать текст)"

    return {
        "type": "ocr",
        "user_id": user_id,
        "student_id": student_id,
        "text": text
    }
