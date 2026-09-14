class ChatAccessDeniedError(Exception):
    """Foydalanuvchi so'ralgan chat yoki xabarga kira olmaydi."""

    def __init__(self, detail: str = "Sizda bu chatga ruxsat yo'q"):
        self.detail = detail
        super().__init__(detail)


class MessageNotFoundError(ChatAccessDeniedError):
    """Xabar topilmadi yoki o'chirilgan."""

    def __init__(self, detail: str = "Xabar topilmadi"):
        super().__init__(detail)
