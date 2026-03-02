from app.core.config import settings
from app.services.ai.providers.gemini_provider import GeminiProvider


# from app.ai.providers.openai_provider import OpenAIProvider
# from app.ai.providers.deepseek_provider import DeepSeekProvider

def get_provider(name: str, logger):
    name = name.lower()

    if name == "gemini":
        return GeminiProvider(
            api_key=settings.GEMINI_API_KEY,
            model=settings.GEMINI_MODEL,
            logger=logger,
        )

    # if name == "openai":
    #     return OpenAIProvider(client=openai_client, model=settings.OPENAI_MODEL)

    # if name == "deepseek":
    #     return DeepSeekProvider(...)

    raise ValueError(f"Unknown provider: {name}")