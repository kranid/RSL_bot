from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


add_video_description = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="🔙 Назад"),
        ],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
    input_field_placeholder="Добавьте описание к видео",
)
