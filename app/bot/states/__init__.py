from aiogram.fsm.state import State, StatesGroup


class RegistrationState(StatesGroup):
    waiting_for_contact = State()
    waiting_for_grade = State()


class QuizGenerationState(StatesGroup):
    waiting_for_pdf = State()


class QuizDurationState(StatesGroup):
    waiting_for_single_player_custom_minutes = State()
    waiting_for_friends_custom_minutes = State()
