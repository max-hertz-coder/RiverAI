import os, io, tempfile, logging, re, subprocess
from pathlib import Path
from typing import List
from aiogram import types
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton

from ocr_service import ocr_openai_vision
from generation_service import generate_raw_tasks, generate_raw_solutions
from corrections_service import generate_corrected_tasks
from pdf_utils import (
    template_basic, template_solutions,
    sanitize_solutions, escape_latex, compile_latex_to_pdf
)
chat_mode: dict[int,str] = {}

logger = logging.getLogger(__name__)

# Временные хранилища
pending_prompts: dict[int,str]     = {}
last_raw_tasks: dict[int,str]      = {}
pending_corrections: dict[int,str] = {}

async def build_and_send(raw_tasks: str, msg: types.Message):
    cid = msg.chat.id
    last_raw_tasks[cid] = raw_tasks

    loader = await msg.answer("⏳ Генерирую задачи и решения…")

    # очистка и разбиение
    cleaned = re.sub(r'(?si)Варианты ответа:.*?(?=(?:\n\s*\d+\.\s)|\Z)', '', raw_tasks).strip()
    split_re = re.compile(r'(?m)^\s*(\d+)\.\s*([\s\S]*?)(?=^\s*\d+\.|\Z)')
    tasks = [m.group(2).strip() for m in split_re.finditer(cleaned)] or [cleaned]

    # batch-решения
    sols_raw = await generate_raw_solutions(cleaned)
    sols = [m.group(2).strip() for m in split_re.finditer(sols_raw)] or []
    if len(sols) != len(tasks):
        sols = [ (await generate_raw_solutions(t)).strip() for t in tasks ]
    sols = sanitize_solutions(sols)

    # пакуем в \item
    items_t = "\n".join(f"\\item {escape_latex(t)}" for t in tasks)
    items_s = "\n".join(f"\\item {escape_latex(s)}" for s in sols)

    # компиляция
    pdf_t, log_t = compile_latex_to_pdf(template_basic.render(title="Задачи", content=items_t))
    pdf_s, log_s = compile_latex_to_pdf(template_solutions.render(
        content_tasks=items_t, content_solutions=items_s
    ))

    await loader.delete()

    # отправка
    async def send_pdf(pdf_path, caption, log):
        if pdf_path:
            await msg.answer_document(FSInputFile(pdf_path), caption=caption)
            os.remove(pdf_path)
        elif log.strip():
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
            tf.write(log.encode()); tf.close()
            await msg.answer_document(FSInputFile(tf.name), caption=f"❌ Лог ошибок ({caption})")
            os.remove(tf.name)
        else:
            await msg.answer(f"❌ Не удалось {caption.lower()}, лог пуст.")

    await send_pdf(pdf_t, "📄 Задачи", log_t)
    await send_pdf(pdf_s, "📄 Решения", log_s)

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton("✅ Всё ок", callback_data="confirm_ok"),
        InlineKeyboardButton("✏️ Исправить", callback_data="confirm_fix"),
    ]])
    await msg.answer("Всё устраивает?", reply_markup=kb)

# Handlers

async def handle_document(m: types.Message):
    if chat_mode.get(m.chat.id) != "generate": return
    info = await m.bot.get_file(m.document.file_id)
    data = await m.bot.download_file(info.file_path)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=Path(m.document.file_name).suffix)
    tmp.write(data.read() if isinstance(data, io.BytesIO) else data); tmp.close()

    loader = await m.answer("⌛ Распознаю текст…")
    text = await ocr_openai_vision(tmp.name)
    os.remove(tmp.name)

    if not text:
        return await loader.edit_text("❌ Не удалось распознать текст.")
    await loader.delete()

    cap = (m.caption or "").strip()
    if cap:
        await handle_text_inner(f"{cap}\n\n{text}", m)
    else:
        pending_prompts[m.chat.id] = text
        await m.answer("📥 Текст распознан. Введите подпись для генерации:")

async def handle_photo(m: types.Message):
    if chat_mode.get(m.chat.id) != "generate": return
    file_id = m.photo[-1].file_id
    info = await m.bot.get_file(file_id)
    data = await m.bot.download_file(info.file_path)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    tmp.write(data.read() if isinstance(data, io.BytesIO) else data); tmp.close()

    loader = await m.answer("⌛ Распознаю фото…")
    text = await ocr_openai_vision(tmp.name)
    os.remove(tmp.name)

    if not text:
        return await loader.edit_text("❌ Не удалось распознать текст.")
    await loader.delete()

    cap = (m.caption or "").strip()
    if cap:
        await handle_text_inner(f"{cap}\n\n{text}", m)
    else:
        pending_prompts[m.chat.id] = text
        await m.answer("📥 Текст распознан. Введите подпись для генерации:")

async def handle_text(m: types.Message):
    if chat_mode.get(m.chat.id) != "generate": return
    cid = m.chat.id
    if cid in pending_prompts:
        ocr = pending_prompts.pop(cid)
        await handle_text_inner(f"{m.text}\n\n{ocr}", m)
    else:
        await handle_text_inner(m.text, m)

async def handle_text_inner(prompt: str, m: types.Message):
    tasks_raw = await generate_raw_tasks(prompt)
    await build_and_send(tasks_raw, m)

async def handle_confirm(cb):
    cid = cb.message.chat.id
    if cb.data == "confirm_ok":
        await cb.answer("👍 Отлично!")
        await cb.message.edit_reply_markup(None)
    else:
        raw = last_raw_tasks.get(cid)
        if raw:
            pending_corrections[cid] = raw
            await cb.message.edit_reply_markup(None)
            await cb.message.answer("✏️ Опишите, что нужно изменить:")

async def handle_fix(m: types.Message):
    cid = m.chat.id
    if cid not in pending_corrections: return
    instr, raw = m.text, pending_corrections.pop(cid)
    corrected = await generate_corrected_tasks(instr, raw)
    await build_and_send(corrected, m)