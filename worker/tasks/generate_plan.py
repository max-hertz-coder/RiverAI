from worker import db, config
from worker.utils import encryption
from worker.services import gpt_service, latex_service, storage_service

async def handle_generate_plan(task):
    user_id = task["user_id"]
    student_id = task["student_id"]
    description = task["description"]
    # Fetch student data
    student_row = await db.get_student(student_id)
    subject = ""
    level = ""
    if student_row:
        subject = encryption.decrypt_str(student_row["subject_enc"]) if student_row["subject_enc"] else ""
        level = encryption.decrypt_str(student_row["level_enc"]) if student_row["level_enc"] else ""
    # Compose prompt for GPT
    prompt = (f"Сгенерируй учебный план по предмету {subject or 'N/A'}, уровень {level or 'N/A'}, учитывая: {description}. "
              f"Предоставь план как список тем или занятий.")
    messages = [{"role": "user", "content": prompt}]
    # Choose model based on user plan
    user = await db.get_user(user_id)
    model = "gpt-3.5-turbo"
    if user and user["plan"] == "premium":
        model = "gpt-4"  # use GPT-4 for premium users
    # Ask GPT
    answer = await gpt_service.ask_gpt(messages, model=model)
    plan_text = answer.strip() if answer else "(Нет ответа)"
    # Try to generate PDF
    pdf_path = latex_service.generate_plan_pdf(plan_text)
    file_url = None
    file_data_b64 = None
    # If user has Yandex Disk, upload there
    if user and user["ydisk_token_enc"]:
        token = encryption.decrypt_str(user["ydisk_token_enc"])
        if token:
            # Use a default remote path
            remote_path = f"AI_Tutor/Plan_{student_id}.pdf"
            success = await storage_service.upload_to_yadisk(token, pdf_path, remote_path) if pdf_path else False
            if success:
                file_url = "yadisk"
    # If no Yandex Disk or upload failed, we will return file content (base64) to send via Telegram
    if file_url is None and pdf_path:
        # Read file and encode to base64
        import base64
        with open(pdf_path, "rb") as f:
            file_data_b64 = base64.b64encode(f.read()).decode('utf-8')
    # Increment usage count
    await db.increment_usage(user_id)
    # Prepare result message
    result = {
        "type": "plan",
        "user_id": user_id,
        "student_id": student_id,
        "plan_text": plan_text,
        "file_url": file_url
    }
    if file_data_b64:
        result["file"] = file_data_b64
    return result
