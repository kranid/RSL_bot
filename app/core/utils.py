from core.limiter import Decision
from core.settings import settings


def validate_tg_id_format(value: str) -> bool:
    return value.isdigit()


def format_show_users_message(users_list: list[tuple[int, str, str, bool]]) -> str:
    msg = "Пользователи:\n"
    users_list_str = "\n".join(
        [
            f" - TG id: {user_data[0]}"
            f"{f', username {user_data[1]}' if user_data[1] else ''}, "
            f"role {user_data[2]}, "
            f"status {'заблокирован' if user_data[3] else 'активен'}"
            for user_data in users_list
        ]
    )
    return msg + users_list_str


def get_content_type(message):
    if message.text:
        content_type = "text"
    elif message.photo:
        content_type = "photo"
    elif message.video:
        content_type = "video"
    elif message.video_note:
        content_type = "video_note"
    elif message.animation:
        content_type = "GIF"
    elif message.audio:
        content_type = "audio"
    elif message.document:
        content_type = "document"
    elif message.sticker:
        content_type = "sticker"
    elif message.voice:
        content_type = "voice"
    elif message.contact:
        content_type = "contact"
    elif message.location:
        content_type = "location"
    else:
        content_type = "unknown"
    return content_type


def check_valid_content_type(
    content_type: str, valid_content_types: list[str]
) -> bool:
    return content_type in valid_content_types


def check_media_limits(message) -> str | None:
    limits = settings.limits
    if not limits.enabled:
        return None

    media = message.video or message.video_note or message.animation
    if media is None:
        return None

    file_size = getattr(media, "file_size", None)
    if file_size is not None and file_size > limits.max_file_size_mb * 1024 * 1024:
        return f"Видео слишком большое. Максимальный размер — {limits.max_file_size_mb} МБ."

    duration = getattr(media, "duration", None)
    if duration is not None and duration > limits.max_video_duration_seconds:
        return f"Видео слишком длинное. Максимальная длительность — {limits.max_video_duration_seconds} сек."

    return None


def is_admin(user_role:str|None):
    return user_role in ["admin", "superadmin"]

def limiter_reject_text(decision: Decision) -> str:
    if decision is Decision.USER_BUSY:
        return "Ваше предыдущее видео ещё обрабатывается. Дождитесь результата, пожалуйста."
    if decision is Decision.OVERLOADED:
        return "Сервис сейчас перегружен. Попробуйте через пару минут."
    return "Не удалось принять запрос."
