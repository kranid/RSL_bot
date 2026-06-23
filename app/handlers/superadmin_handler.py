from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from core.database.database_helper import DatabaseHelper
from core.utils import validate_tg_id_format
from exceptions.database_exceptions import UserNotFoundException
from keyboards.inline_keyboards import (
    confirm_add_admin_role_keyboard,
    confirm_delete_admin_keyboard,
)
from managers.message_manager import TypeStates


superadmin_router = Router()


@superadmin_router.message(Command("add_admin"))
async def add_admin_handler(message: Message, state: FSMContext) -> None:
    await state.set_state(TypeStates.add_admin)
    await message.answer(
        text="Введите Telegram id пользователя, которому необходимо "
        "выдать роль 'admin'"
    )


@superadmin_router.callback_query(F.data == "confirm_add_admin_yes")
async def confirm_add_admin_yes_handler(
    callback: CallbackQuery, state: FSMContext
) -> None:
    tg_id_for_role:str|None = (await state.get_data()).get("tg_id_for_role")
    assert tg_id_for_role is not None
    await DatabaseHelper.instance().add_user_or_update(
        int(tg_id_for_role), username=None, role="admin", manual_flg=True
    )
    assert isinstance(callback.message, Message)
    await callback.message.answer("Роль 'admin' выдана")
    await state.clear()


@superadmin_router.callback_query(F.data == "confirm_add_admin_no")
async def confirm_add_admin_no_handler(
    callback: CallbackQuery, state: FSMContext
) -> None:
    assert isinstance(callback.message, Message)
    await callback.message.answer("Роль 'admin' не была выдана")
    await state.clear()


@superadmin_router.message(Command("delete_admin"))
async def delete_admin_handler(message: Message, state: FSMContext) -> None:
    await state.set_state(TypeStates.delete_admin)
    await message.answer(
        text="Введите Telegram id пользователя, у которого необходимо забрать "
        "роль 'admin'"
    )


@superadmin_router.callback_query(F.data == "confirm_delete_admin_yes")
async def confirm_delete_admin_yes_handler(
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
            await DatabaseHelper.instance().add_user_or_update(
                tg_id=int(tg_id), role="user", manual_flg=True
            )
        except UserNotFoundException:
            await callback.message.answer(f"Пользователь {tg_id} не найден")
        else:
            await callback.message.answer(
                f"Пользователю {tg_id} была установлена роль 'user'"
            )
            await state.clear()


@superadmin_router.callback_query(F.data == "confirm_delete_user_no")
async def confirm_delete_user_no_handler(
    callback: CallbackQuery, state: FSMContext
) -> None:
    assert isinstance(callback.message, Message)
    await callback.message.answer("Роль 'user' осталась у пользователя")
    await state.clear()


@superadmin_router.message(TypeStates.add_admin)
async def pass_tg_id_to_add_admin_handler(
    message: Message, state: FSMContext
) -> None:
    if message.text:
        tg_id_for_role: str = message.text
        if not validate_tg_id_format(tg_id_for_role):
            await message.answer(
                "Telegram id должен быть числом. Попробуйте выполнить команду еще раз."
            )
            await state.clear()
        else:
            tg_id_for_role_int: int = int(tg_id_for_role)
            await state.update_data(tg_id_for_role=tg_id_for_role_int)
            await message.answer(
                "Подтвердите, что необходимо выдать роль 'admin' "
                f"пользователю {tg_id_for_role}",
                reply_markup=confirm_add_admin_role_keyboard,
            )
    else:
        await message.answer("Необходимо ввести Telegram id пользователя")


@superadmin_router.message(TypeStates.delete_admin)
async def pass_tg_id_to_delete_admin_handler(
    message: Message, state: FSMContext
) -> None:
    if message.text:
        tg_id: str = message.text
        if not validate_tg_id_format(tg_id):
            await message.answer(
                "Telegram id должен быть числом. Попробуйте выполнить команду еще раз."
            )
            await state.clear()
        else:
            tg_id_int: int = int(tg_id)
            await state.update_data(tg_id=tg_id_int)
            await message.answer(
                "Подтвердите, что необходимо забрать роль 'admin' "
                f"у пользователя {tg_id}",
                reply_markup=confirm_delete_admin_keyboard,
            )
    else:
        await message.answer("Необходимо ввести Telegram id пользователя")
