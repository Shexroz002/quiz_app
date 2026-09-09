import time
from urllib.parse import parse_qsl

from aiogram.utils.web_app import safe_parse_webapp_init_data


def validate_init_data(init_data: str, bot_token: str) -> int:
    pairs = parse_qsl(init_data, strict_parsing=True)
    if len(dict(pairs)) != len(pairs):
        raise ValueError("Duplicate init data fields")
    data = safe_parse_webapp_init_data(bot_token, init_data)
    age = time.time() - data.auth_date.timestamp()
    if age < -30 or age > 3600 or data.user is None or data.user.is_bot:
        raise ValueError("Expired or invalid Telegram identity")
    return data.user.id
