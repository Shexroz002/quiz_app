from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.bot.keyboards.inline import quiz_webapp_url


def room_link(username, code):
    return f"https://t.me/{username}?start=room_{code}"


def room_share_link(username, code):
    return "https://t.me/share/url?" + urlencode({
        "url": room_link(username, code),
        "text": "Test xonasiga qo‘shiling!",
    })


def room_webapp_url(session):
    url = urlsplit(quiz_webapp_url(session.quiz_id))
    query = dict(parse_qsl(url.query))
    query["room_session"] = str(session.id)
    return urlunsplit(url._replace(query=urlencode(query)))


def room_keyboard(session, username, *, is_host, group_chat=False):
    if session.status == "finished":
        return None
    if session.status == "waiting":
        rows = []
        if group_chat:
            rows.append([
                InlineKeyboardButton(
                    text="➕ Testga qo‘shilish",
                    url=room_link(username, session.join_code),
                ),
            ])
        elif is_host:
            rows.append([
                InlineKeyboardButton(
                    text="🚀 Boshlash",
                    callback_data=f"room:start:{session.id}",
                ),
            ])
        if not group_chat:
            rows.append([InlineKeyboardButton(
                text="👥 Do‘stlarga ulashish",
                url=room_share_link(username, session.join_code),
            )])
    elif group_chat:
        rows = [[InlineKeyboardButton(
            text="📝 Testni ishlash",
            url=room_link(username, session.join_code),
        )]]
    else:
        rows = [[InlineKeyboardButton(
            text="🚀 Testni boshlash",
            web_app=WebAppInfo(url=room_webapp_url(session)),
        )]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def player_keyboard(session):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="📝 Testni boshlash",
            web_app=WebAppInfo(url=room_webapp_url(session)),
        )
    ]])


def host_room_keyboard(session):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🚀 Testni boshlash",
            callback_data=f"room:start:{session.id}",
        )
    ]])
