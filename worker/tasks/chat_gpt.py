import json
from worker import redis_cache, db
from worker.services import gpt_service

MAX_HISTORY_MESSAGES = 10  # limit conversation length

async def handle_chat_gpt(task):
    user_id = task["user_id"]
    student_id = task["student_id"]
    user_message = task["message"]
    # Retrieve conversation history from Redis
    conv_json = await redis_cache.get_conversation(user_id, student_id)
    conversation = []
    if conv_json:
        try:
            conversation = json.loads(conv_json)
        except json.JSONDecodeError:
            conversation = []
    # If no history, add a system message with context (optional)
    if not conversation:
        student = await db.get_student(student_id)
        if student:
            subject = student["subject_enc"]
            level = student["level_enc"]
            # Decrypt subject and level for context
            from worker.utils import encryption
            subject = encryption.decrypt_str(subject) if subject else ""
            level = encryption.decrypt_str(level) if level else ""
            sys_content = f"You are a helpful tutor assistant. The student is learning {subject} at {level} level."
            conversation.append({"role": "system", "content": sys_content})
    # Add user message to conversation
    conversation.append({"role": "user", "content": user_message})
    # Trim conversation if too long
    # Keep system + last (MAX_HISTORY_MESSAGES*2) messages (user+assistant pairs)
    if len(conversation) > 1 + 2 * MAX_HISTORY_MESSAGES:
        # remove oldest user+assistant pair
        # (assuming system is at index 0)
        if conversation[0]["role"] == "system":
            # remove items at index 1 and 2 (first user and assistant) if exist
            if len(conversation) > 2:
                conversation = [conversation[0]] + conversation[-2*MAX_HISTORY_MESSAGES:]
        else:
            conversation = conversation[-2*MAX_HISTORY_MESSAGES:]
    # Ask GPT with conversation
    answer = await gpt_service.ask_gpt(conversation)
    assistant_reply = answer.strip() if answer else "Ошибка или пустой ответ."
    # Add assistant reply to conversation
    conversation.append({"role": "assistant", "content": assistant_reply})
    # Save updated conversation to Redis
    conv_json = json.dumps(conversation, ensure_ascii=False)
    await redis_cache.save_conversation(user_id, student_id, conv_json)
    # Return result
    return {
        "type": "chat",
        "user_id": user_id,
        "student_id": student_id,
        "answer": assistant_reply
    }

async def handle_end_chat(task):
    """Clear chat context for given user & student."""
    user_id = task["user_id"]
    student_id = task["student_id"]
    await redis_cache.clear_conversation(user_id, student_id)
    # No direct result to send to user for end_chat, so we might return nothing or a simple ack
    return None
