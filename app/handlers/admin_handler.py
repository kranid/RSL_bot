import html
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from core.database.database_helper import DatabaseHelper
from core.settings import settings
from core.utils import format_show_users_message, validate_tg_id_format
from exceptions.database_exceptions import (
    CantChangeHigherAccessRole,
    UserAlreadyBannedException,
    UserHasNoRoleException,
    UserNotFoundException,
)
from keyboards.inline_keyboards import (
    confirm_add_user_role_keyboard,
    confirm_ban_keyboard,
    confirm_delete_user_keyboard,
    confirm_unban_keyboard,
)
from managers.message_manager import TypeStates


admin_router = Router()
logger = logging.getLogger(__name__)

PENDING_PAGE_SIZE = 20


@admin_router.message(Command("add_user"))
async def add_user_handler(message: Message, state: FSMContext) -> None:
    await state.set_state(TypeStates.add_user)
    await message.answer(
        text="Введите Telegram id пользователя, которому необходимо "
        "выдать роль 'user'"
    )


@admin_router.callback_query(F.data == "confirm_add_user_yes")
async def confirm_add_user_yes_handler(
    callback: CallbackQuery, state: FSMContext
) -> None:
    tg_id_for_role:str|None = (await state.get_data()).get("tg_id_for_role")
    assert tg_id_for_role is not None
    await DatabaseHelper.instance().add_user_or_update(
        int(tg_id_for_role), username=None, role="user", manual_flg=True
    )
    assert isinstance(callback.message, Message)
    await callback.message.answer("Роль 'user' выдана")
    await state.clear()


@admin_router.callback_query(F.data == "confirm_add_user_no")
async def confirm_add_user_no_handler(
    callback: CallbackQuery, state: FSMContext
) -> None:
    assert isinstance(callback.message, Message)
    await callback.message.answer("Роль 'user' не была выдана")
    await state.clear()


@admin_router.message(Command("show_users"))
async def show_all_users(message: Message) -> None:
    users_list: list[
        tuple[int, str, str, bool]
    ] = await DatabaseHelper.instance().select_users()
    msg = format_show_users_message(users_list)
    await message.answer(text=msg)


@admin_router.message(Command("show_requests"))
async def show_requests_handler(message: Message) -> None:
    pending = await DatabaseHelper.instance().select_pending_users(
        limit=PENDING_PAGE_SIZE
    )
    total = await DatabaseHelper.instance().count_pending_users()
    if not pending:
        await message.answer("Заявок на доступ нет")
        return

    for tg_id, username in pending:
        if username:
            who = f"@{html.escape(username)}"
        else:
            who = f'<a href="tg://user?id={tg_id}">профиль</a>'
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Одобрить",
                        callback_data=f"approve:{tg_id}",
                    ),
                ]
            ]
        )
        await message.answer(f"{who} - <code>{tg_id}</code>", reply_markup=kb)

    shown = len(pending)
    if total > shown:
        await message.answer(
            f"Показаны {shown} из {total}. Одобрите этих и вызовите "
            f"/show_requests снова для следующих."
        )
    else:
        await message.answer(f"Всего заявок: {total}")


@admin_router.message(Command("invite"))
async def invite_handler(message: Message) -> None:
    assert message.bot is not None
    me = await message.bot.get_me()
    link = f"https://t.me/{me.username}?start={settings.tg.invite_code}"
    await message.answer(
        f"Пригласительная ссылка:\n{link}\n\n"
        f"Отправьте её тем, кому нужно выдать доступ. "
        f"Перешедшие по ней получат роль user автоматически."
    )


@admin_router.message(Command("stats"))
async def stats_handler(message: Message) -> None:
    stats = await DatabaseHelper.instance().get_users_stats()
    await message.answer(
        f"Статистика пользователей\n\n"
        f"Всего в базе: {stats['total']}\n\n"
        f"С ролью:\n"
        f"• user: {stats['user']}\n"
        f"• admin: {stats['admin']}\n"
        f"• superadmin: {stats['superadmin']}\n\n"
        f"Ожидают одобрения: {stats['pending']}\n"
        f"Забанено: {stats['banned']}"
    )


