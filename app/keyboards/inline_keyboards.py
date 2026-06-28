from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


confirm_add_user_role_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Да", callback_data="confirm_add_user_yes"
            ),
            InlineKeyboardButton(
                text="Нет", callback_data="confirm_add_user_no"
            ),
        ]
    ]
)

confirm_delete_user_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Да", callback_data="confirm_delete_user_yes"
            ),
            InlineKeyboardButton(
                text="Нет", callback_data="confirm_delete_user_no"
            ),
        ]
    ]
)

confirm_add_admin_role_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Да", callback_data="confirm_add_admin_yes"
            ),
            InlineKeyboardButton(
                text="Нет", callback_data="confirm_add_admin_no"
            ),
        ]
    ]
)

confirm_delete_admin_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Да", callback_data="confirm_delete_admin_yes"
            ),
            InlineKeyboardButton(
                text="Нет", callback_data="confirm_delete_admin_no"
            ),
        ]
    ]
)

model_response_actions = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Перегенерация", callback_data="regen")],
    ]
)

confirm_ban_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="Да", callback_data="confirm_ban_yes"),
            InlineKeyboardButton(text="Нет", callback_data="confirm_ban_no"),
        ]
    ]
)

confirm_unban_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="Да", callback_data="confirm_unban_yes"),
            InlineKeyboardButton(text="Нет", callback_data="confirm_unban_no"),
        ]
    ]
)
