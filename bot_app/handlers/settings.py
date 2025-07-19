# bot_app/handlers/settings.py

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters.state import StateFilter  # <--- импортируем StateFilter

from bot_app import database
from bot_app.keyboards import settings as settings_kb

import bcrypt

router = Router()

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
    user = await database.db.get_user_by_tg_id(callback.from_user.id)
    lang = user["language"] if user else "RU"
    text = "Настройки профиля:" if lang == "RU" else "Profile Settings:"
    await callback.message.edit_text(text, reply_markup=settings_kb.settings_menu_kb(lang))

@router.callback_query(F.data == "change_name")
async def cb_change_name(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ChangeNameFSM.waiting_for_name)
    await callback.message.edit_text("Введите новое имя:")

# Здесь используем StateFilter, а не напрямую ChangeNameFSM.waiting_for_name
@router.message(StateFilter(ChangeNameFSM.waiting_for_name))
async def process_change_name(message: Message, state: FSMContext):
    new_name = message.text.strip()
    if not new_name:
        await message.reply("Имя не может быть пустым. Введите новое имя:")
        return
    await database.db.update_user_name(message.from_user.id, new_name)
    await message.answer("Имя обновлено ✅")
    await state.clear()

    user = await database.db.get_user_by_tg_id(message.from_user.id)
    lang = user["language"] if user else "RU"
    text = "Настройки профиля:" if lang == "RU" else "Profile Settings:"
    await message.answer(text, reply_markup=settings_kb.settings_menu_kb(lang))

# Аналогично для смены пароля и токена Яндекс.Диска:
@router.callback_query(F.data == "change_password")
async def cb_change_password(callback: CallbackQuery, state: FSMContext):
    user = await database.db.get_user_by_tg_id(callback.from_user.id)
    if user and not user["password_hash"]:
        await state.set_state(ChangePasswordFSM.waiting_for_new)
        await callback.message.edit_text("Установите новый пароль:")
    else:
        await state.set_state(ChangePasswordFSM.waiting_for_old)
        await callback.message.edit_text("Введите текущий пароль:")

@router.message(StateFilter(ChangePasswordFSM.waiting_for_old))
async def process_old_password(message: Message, state: FSMContext):
    old_pass = message.text.strip()
    user = await database.db.get_user_by_tg_id(message.from_user.id)
    if not user or not user["password_hash"]:
        await message.answer("Пароль не установлен.")
        await state.clear()
        return
    if not bcrypt.checkpw(old_pass.encode(), user["password_hash"].encode()):
        await message.reply("Неверный текущий пароль. Попробуйте снова:")
        return
    await state.set_state(ChangePasswordFSM.waiting_for_new)
    await message.answer("Введите новый пароль:")

@router.message(StateFilter(ChangePasswordFSM.waiting_for_new))
async def process_new_password(message: Message, state: FSMContext):
    new_pass = message.text.strip()
    if not new_pass:
        await message.reply("Пароль не может быть пустым. Введите новый пароль:")
        return
    await database.db.update_user_password(message.from_user.id, bcrypt.hashpw(new_pass.encode(), bcrypt.gensalt()).decode())
    await message.answer("Пароль обновлён ✅")
    await state.clear()

    user = await database.db.get_user_by_tg_id(message.from_user.id)
    lang = user["language"] if user else "RU"
    text = "Настройки профиля:" if lang == "RU" else "Profile Settings:"
    await message.answer(text, reply_markup=settings_kb.settings_menu_kb(lang))

@router.callback_query(F.data == "set_ydisk_token")
async def cb_set_token(callback: CallbackQuery, state: FSMContext):
    await state.set_state(YandexTokenFSM.waiting_for_token)
    await callback.message.edit_text("Введите токен Яндекс.Диска:")

@router.message(StateFilter(YandexTokenFSM.waiting_for_token))
async def process_token(message: Message, state: FSMContext):
    token = message.text.strip()
    await database.db.update_user_ydisk_token(message.from_user.id, token)
    await message.answer("Токен сохранён ✅")
    await state.clear()

    user = await database.db.get_user_by_tg_id(message.from_user.id)
    lang = user["language"] if user else "RU"
    text = "Настройки профиля:" if lang == "RU" else "Profile Settings:"
    await message.answer(text, reply_markup=settings_kb.settings_menu_kb(lang))