@admin_router.callback_query(F.data.startswith("approve:"))
async def approve_request_handler(callback: CallbackQuery, bot: Bot) -> None:
    assert isinstance(callback.message, Message)
    assert callback.from_user is not None
    assert callback.data is not None

    actor_role = await DatabaseHelper.instance().get_user_role(callback.from_user.id)
    if actor_role not in ("admin", "superadmin"):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    try:
        target_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Некорректная заявка", show_alert=True)
        return

    target_data = await DatabaseHelper.instance().select_user_data(target_id)
    if target_data is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    current_role = target_data[2]
    if current_role is not None:
        await callback.answer("У пользователя уже есть роль")
        return
    if await DatabaseHelper.instance().is_banned(target_id):
        await callback.answer("Пользователь заблокирован", show_alert=True)
        return

    await DatabaseHelper.instance().add_user_or_update(
        target_id, username=None, role="user", manual_flg=True
    )

    welcome_text = (
        "Добро пожаловать! \nЯ бот для перевода русского жестового языка.\n"
        "Запишите кружочек или отправьте видеофайл для тестирования ML модели "
    )
    notification_sent = True
    try:
        await bot.send_message(target_id, welcome_text)
    except Exception:
        notification_sent = False
        logger.warning(
            "failed to send approval welcome message to user %s",
            target_id,
            exc_info=True,
        )

    if notification_sent:
        await callback.message.edit_text(
            f"✅ Одобрен: <code>{target_id}</code> - выдана роль user"
        )
        await callback.answer("Готово")
    else:
        await callback.message.edit_text(
            f"✅ Одобрен: <code>{target_id}</code> - выдана роль user. "
            f"Уведомление пользователю отправить не удалось."
        )
        await callback.answer(
            "Одобрено, но уведомление не отправлено",
            show_alert=True,
        )


@admin_router.message(Command("delete_user"))
async def delete_user_handler(message: Message, state: FSMContext) -> None:
    await state.set_state(TypeStates.delete_user)
    await message.answer(
        text="Введите Telegram id пользователя, у которого необходимо "
        "забрать роль 'user'"
    )


@admin_router.callback_query(F.data == "confirm_delete_user_yes")
async def confirm_delete_user_yes_handler(
    callback: CallbackQuery, state: FSMContext
) -> None:
    tg_id:str|None = (await state.get_data()).get("tg_id")
    assert isinstance(callback.message, Message)
    assert tg_id is not None
    assert callback.message.from_user is not None
    if tg_id == callback.message.from_user.id:
        await callback.message.answer(
            "Администратор не может изменять роль у самого себя"
        )
    else:
        try:
            await DatabaseHelper.instance().delete_user(int(tg_id))
        except UserNotFoundException:
            await callback.message.answer(
                f"Пользователь {tg_id} не найден. Попробуйте ввести "
                "Telegram id еще раз"
            )
        except CantChangeHigherAccessRole:
            await callback.message.answer(
                f"У пользователя {tg_id} другая роль. "
                "Администратор не может изменить такую же или "
                "вышестоящую роль"
            )
            await state.clear()
        else:
            await callback.message.answer(
                f"Пользователь {tg_id} был лишен всех ролей"
            )
            await state.clear()


@admin_router.callback_query(F.data == "confirm_delete_user_no")
async def confirm_delete_user_no_handler(
    callback: CallbackQuery, state: FSMContext
) -> None:
    assert isinstance(callback.message, Message)
    await callback.message.answer("Роль 'user' осталась у " "пользователя")
    await state.clear()


@admin_router.message(TypeStates.add_user)
async def pass_tg_id_to_add_user_handler(
    message: Message, state: FSMContext
) -> None:
    if message.text:
        tg_id_for_role: str = message.text
        if not validate_tg_id_format(tg_id_for_role):
            await message.answer(
                "Telegram id должен быть числом. Попробуйте выполнить команду еще раз"
            )
            await state.clear()
        else:
            tg_id_for_role_int: int = int(tg_id_for_role)
            await state.update_data(tg_id_for_role=tg_id_for_role_int)
            await message.answer(
                "Подтвердите, что необходимо выдать роль 'user' "
                f"пользователю {tg_id_for_role}",
                reply_markup=confirm_add_user_role_keyboard,
            )
    else:
        await message.answer("Необходимо ввести Telegram id пользователя")


@admin_router.message(TypeStates.delete_user)
async def pass_tg_id_to_delete_user_handler(
    message: Message, state: FSMContext
) -> None:
    if message.text:
        tg_id: str = message.text
        if not validate_tg_id_format(tg_id):
            await message.answer(
                "Telegram id должен быть числом. Попробуйте выполнить команду еще раз"
            )
            await state.clear()
        else:
            tg_id_int: int = int(tg_id)
            await state.update_data(tg_id=tg_id_int)
            await message.answer(
                "Подтвердите, что необходимо забрать роль 'user' "
                f"у пользователя {tg_id}",
                reply_markup=confirm_delete_user_keyboard,
            )
    else:
        await message.answer("Необходимо ввести Telegram id пользователя")


@admin_router.message(Command("ban"))
async def ban_handler(message: Message, state: FSMContext) -> None:
    await state.set_state(TypeStates.ban)
    await message.answer(
        text="Введите Telegram id пользователя, которого необходимо заблокировать"
    )


