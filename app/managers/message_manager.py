from aiogram.fsm.state import State, StatesGroup


class TypeStates(StatesGroup):
    send_video: State = State()
    add_user: State = State()
    delete_user: State = State()
    add_admin: State = State()
    delete_admin: State = State()
