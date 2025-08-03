from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters.state import StateFilter

from bot_app import database
from bot_app.keyboards import settings as settings_kb
from bot_app.keyboards.main_menu import bottom_menu_settings_kb, bottom_menu_kb

router = Router()

class YandexTokenFSM(StatesGroup):
    waiting_for_token = State()
    editing_token = State()

# --- Обработка кнопки "Настройки" из нижнего меню
@router.message(F.text == "⚙️ Настройки")
async def msg_settings_menu(message: Message):
    user = await database.db.get_user_by_tg_id(message.from_user.id)
    lang = user["language"] if user else "RU"
    text = "Настройки профиля:" if lang == "RU" else "Profile Settings:"
    await message.answer(text, reply_markup=bottom_menu_settings_kb(lang))

# --- Обработка кнопки "Настройки" из CallbackQuery (для совместимости)
@router.callback_query(F.data == "settings")
async def cb_settings(callback: CallbackQuery):
    user = await database.db.get_user_by_tg_id(callback.from_user.id)
    lang = user["language"] if user else "RU"
    text = "Настройки профиля:" if lang == "RU" else "Profile Settings:"
    await callback.message.edit_text(text, reply_markup=bottom_menu_settings_kb(lang))

# --- Установка Яндекс.Токена
@router.message(F.text == "🔗 Подключить Яндекс.Диск")
async def msg_set_token(message: Message, state: FSMContext):
    await state.set_state(YandexTokenFSM.waiting_for_token)
    await message.answer("🔐 *Подключение Яндекс.Диска*\n\n"
        "Чтобы подключить Яндекс.Диск и загружать туда материалы, выполните следующие шаги:\n\n"
        "Ты можешь прямо сейчас получить OAuth токен на сайте Яндекса:\n"
        "🔗 https://yandex.ru/dev/disk/poligon/ \n"
        "Перейди по ссылке.\n"
        "Нажми Получить OAuth-токен\n"
        "Авторизуйся под своей учёткой.\n"
        "Скопируй токен — и вставь в бота\n"
        "⚠️ Такой токен действителен до его отзыва вручную.\n")

@router.callback_query(F.data == "set_ydisk_token")
async def cb_set_token(callback: CallbackQuery, state: FSMContext):
    await state.set_state(YandexTokenFSM.waiting_for_token)
    await callback.message.edit_text("🔐 *Подключение Яндекс.Диска*\n\n"
        "Чтобы подключить Яндекс.Диск и загружать туда материалы, выполните следующие шаги:\n\n"
        "Ты можешь прямо сейчас получить OAuth токен на сайте Яндекса:\n"
        "🔗 https://yandex.ru/dev/disk/poligon/ \n"
        "Перейди по ссылке.\n"
        "Нажми Получить OAuth-токен\n"
        "Авторизуйся под своей учёткой.\n"
        "Скопируй токен — и вставь в бота\n"
        "⚠️ Такой токен действителен до его отзыва вручную.\n")

@router.message(StateFilter(YandexTokenFSM.waiting_for_token))
async def process_token(message: Message, state: FSMContext):
    token = message.text.strip()
    await database.db.update_user_ydisk_token(message.from_user.id, token)
    await message.answer("Токен сохранён ✅")
    await state.clear()
    
    # Возвращаемся в меню настроек
    user = await database.db.get_user_by_tg_id(message.from_user.id)
    lang = user["language"] if user else "RU"
    text = "Настройки профиля:" if lang == "RU" else "Profile Settings:"
    await message.answer(text, reply_markup=bottom_menu_settings_kb(lang))

# --- Отключить напоминание про Диск
@router.callback_query(F.data == "dismiss_disk_prompt")
async def cb_dismiss_prompt(callback: CallbackQuery):
    await database.db.set_user_disk_prompt_disabled(callback.from_user.id)
    await callback.answer("Ок, больше не будем напоминать.\nНо знайте что всегда можете добавить его в соответствующем меню настроек", show_alert=False)

# --- Удаление аккаунта
@router.callback_query(F.data == "delete_account")
async def cb_delete_account(callback: CallbackQuery):
    await database.db.delete_user(callback.from_user.id)
    await callback.message.edit_text("Ваш аккаунт и все данные удалены.")

