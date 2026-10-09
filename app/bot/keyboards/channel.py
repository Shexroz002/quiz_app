from aiogram.types import (
    ChatAdministratorRights,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    KeyboardButtonRequestChat,
    ReplyKeyboardMarkup,
)

CHANNEL_PICK = "channel:pick:"
CHANNEL_NEW = "channel:new"
GROUP_NEW = "group:new"

#: Telegram echoes the id back with the chosen chat, which is how the handler
#: knows whether a channel or a group was asked for.
CHANNEL_REQUEST_ID = 1
GROUP_REQUEST_ID = 2

CANCEL_TEXT = "✖️ Bekor qilish"


def parse_channel_id(data: str | None) -> int | None:
    """A channel id is negative, so this cannot lean on ``str.isdigit``."""
    value = (data or "").removeprefix(CHANNEL_PICK)
    digits = value[1:] if value.startswith("-") else value
    return int(value) if digits.isdigit() and digits else None


def chat_list_keyboard(chats: list[dict], *, is_channel: bool) -> InlineKeyboardMarkup:
    """The chats this admin has published to before, newest first."""
    icon = "📣" if is_channel else "👥"
    rows = [
        [InlineKeyboardButton(
            text=f"{icon} {chat['title'][:48]}",
            callback_data=f"{CHANNEL_PICK}{chat['chat_id']}",
        )]
        for chat in chats
    ]
    rows.append([InlineKeyboardButton(
        text="➕ Boshqa kanal" if is_channel else "➕ Boshqa guruh",
        callback_data=CHANNEL_NEW if is_channel else GROUP_NEW,
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


#: Telegram rejects a rights object with nothing set ("ADMIN_RIGHTS_EMPTY"),
#: and every administrator has this one -- it is implied by any other
#: privilege -- so it is what "must be an admin here" is expressed with.
_BASE_RIGHT = "can_manage_chat"

_RIGHT_FLAGS = (
    "is_anonymous",
    "can_manage_chat",
    "can_delete_messages",
    "can_manage_video_chats",
    "can_restrict_members",
    "can_promote_members",
    "can_change_info",
    "can_invite_users",
    "can_post_stories",
    "can_edit_stories",
    "can_delete_stories",
    "can_send_welcome_messages",
)


def _admin_rights(**granted: bool) -> ChatAdministratorRights:
    """The Bot API wants every flag spelled out; we only ask for a couple."""
    flags = dict.fromkeys(_RIGHT_FLAGS, False)
    flags[_BASE_RIGHT] = True
    flags.update(granted)
    return ChatAdministratorRights(**flags)


def add_bot_keyboard(bot_username: str, *, is_channel: bool) -> InlineKeyboardMarkup:
    """Telegram's own "add this bot" flow, pre-filled for what the quiz needs.

    ``startchannel`` asks for the posting right straight away; ``startgroup``
    needs no rights at all, so it asks for none.
    """
    url = (
        f"https://t.me/{bot_username}?startchannel=true&admin=post_messages"
        if is_channel
        else f"https://t.me/{bot_username}?startgroup=true"
    )
    label = "➕ Botni kanalga qo'shish" if is_channel else "➕ Botni guruhga qo'shish"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label, url=url)]])


def chat_picker_keyboard(*, is_channel: bool) -> ReplyKeyboardMarkup:
    """Telegram's own chat list, filtered to what the quiz actually needs.

    The client only offers chats where the person is an administrator and the
    bot can publish -- a channel where the bot is an admin that may post, or a
    group the bot is already in. The rights are verified again server-side
    before anything is published.
    """
    if is_channel:
        label = "📣 Kanalni tanlash"
        request = KeyboardButtonRequestChat(
            request_id=CHANNEL_REQUEST_ID,
            chat_is_channel=True,
            request_title=True,
            user_administrator_rights=_admin_rights(can_post_messages=True),
            bot_administrator_rights=_admin_rights(can_post_messages=True),
        )
    else:
        label = "👥 Guruhni tanlash"
        # Only "you administer it" is asked for. ``bot_is_member`` is left out
        # on purpose: the client answers it from whatever membership it happens
        # to have cached, which can hide a group the bot is really in -- and the
        # bot checks its own access server-side before publishing anyway.
        request = KeyboardButtonRequestChat(
            request_id=GROUP_REQUEST_ID,
            chat_is_channel=False,
            request_title=True,
            user_administrator_rights=_admin_rights(),
        )
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=label, request_chat=request)],
            [KeyboardButton(text=CANCEL_TEXT)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
