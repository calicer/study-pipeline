import logging
import aiohttp
from core.config import Config
from core.models import StudyNote

logger = logging.getLogger(__name__)


class TelegramNotifier:
    BASE_URL = "https://api.telegram.org/bot{token}"

    def __init__(self, config: Config):
        self.config = config
        self.api_url = self.BASE_URL.format(token=config.telegram_bot_token)

    async def send_study_notes(self, notes: StudyNote):
        message = notes.to_telegram_message()
        return await self._send(message, parse_mode="Markdown")

    async def send_reminder(self, topic, message=None):
        text = message or f"⏰ Time to study: *{topic}*\nReady to learn?"
        return await self._send(text, parse_mode="Markdown")

    async def _send(self, text, parse_mode="Markdown"):
        if not self.config.telegram_bot_token or not self.config.telegram_chat_id:
            logger.error("Telegram not configured")
            return False

        if len(text) > 4096:
            text = text[:4076] + "\n\n_...truncated_"

        url = f"{self.api_url}/sendMessage"
        payload = {
            "chat_id": self.config.telegram_chat_id,
            "text": text,
            "disable_web_page_preview": False,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload,
                                        timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
                    if not data.get("ok"):
                        desc = data.get("description", "Unknown")
                        logger.error(f"Telegram error: {desc}")
                        if parse_mode == "Markdown" and "can't parse" in desc.lower():
                            return await self._send(text, parse_mode=None)
                        return False
                    logger.info("Telegram message sent!")
                    return True
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False
