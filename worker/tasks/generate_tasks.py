import asyncio
from worker.services.generation_service import (
    generate_raw_tasks, generate_raw_solutions, generate_solutions_continuation
)
from worker.services.corrections_service import generate_corrected_tasks
from worker.services.ocr_service import run_ocr
from worker.services.latex_service import compile_latex_to_pdf

async def execute(payload: dict) -> dict:
    """
    Обработчик задачи generate_tasks.

    Поддерживаемые поля payload:
      - 'prompt': str — текстовый запрос для генерации списка задач
      - 'use_ocr': bool — если True, выполнить OCR по 'path_or_url'
      - 'path_or_url': str — путь или URL к изображению/PDF для OCR
      - 'instruction': str — инструкция для корректировки сгенерированных задач
      - 'generate_solutions': bool — если True, сгенерировать решения к задачам
      - 'latex_source': str — LaTeX-код для компиляции в PDF
    """
    result: dict = {}

    # 1. OCR при необходимости
    if payload.get('use_ocr') and 'path_or_url' in payload:
        ocr_text = await run_ocr(payload['path_or_url'])
        result['ocr_text'] = ocr_text
        # подставляем распознанный текст в prompt, если нет явного prompt
        if not payload.get('prompt'):
            payload['prompt'] = ocr_text or ''

    # 2. Генерация raw задач
    prompt = payload.get('prompt', '')
    raw_tasks = await generate_raw_tasks(prompt)
    result['raw_tasks'] = raw_tasks

    # 3. Коррекция raw задач по инструкции
    if 'instruction' in payload:
        corrected = await generate_corrected_tasks(payload['instruction'], raw_tasks)
        result['corrected_tasks'] = corrected

    # 4. Генерация решений
    if payload.get('generate_solutions'):
        solutions = await generate_raw_solutions(raw_tasks)
        result['solutions'] = solutions

    # 5. Компиляция LaTeX в PDF
    if 'latex_source' in payload:
        pdf_bytes = await compile_latex_to_pdf(payload['latex_source'])
        result['pdf_bytes'] = pdf_bytes

    return result
