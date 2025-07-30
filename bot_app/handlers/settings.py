from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters.state import StateFilter
from bot_app import database
from bot_app.keyboards import settings as settings_kb

router = Router()

class YandexTokenFSM(StatesGroup):
    waiting_for_token = State()
    editing_token = State()

@router.callback_query(F.data == "settings")
async def cb_settings(callback: CallbackQuery):
    user = await database.db.get_user_by_tg_id(callback.from_user.id)
    lang = user["language"] if user else "RU"
    text = "Настройки профиля:" if lang == "RU" else "Profile Settings:"
    await callback.message.edit_text(text, reply_markup=settings_kb.settings_menu_kb(lang))

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

@router.callback_query(F.data == "dismiss_disk_prompt")
async def cb_dismiss_prompt(callback: CallbackQuery):
    await database.db.set_user_disk_prompt_disabled(callback.from_user.id)
    await callback.answer("Ок, больше не будем напоминать.\nНо знайте что всегда можете добавить его в соответствующем меню настроек", show_alert=False)

@router.callback_query(F.data == "delete_account")
async def cb_delete_account(callback: CallbackQuery):
    await database.db.delete_user(callback.from_user.id)
    await callback.message.edit_text("Ваш аккаунт и все данные удалены.")

@router.callback_query(F.data == "edit_ydisk_token")
async def cb_edit_token(callback: CallbackQuery, state: FSMContext):
    await state.set_state(YandexTokenFSM.editing_token)
    await callback.message.edit_text("🔐 *Подключение Яндекс.Диска*\n\n"
        "Чтобы подключить Яндекс.Диск и загружать туда материалы, выполните следующие шаги:\n\n"
        "Ты можешь прямо сейчас получить OAuth токен на сайте Яндекса:\n"
        "🔗 https://yandex.ru/dev/disk/poligon/ \n"
        "Перейди по ссылке.\n"
        "Нажми Получить OAuth-токен\n"
        "Авторизуйся под своей учёткой.\n"
        "Скопируй токен — и вставь в бота\n"
        "⚠️ Такой токен действителен до его отзыва вручную.\n")

@router.message(StateFilter(YandexTokenFSM.editing_token))
async def process_edit_token(message: Message, state: FSMContext):
    token = message.text.strip()
    await database.db.update_user_ydisk_token(message.from_user.id, token)
    await message.answer("Новый токен сохранён ✅")
    await state.clear()

    user = await database.db.get_user_by_tg_id(message.from_user.id)
    lang = user["language"] if user else "RU"
    text = "Настройки профиля:" if lang == "RU" else "Profile Settings:"
    await message.answer(text, reply_markup=settings_kb.settings_menu_kb(lang))