# --- Редактирование Яндекс токена
@router.message(F.text == "✏️ Изменить токен Я.Диска")
async def msg_edit_token(message: Message, state: FSMContext):
    await state.set_state(YandexTokenFSM.editing_token)
    await message.answer("🔐 *Изменение токена Яндекс.Диска*\n\n"
        "🔗 https://yandex.ru/dev/disk/poligon/ \n"
        "Скопируйте новый токен и отправьте его сюда.")

@router.callback_query(F.data == "edit_ydisk_token")
async def cb_edit_token(callback: CallbackQuery, state: FSMContext):
    await state.set_state(YandexTokenFSM.editing_token)
    await callback.message.edit_text("🔐 *Изменение токена Яндекс.Диска*\n\n"
        "🔗 https://yandex.ru/dev/disk/poligon/ \n"
        "Скопируйте новый токен и отправьте его сюда.")

@router.message(StateFilter(YandexTokenFSM.editing_token))
async def process_edit_token(message: Message, state: FSMContext):
    token = message.text.strip()
    await database.db.update_user_ydisk_token(message.from_user.id, token)
    await message.answer("Новый токен сохранён ✅")
    await state.clear()

    # Возвращаемся в меню настроек
    user = await database.db.get_user_by_tg_id(message.from_user.id)
    lang = user["language"] if user else "RU"
    text = "Настройки профиля:" if lang == "RU" else "Profile Settings:"
    await message.answer(text, reply_markup=bottom_menu_settings_kb(lang))

# --- Возврат в главное меню
@router.message(F.text == "← Главное меню")
async def back_to_main_from_settings(message: Message):
    """Возврат в главное меню из настроек"""
    first_name = message.from_user.first_name or ""
    user = await database.db.get_user_by_tg_id(message.from_user.id)
    lang = user["language"] if user else "RU"
    welcome = (
        f"🤖 AI Assistant for Tutors\nWelcome, {first_name}!\nWhat shall we do today?"
        if lang == "EN"
        else f"🤖 ИИ-Ассистент для Репетитора\nДобро пожаловать, {first_name}!\nЧем займёмся сегодня?"
    )
    await message.answer(welcome, reply_markup=bottom_menu_kb(lang))

# --- Обработчики для английского языка ---
@router.message(F.text == "🔗 Connect Yandex.Disk")
async def msg_set_token_en(message: Message, state: FSMContext):
    await state.set_state(YandexTokenFSM.waiting_for_token)
    await message.answer("🔐 *Connecting Yandex.Disk*\n\n"
        "To connect Yandex.Disk and upload materials there, follow these steps:\n\n"
        "You can get an OAuth token right now on the Yandex website:\n"
        "🔗 https://yandex.ru/dev/disk/poligon/ \n"
        "Go to the link.\n"
        "Click Get OAuth Token\n"
        "Authorize under your account.\n"
        "Copy the token — and paste it into the bot\n"
        "⚠️ Such a token is valid until manually revoked.\n")

@router.message(F.text == "✏️ Edit Yandex.Disk Token")
async def msg_edit_token_en(message: Message, state: FSMContext):
    await state.set_state(YandexTokenFSM.editing_token)
    await message.answer("🔐 *Changing Yandex.Disk Token*\n\n"
        "🔗 https://yandex.ru/dev/disk/poligon/ \n"
        "Copy the new token and send it here.")

@router.message(F.text == "← Back to Main")
async def back_to_main_from_settings_en(message: Message):
    """Возврат в главное меню из настроек на английском"""
    first_name = message.from_user.first_name or ""
    user = await database.db.get_user_by_tg_id(message.from_user.id)
    lang = user["language"] if user else "RU"
    welcome = (
        f"🤖 AI Assistant for Tutors\nWelcome, {first_name}!\nWhat shall we do today?"
        if lang == "EN"
        else f"🤖 ИИ-Ассистент для Репетитора\nДобро пожаловать, {first_name}!\nЧем займёмся сегодня?"
    )
    await message.answer(welcome, reply_markup=bottom_menu_kb(lang))
