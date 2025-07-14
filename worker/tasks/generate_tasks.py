from worker import db
from worker.utils import encryption
from worker.services import gpt_service, latex_service, storage_service

async def handle_generate_tasks(task):
    user_id = task["user_id"]
    student_id = task["student_id"]
    description = task["description"]
    # Fetch student info
    student_row = await db.get_student(student_id)
    subject = ""
    level = ""
    if student_row:
        subject = encryption.decrypt_str(student_row["subject_enc"]) if student_row["subject_enc"] else ""
        level = encryption.decrypt_str(student_row["level_enc"]) if student_row["level_enc"] else ""
    prompt = (f"Сгенерируй набор учебных задач по предмету {subject or 'N/A'}, уровень {level or 'N/A'}, учитывая: {description}. "
              "Приведи задачи и решения, разделяя части символом '@'.")
    messages = [{"role": "user", "content": prompt}]
    user = await db.get_user(user_id)
    model = "gpt-3.5-turbo"
    if user and user["plan"] == "premium":
        model = "gpt-4"
    answer = await gpt_service.ask_gpt(messages, model=model)
    output = answer or ""
    # Split tasks and solutions by '@'
    parts = output.split('@') if '@' in output else [output]
    # Prepare a text with tasks (without solutions) for quick view
    tasks_text = ""
    for i in range(0, len(parts), 2):
        task_text = parts[i].strip()
        if task_text:
            tasks_text += f"{i//2 + 1}. {task_text}\n"
    # Generate PDF of tasks + solutions
    pdf_path = latex_service.generate_tasks_pdf(parts)
    file_url = None
    file_data_b64 = None
    if user and user["ydisk_token_enc"]:
        token = encryption.decrypt_str(user["ydisk_token_enc"])
        if token:
            remote_path = f"AI_Tutor/Tasks_{student_id}.pdf"
            success = await storage_service.upload_to_yadisk(token, pdf_path, remote_path) if pdf_path else False
            if success:
                file_url = "yadisk"
    if file_url is None and pdf_path:
        import base64
        with open(pdf_path, "rb") as f:
            file_data_b64 = base64.b64encode(f.read()).decode('utf-8')
    await db.increment_usage(user_id)
    result = {
        "type": "tasks",
        "user_id": user_id,
        "student_id": student_id,
        "tasks_text": tasks_text,
        "file_url": file_url
    }
    if file_data_b64:
        result["file"] = file_data_b64
    return result
