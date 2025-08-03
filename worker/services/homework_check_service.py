import os
import logging
from typing import Dict, Any
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY environment variable")

client = OpenAI(api_key=OPENAI_KEY)
logger = logging.getLogger(__name__)

async def check_homework(text: str) -> str:
    """
    Отправляем GPT на проверку: просим найти ошибки и дать рекомендации.
    """
    system = """Вы — опытный преподаватель математики. Проверьте домашнюю работу ниже, найдите ошибки и дайте комментарии.

Оформите ответ в ПРОСТОМ LaTeX формате, используя ТОЛЬКО следующие команды:
- \\section*{название} - для разделов
- \\begin{enumerate} ... \\end{enumerate} - для списков
- \\item - для элементов списка

ВАЖНЫЕ ПРАВИЛА:
1. Каждый \\item должен быть на отдельной строке
2. Не оставляйте пустые enumerate блоки
3. Используйте простые названия разделов без специальных символов
4. НЕ используйте \\textbf, \\textit или другие команды форматирования
5. НЕ используйте Unicode символы вообще
6. НЕ используйте математические символы в тексте
7. Пишите простым текстом без специальных символов

Структура ответа:
\\section*{Общая оценка}
[Краткая общая оценка работы]

\\section*{Найденные ошибки}
\\begin{enumerate}
\\item [Описание ошибки 1]
\\item [Описание ошибки 2]
\\end{enumerate}

\\section*{Рекомендации}
\\begin{enumerate}
\\item [Рекомендация 1]
\\item [Рекомендация 2]
\\end{enumerate}

ПРИМЕР ПРАВИЛЬНОГО ФОРМАТА:
\\section*{Общая оценка}
Работа содержит несколько ошибок в математических выражениях.

\\section*{Найденные ошибки}
\\begin{enumerate}
\\item Ошибка в решении уравнения
\\item Неправильное применение свойств логарифмов
\\end{enumerate}"""
    
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": f"Проверьте эту домашнюю работу:\n\n{text}"}
            ],
            temperature=0.0,
            max_tokens=2000
        )
        check_result = resp.choices[0].message.content.strip()
        return check_result
    except Exception as e:
        logger.exception("Error in check_homework")
        return "❌ Не удалось проверить ДЗ: " + str(e)

async def handle_check_homework(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    Обработчик задачи проверки домашнего задания.
    Принимает task с полями: task_id, text (текст для проверки)
    Возвращает результат проверки.
    """
    task_id = task.get("task_id")
    text = task.get("text", "").strip()
    
    logger.info(f"🔧 Обрабатываем задачу check_homework: task_id={task_id}, text_length={len(text)}")
    
    if not task_id:
        logger.error("❌ Отсутствует task_id в задаче check_homework")
        return {"type": "error", "message": "Отсутствует task_id."}
    
    if not text:
        logger.error("❌ Нет текста для проверки в задаче check_homework")
        return {"type": "error", "message": "Нет текста для проверки."}
    
    try:
        logger.info(f"🔧 Проверяем домашнее задание: task_id={task_id}")
        
        # Проверяем домашнее задание
        check_result = await check_homework(text)
        
        logger.info(f"✅ Проверено домашнее задание: task_id={task_id}, result_length={len(check_result)}")
        
        return {
            "type": "check_homework",
            "task_id": task_id,
            "original_text": text,
            "check_result": check_result
        }
        
    except Exception as e:
        logger.exception(f"❌ Ошибка в handle_check_homework для task_id={task_id}: {e}")
        return {
            "type": "error",
            "task_id": task_id,
            "message": f"Ошибка при проверке домашнего задания: {str(e)}"
        } 