import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv


@dataclass
class Config:
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    youtube_api_key: str = ""
    google_search_api_key: str = ""
    google_search_engine_id: str = ""
    github_token: str = ""
    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    groq_api_key: str = ""
    jina_api_key: str = ""
    notion_api_key: str = ""
    notion_database_id: str = ""
    max_resources: int = 5

    @classmethod
    def from_env(cls, env_path=None):
        if env_path:
            load_dotenv(env_path)
        else:
            load_dotenv(Path(__file__).parent.parent / ".env")
        return cls(
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            youtube_api_key=os.getenv("YOUTUBE_API_KEY", ""),
            google_search_api_key=os.getenv("GOOGLE_SEARCH_API_KEY", ""),
            google_search_engine_id=os.getenv("GOOGLE_SEARCH_ENGINE_ID", ""),
            github_token=os.getenv("GITHUB_TOKEN", ""),
            llm_provider=os.getenv("LLM_PROVIDER", "gemini"),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            groq_api_key=os.getenv("GROQ_API_KEY", ""),
            jina_api_key=os.getenv("JINA_API_KEY", ""),
            notion_api_key=os.getenv("NOTION_API_KEY", ""),
            notion_database_id=os.getenv("NOTION_DATABASE_ID", ""),
            max_resources=int(os.getenv("MAX_RESOURCES_PER_TOPIC", "5")),
        )

    def get_active_llm_key(self):
        if self.llm_provider == "groq" and self.groq_api_key:
            return self.groq_api_key
        return self.gemini_api_key

    def validate_minimum(self):
        errors = []
        if not self.telegram_bot_token:
            errors.append("TELEGRAM_BOT_TOKEN is required")
        if not self.telegram_chat_id:
            errors.append("TELEGRAM_CHAT_ID is required")
        if not self.gemini_api_key and not self.groq_api_key:
            errors.append("At least one LLM key (GEMINI or GROQ) is required")
        return errors