@admin_router.message(TypeStates.ban)
async def pass_tg_id_to_ban_handler(
    message: Message, state: FSMContext
) -> None:
    if message.text:
        tg_id: str = message.text
        if not validate_tg_id_format(tg_id):
            await message.answer(
                "Telegram id должен быть числом. Попробуйте выполнить команду еще раз"
            )
            await state.clear()
        else:
            tg_id_int: int = int(tg_id)
            db_data = await DatabaseHelper.instance().select_user_data(tg_id_int)
            if db_data is None:
                await message.answer(
                    f"Пользователь {tg_id} не найден. Попробуйте ввести Telegram id еще раз"
                )
                await state.clear()
            elif await DatabaseHelper.instance().is_banned(tg_id_int):
                await message.answer(f"Пользователь {tg_id} уже заблокирован")
                await state.clear()
            elif db_data[2] is None:
                await message.answer(
                    "Пользователю не выдана роль, его нельзя заблокировать"
                )
                await state.clear()
            elif db_data[2] in ("admin", "superadmin"):
                await message.answer(
                    "Пользователей с ролью admin или superadmin нельзя заблокировать"
                )
                await state.clear()
            else:
                await state.update_data(tg_id=tg_id_int)
                await message.answer(
                    f"Подтвердите, что необходимо заблокировать пользователя {tg_id}",
                    reply_markup=confirm_ban_keyboard,
                )
    else:
        await message.answer("Необходимо ввести Telegram id пользователя")


@admin_router.callback_query(F.data == "confirm_ban_yes")
async def confirm_ban_yes_handler(
    callback: CallbackQuery, state: FSMContext
) -> None:
    tg_id:int|None = (await state.get_data()).get("tg_id")
    assert isinstance(callback.message, Message)
    assert tg_id is not None
    try:
        await DatabaseHelper.instance().ban_user(tg_id)
    except UserNotFoundException:
        await callback.message.answer(
            f"Пользователь {tg_id} не найден. Попробуйте ввести Telegram id еще раз"
        )
    except UserAlreadyBannedException:
        await callback.message.answer(f"Пользователь {tg_id} уже заблокирован")
    except UserHasNoRoleException:
        await callback.message.answer(
            "Пользователю не выдана роль, его нельзя заблокировать"
        )
    except CantChangeHigherAccessRole:
        await callback.message.answer(
            "Пользователей с ролью admin или superadmin нельзя заблокировать"
        )
    else:
        await callback.message.answer(f"Пользователь {tg_id} заблокирован")
    await state.clear()


@admin_router.callback_query(F.data == "confirm_ban_no")
async def confirm_ban_no_handler(
    callback: CallbackQuery, state: FSMContext
) -> None:
    assert isinstance(callback.message, Message)
    await callback.message.answer("Пользователь не был заблокирован")
    await state.clear()


@admin_router.message(Command("unban"))
async def unban_handler(message: Message, state: FSMContext) -> None:
    await state.set_state(TypeStates.unban)
    await message.answer(
        text="Введите Telegram id пользователя, которого необходимо разблокировать"
    )


@admin_router.message(TypeStates.unban)
async def pass_tg_id_to_unban_handler(
    message: Message, state: FSMContext
) -> None:
    if message.text:
        tg_id: str = message.text
        if not validate_tg_id_format(tg_id):
            await message.answer(
                "Telegram id должен быть числом. Попробуйте выполнить команду еще раз"
            )
            await state.clear()
        else:
            tg_id_int: int = int(tg_id)
            db_data = await DatabaseHelper.instance().select_user_data(tg_id_int)
            if db_data is None:
                await message.answer(
                    f"Пользователь {tg_id} не найден. Попробуйте ввести Telegram id еще раз"
                )
                await state.clear()
            elif not await DatabaseHelper.instance().is_banned(tg_id_int):
                await message.answer(f"Пользователь {tg_id} не заблокирован")
                await state.clear()
            else:
                await state.update_data(tg_id=tg_id_int)
                await message.answer(
                    f"Подтвердите, что необходимо разблокировать пользователя {tg_id}",
                    reply_markup=confirm_unban_keyboard,
                )
    else:
        await message.answer("Необходимо ввести Telegram id пользователя")


@admin_router.callback_query(F.data == "confirm_unban_yes")
async def confirm_unban_yes_handler(
    callback: CallbackQuery, state: FSMContext
) -> None:
    tg_id:int|None = (await state.get_data()).get("tg_id")
    assert isinstance(callback.message, Message)
    assert tg_id is not None
    try:
        await DatabaseHelper.instance().unban_user(tg_id)
    except UserNotFoundException:
        await callback.message.answer(
            f"Пользователь {tg_id} не найден. Попробуйте ввести Telegram id еще раз"
        )
    else:
        await callback.message.answer(f"Пользователь {tg_id} разблокирован")
    await state.clear()


@admin_router.callback_query(F.data == "confirm_unban_no")
async def confirm_unban_no_handler(
    callback: CallbackQuery, state: FSMContext
) -> None:
    assert isinstance(callback.message, Message)
    await callback.message.answer("Пользователь не был разблокирован")
    await state.clear()
