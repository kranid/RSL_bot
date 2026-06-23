class UserNotFoundException(Exception):

    def __init__(self, tg_id: int):
        self.tg_id: int = tg_id

    def __str__(self):
        return f"User with Telegram id {self.tg_id} not found"


class CantChangeHigherAccessRole(Exception):

    def __str__(self):
        return "Can't change higher access or the same role"
