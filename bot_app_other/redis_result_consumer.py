import json
import logging
import asyncio
from io import BytesIO
import base64
from aiogram import Bot
from common.redis_utils import (
    get_context_by_task_id,
    cleanup_task_context,
    save_last_solutions_file,  # 👈 добавлено
)
from bot_app.keyboards.chat_menu import (
    chat_gpt_back_kb,
    result_plan_kb,
    result_tasks_kb,
    result_check_kb
)


async def process_redis_result(result_data: dict, bot: Bot):
    """Обрабатывает результат из Redis"""
    try:
        task_id = result_data.get("task_id")
        if not task_id:
            logging.warning("⚠️ В результате нет task_id")
            return

        context = await get_context_by_task_id(task_id)
        if not context:
            logging.warning(f"⚠️ Контекст не найден для task_id={task_id}")
            return

        user_id = context.get("user_id")
        student_id = context.get("student_id")
        result_type = result_data.get("type")

        if not user_id or not result_type:
            logging.warning("⚠️ В результате нет user_id или type")
            return

        logging.info(f"📥 Обрабатываем результат: task_id={task_id}, type={result_type}, user_id={user_id}")

        # === Generated tasks ===
        if result_type == "tasks":
            latex_tasks = result_data.get("latex_tasks")
            latex_solutions = result_data.get("latex_solutions")

            logging.info(f"🔧 Обрабатываем tasks результат:")
            logging.info(f"  Has latex_tasks: {bool(latex_tasks)}")
            logging.info(f"  Has latex_solutions: {bool(latex_solutions)}")

            kb = {
                "inline_keyboard": [[
                    {"text": "✅ Всё отлично",    "callback_data": "tasks_ok"},
                    {"text": "✏️ Переделать", "callback_data": f"refine_tasks:{student_id}"}
                ]]
            }

            # Сначала отправляем PDF
            if latex_tasks and latex_solutions:
                from bot_app.pdf_compiler import compile_and_send_pdfs

                # 🧠 Компилируем и отправляем PDF
                pdf_paths = await compile_and_send_pdfs(latex_tasks, latex_solutions, bot, user_id)

                # 🧠 Сохраняем Solutions.pdf в Redis (base64)
                if pdf_paths and pdf_paths.get("solutions"):
                    with open(pdf_paths["solutions"], "rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                        await save_last_solutions_file(user_id, b64)

            else:
                logging.warning(f"⚠️ LaTeX код отсутствует в результате")
                await bot.send_message(user_id, "❌ Ошибка: LaTeX код не получен")

            # Затем задаём вопрос
            await bot.send_message(user_id, "❓ Всё ли устраивает?", reply_markup=kb)

        # === Chat response ===
        elif result_type == "chat":
            text = result_data.get("answer", "(нет ответа)")
            await bot.send_message(user_id, text, reply_markup=chat_gpt_back_kb(student_id))

        # === Study plan ===
        elif result_type == "plan":
            plan_text = result_data.get("plan_text", "(пусто)")
            await bot.send_message(user_id, f"📄 План:\n{plan_text}", reply_markup=result_plan_kb(student_id))

        # === Homework check ===
        elif result_type == "check":
            report = result_data.get("report_text", "(нет отчёта)")
            await bot.send_message(user_id, f"✔️ Результаты проверки:\n{report}", reply_markup=result_check_kb(student_id))

            file_b64 = result_data.get("file")
            if file_b64:
                pdf_bytes = base64.b64decode(file_b64)
                buf = BytesIO(pdf_bytes)
                buf.name = "Homework_Report.pdf"
                await bot.send_document(user_id, buf, caption="📎 Отчёт в PDF")

        # === New Homework check (with PDF) ===
        elif result_type == "homework_check":
            report_text = result_data.get("check_result", "(нет отчёта)")
            latex_content = result_data.get("latex_content", "")
            
            # Компилируем и отправляем PDF, если есть LaTeX код
            if latex_content:
                try:
                    from bot_app.pdf_compiler import compile_latex_to_pdf
                    from aiogram.types import BufferedInputFile
                    
                    pdf_path, log = compile_latex_to_pdf(latex_content)
                    if pdf_path:
                        with open(pdf_path, "rb") as f:
                            file_bytes = f.read()
                            document = BufferedInputFile(file_bytes, filename="Homework_Check.pdf")
                            await bot.send_document(user_id, document, caption="📄 Результат проверки ДЗ")
                        logging.info(f"✅ PDF Homework Check отправлен пользователю {user_id}")
                    else:
                        logging.error(f"🔴 Ошибка компиляции PDF Homework Check: {log}")
                        await bot.send_message(user_id, "❌ Ошибка создания PDF с результатом проверки")
                except Exception as e:
                    logging.exception("Ошибка отправки PDF: %s", e)
                    await bot.send_message(user_id, "❌ Ошибка создания PDF с результатом проверки")
            else:
                # Если нет LaTeX кода, отправляем только текстовый отчет
                if len(report_text) > 4000:
                    report_text = report_text[:4000] + "\n\n... (отчет обрезан)"
                await bot.send_message(user_id, f"📋 **Результат проверки ДЗ:**\n\n{report_text}")

        # === New Chat GPT response ===
        elif result_type == "chat_gpt":
            answer = result_data.get("gpt_response", "(нет ответа)")
            
            if len(answer) > 4000:
                answer = answer[:4000] + "\n\n... (ответ обрезан)"
            
            await bot.send_message(user_id, f"🤖 **Ответ GPT:**\n\n{answer}")

        # === Error ===
        elif result_type == "error":
            error_msg = result_data.get("message", "Неизвестная ошибка")
            await bot.send_message(user_id, f"⚠️ Ошибка: {error_msg}")

        else:
            logging.warning(f"❓ Unknown result type: {result_type}")

        logging.info(f"✅ Отправлено пользователю {user_id} по task_id={task_id}")

    except Exception as e:
        logging.exception(f"🔴 Ошибка обработки результата: {e}")

    finally:
        await cleanup_task_context(task_id)


async def consume_redis_results(bot: Bot):
    """Проверяет Redis на наличие результатов каждые 2 секунды"""
    from common.redis_utils import _get_client

    logging.info("🔧 Запускаем проверку результатов в Redis...")

    while True:
        try:
            client = _get_client()
            result_keys = await client.keys("result:*")

            for key in result_keys:
                try:
                    result_json = await client.get(key)
                    if result_json:
                        result_data = json.loads(result_json)
                        await process_redis_result(result_data, bot)
                        await client.delete(key)
                        logging.info(f"✅ Обработан результат из Redis: {key}")
                except Exception as e:
                    logging.error(f"🔴 Ошибка обработки результата из Redis {key}: {e}")

            await asyncio.sleep(2)

        except Exception as e:
            logging.error(f"🔴 Ошибка в consume_redis_results: {e}")
            await asyncio.sleep(5)
