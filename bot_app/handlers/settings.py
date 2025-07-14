from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bot_app import database
from bot_app.keyboards import settings as settings_kb

import bcrypt

router = Router()

# FSM states for changing name and password, and Yandex token
class ChangeNameFSM(StatesGroup):
    waiting_for_name = State()

class ChangePasswordFSM(StatesGroup):
    waiting_for_old = State()
    waiting_for_new = State()
    waiting_for_confirm = State()

class YandexTokenFSM(StatesGroup):
    waiting_for_token = State()

@router.callback_query(F.data == "settings")
async def cb_settings(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = await database.db.get_user_by_tg_id(user_id)
    lang = user["language"] if user else "RU"
    text = "Настройки профиля:" if lang == "RU" else "Profile Settings:"
    await callback.message.edit_text(text, reply_markup=settings_kb.settings_menu_kb(lang))

@router.callback_query(F.data == "change_name")
async def cb_change_name(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ChangeNameFSM.waiting_for_name)
    await callback.message.edit_text("Введите новое имя:")

@router.message(ChangeNameFSM.waiting_for_name)
async def process_change_name(message: Message, state: FSMContext):
    new_name = message.text.strip()
    if not new_name:
        await message.reply("Имя не может быть пустым. Введите новое имя:")
        return
    await database.db.update_user_name(message.from_user.id, new_name)
    await message.answer("Имя обновлено ✅")
    await state.clear()
    # Return to settings menu
    user = await database.db.get_user_by_tg_id(message.from_user.id)
    text = "Настройки профиля:"
    await message.answer(text, reply_markup=settings_kb.settings_menu_kb(user["language"] if user else "RU"))

@router.callback_query(F.data == "change_password")
async def cb_change_password(callback: CallbackQuery, state: FSMContext):
    user = await database.db.get_user_by_tg_id(callback.from_user.id)
    # If no password set yet (empty hash), skip old password
    if user and (not user["password_hash"] or user["password_hash"] == ""):
        # No existing password, go directly to new password
        await state.set_state(ChangePasswordFSM.waiting_for_new)
        await callback.message.edit_text("Установите новый пароль:")
    else:
        await state.set_state(ChangePasswordFSM.waiting_for_old)
        await callback.message.edit_text("Введите текущий пароль:")

@router.message(ChangePasswordFSM.waiting_for_old)
async def process_old_password(message: Message, state: FSMContext):
    old_pass = message.text.strip()
    # Check old password
    user = await database.db.get_user_by_tg_id(message.from_user.id)
    if not user or not user["password_hash"]:
        await message.answer("Пароль не установлен.")
        await state.clear()
        return
    # Verify old password hash
    try:
        if not bcrypt.checkpw(old_pass.encode('utf-8'), user["password_hash"].encode('utf-8')):
            await message.reply("Неверный текущий пароль. Попробуйте снова:")
            return
    except Exception:
        await message.reply("Ошибка проверки пароля.")
        return
    # Ask for new password
    await state.set_state(ChangePasswordFSM.waiting_for_new)
    await message.answer("Введите новый пароль:")

@router.message(ChangePasswordFSM.waiting_for_new)
async def process_new_password(message: Message, state: FSMContext):
    new_pass = message.text.strip()
    if len(new_pass) < 4:
        await message.reply("Пароль слишком короткий. Введите другой:")
        return
    # Temporarily store new password (hashed? we'll confirm first then hash)
    await state.update_data(new_password=new_pass)
    await state.set_state(ChangePasswordFSM.waiting_for_confirm)
    await message.answer("Повторите новый пароль:")

@router.message(ChangePasswordFSM.waiting_for_confirm)
async def process_confirm_password(message: Message, state: FSMContext):
    confirm_pass = message.text.strip()
    data = await state.get_data()
    new_pass = data.get("new_password")
    if confirm_pass != new_pass:
        await message.reply("Пароли не совпадают. Начните заново командой /cancel.")
        await state.clear()
        return
    # Hash the new password and save
    hashed = bcrypt.hashpw(new_pass.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    await database.db.update_user_password(message.from_user.id, hashed)
    await message.answer("Пароль обновлён ✅")
    await state.clear()
    # Return to settings
    user = await database.db.get_user_by_tg_id(message.from_user.id)
    text = "Настройки профиля:"
    await message.answer(text, reply_markup=settings_kb.settings_menu_kb(user["language"] if user else "RU"))

@router.callback_query(F.data == "toggle_notifications")
async def cb_toggle_notifications(callback: CallbackQuery):
    user = await database.db.get_user_by_tg_id(callback.from_user.id)
    if not user:
        return
    current = user["notifications"]
    new_val = not current
    await database.db.update_user_notifications(callback.from_user.id, new_val)
    # Inform user
    notify_text = "Уведомления включены ✅" if new_val else "Уведомления выключены ❌"
    await callback.answer(notify_text, show_alert=True)
    # Optionally update settings menu or keep it same

@router.callback_query(F.data == "change_language")
async def cb_change_language(callback: CallbackQuery):
    await callback.message.edit_text("Выберите язык / Select language:", reply_markup=settings_kb.language_choice_kb())

@router.callback_query(F.data.startswith("lang:"))
async def cb_set_language(callback: CallbackQuery):
    lang = callback.data.split(":")[1]  # "RU" or "EN"
    await database.db.update_user_language(callback.from_user.id, lang)
    msg = "Язык интерфейса сменён." if lang == "RU" else "Language has been changed."
    await callback.message.edit_text(msg, reply_markup=settings_kb.back_button("← Back" if lang=="EN" else "← Назад", "back:main"))

@router.callback_query(F.data == "yandex_disk")
async def cb_yandex_disk(callback: CallbackQuery, state: FSMContext):
    user = await database.db.get_user_by_tg_id(callback.from_user.id)
    if user and user["ydisk_token_enc"]:
        # Already has token
        await state.set_state(YandexTokenFSM.waiting_for_token)
        await callback.message.edit_text("Обновить токен Яндекс.Диска:\n(отправьте новый токен)")
    else:
        await state.set_state(YandexTokenFSM.waiting_for_token)
        await callback.message.edit_text("Отправьте OAuth-токен Яндекс.Диска для интеграции:")

@router.message(YandexTokenFSM.waiting_for_token)
async def process_yandex_token(message: Message, state: FSMContext):
    token = message.text.strip()
    if not token:
        await message.reply("Токен не должен быть пустым.")
        return
    # Save encrypted token in DB
    await database.db.update_user_ydisk_token(message.from_user.id, token)
    await message.answer("Интеграция с Яндекс.Диском выполнена ✅")
    await state.clear()
    # Return to settings menu
    user = await database.db.get_user_by_tg_id(message.from_user.id)
    text = "Настройки профиля:"
    await message.answer(text, reply_markup=settings_kb.settings_menu_kb(user["language"] if user else "RU"))
