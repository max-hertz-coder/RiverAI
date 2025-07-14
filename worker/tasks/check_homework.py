from worker import db
from worker.utils import encryption
from worker.services import gpt_service, latex_service, storage_service

async def handle_check_homework(task):
    user_id = task["user_id"]
    student_id = task["student_id"]
    solution_text = task.get("solution_text") or ""
    filename = task.get("filename") or ""
    # Get student profile
    student_row = await db.get_student(student_id)
    subject = ""
    level = ""
    if student_row:
        subject = encryption.decrypt_str(student_row["subject_enc"]) if student_row["subject_enc"] else ""
        level = encryption.decrypt_str(student_row["level_enc"]) if student_row["level_enc"] else ""
    # Create GPT prompt for checking homework
    prompt = (f"Проверь решение по предмету {subject or 'N/A'}, уровень {level or 'N/A'}. "
              f"Решения: {solution_text if solution_text else '(файл)'}\n"
              "Дай пояснения к ошибкам и верным решениям, перечисли результаты по каждому пункту.")
    messages = [{"role": "user", "content": prompt}]
    user = await db.get_user(user_id)
    model = "gpt-3.5-turbo"
    if user and user["plan"] == "premium":
        model = "gpt-4"
    answer = await gpt_service.ask_gpt(messages, model=model)
    report_text = answer.strip() if answer else "Не удалось получить ответ от GPT."
    # Generate PDF report
    pdf_path = latex_service.generate_report_pdf(report_text)
    file_url = None
    file_data_b64 = None
    if user and user["ydisk_token_enc"]:
        token = encryption.decrypt_str(user["ydisk_token_enc"])
        if token:
            remote_path = f"AI_Tutor/Report_{student_id}.pdf"
            success = await storage_service.upload_to_yadisk(token, pdf_path, remote_path) if pdf_path else False
            if success:
                file_url = "yadisk"
    if file_url is None and pdf_path:
        import base64
        with open(pdf_path, "rb") as f:
            file_data_b64 = base64.b64encode(f.read()).decode('utf-8')
    await db.increment_usage(user_id)
    result = {
        "type": "check",
        "user_id": user_id,
        "student_id": student_id,
        "report_text": report_text,
        "file_url": file_url
    }
    if file_data_b64:
        result["file"] = file_data_b64
    return result
