import logging
import re
from pathlib import Path
import aiohttp
from core.config import Config
from core.models import StudyNote

logger = logging.getLogger(__name__)
NOTES_DIR = Path("generated_notes")


class NotesStorage:
    def __init__(self, config: Config):
        self.config = config
        NOTES_DIR.mkdir(exist_ok=True)

    async def save(self, notes: StudyNote):
        results = {}
        results["local"] = self._save_local(notes)

        # Save to Notion if configured
        if self.config.notion_api_key and self.config.notion_database_id:
            results["notion"] = await self._save_to_notion(notes)
        else:
            logger.info("Notion not configured — skipping")

        return results

    def _save_local(self, notes):
        try:
            slug = re.sub(r"[^a-z0-9]+", "-", notes.topic.lower()).strip("-")
            date_str = notes.generated_at.strftime("%Y-%m-%d")
            filepath = NOTES_DIR / f"{date_str}_{slug}.md"
            filepath.write_text(notes.to_markdown(), encoding="utf-8")
            logger.info(f"Saved: {filepath}")
            return True
        except Exception as e:
            logger.error(f"Local save failed: {e}")
            return False

    async def _save_to_notion(self, notes: StudyNote):
        """
        Notion API — create a page in a database.
        FREE: personal use.
        Docs: https://developers.notion.com/docs/create-a-notion-integration

        Your database needs these columns:
          - Name   (type: title)       ← default first column
          - Topic  (type: rich_text)
          - Date   (type: date)
        """
        url = "https://api.notion.com/v1/pages"
        headers = {
            "Authorization": f"Bearer {self.config.notion_api_key}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }

        # Convert notes to Notion blocks
        blocks = self._markdown_to_notion_blocks(notes.content)

        payload = {
            "parent": {"database_id": self.config.notion_database_id},
            "properties": {
                "Title": {
                    "title": [
                        {"text": {"content": f"Study Notes: {notes.topic}"}}
                    ]
                },
            },
            "children": blocks[:100],  # Notion limit: 100 blocks per request
        }

        # Only add Topic property if it exists in the database
        # (avoids error if user didn't create this column)
        payload["properties"]["Topic"] = {
            "rich_text": [
                {"text": {"content": notes.topic}}
            ]
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, headers=headers, json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    data = await resp.json()

                    if resp.status in (200, 201):
                        page_url = data.get("url", "")
                        logger.info(f"Notion page created: {page_url}")
                        return True

                    # Handle common errors
                    error_msg = data.get("message", "Unknown error")
                    error_code = data.get("code", "")

                    if "validation_error" in error_code:
                        # Property doesn't exist — retry without Topic column
                        logger.warning(f"Notion property error: {error_msg}")
                        logger.info("Retrying without Topic property...")
                        return await self._save_to_notion_minimal(notes, headers)

                    logger.error(f"Notion API error {resp.status}: {error_msg}")
                    return False

        except Exception as e:
            logger.error(f"Notion save failed: {e}")
            return False

    async def _save_to_notion_minimal(self, notes: StudyNote, headers: dict):
        """Fallback: save with only the Name (title) property."""
        url = "https://api.notion.com/v1/pages"
        blocks = self._markdown_to_notion_blocks(notes.content)

        payload = {
            "parent": {"database_id": self.config.notion_database_id},
            "properties": {
                "Title": {
                    "title": [
                        {"text": {"content": f"Study Notes: {notes.topic}"}}
                    ]
                },
            },
            "children": blocks[:100],
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, headers=headers, json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    data = await resp.json()
                    if resp.status in (200, 201):
                        logger.info(f"Notion page created (minimal): {data.get('url', '')}")
                        return True
                    logger.error(f"Notion retry failed: {data.get('message', '')}")
                    return False
        except Exception as e:
            logger.error(f"Notion retry failed: {e}")
            return False

    @staticmethod
    def _markdown_to_notion_blocks(markdown: str) -> list:
        """Convert markdown to Notion block objects."""
        blocks = []
        lines = markdown.split("\n")
        i = 0

        while i < len(lines):
            line = lines[i]

            # Code block
            if line.startswith("```"):
                language = line[3:].strip() or "plain text"
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                blocks.append({
                    "type": "code",
                    "code": {
                        "rich_text": [
                            {"text": {"content": "\n".join(code_lines)[:2000]}}
                        ],
                        "language": language,
                    },
                })
                i += 1
                continue

            # Heading 2
            if line.startswith("## "):
                blocks.append({
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"text": {"content": line[3:].strip()}}]
                    },
                })
            # Heading 3
            elif line.startswith("### "):
                blocks.append({
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [{"text": {"content": line[4:].strip()}}]
                    },
                })
            # Bullet
            elif line.startswith("- ") or line.startswith("* "):
                blocks.append({
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"text": {"content": line[2:].strip()[:2000]}}]
                    },
                })
            # Numbered list
            elif re.match(r"^\d+\.\s", line):
                text = re.sub(r"^\d+\.\s", "", line).strip()
                blocks.append({
                    "type": "numbered_list_item",
                    "numbered_list_item": {
                        "rich_text": [{"text": {"content": text[:2000]}}]
                    },
                })
            # Non-empty paragraph
            elif line.strip():
                blocks.append({
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": line.strip()[:2000]}}]
                    },
                })

            i += 1

        return blocks
