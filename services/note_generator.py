import json
import logging
import re
from textwrap import dedent
import aiohttp
from core.config import Config
from core.models import ExtractedContent, StudyNote

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = dedent("""\
You are an expert technical educator. Create clear, well-structured
study notes in Markdown. Use headings (##), code examples, bold for
key terms, practical examples. End with Key Takeaways (3-5 bullets).""")

USER_PROMPT = dedent("""\
Create comprehensive study notes on: **{topic}**

Source material from {n} resources:
---
{content}
---

Generate notes covering: core concepts, how it works, best practices,
common pitfalls, key takeaways.

Also provide:
- A 2-3 sentence summary for a Telegram message
- A list of 5-8 key concepts as a JSON array

Format EXACTLY as:
## Notes
[notes here]

## Summary
[2-3 sentences]

## Key Concepts
["concept1", "concept2", ...]""")


class NoteGenerator:
    def __init__(self, config: Config):
        self.config = config

    async def generate(self, topic, content_items):
        merged = self._merge(content_items)
        prompt = USER_PROMPT.format(topic=topic, n=len(content_items), content=merged)

        if self.config.llm_provider == "groq" and self.config.groq_api_key:
            raw = await self._call_groq(prompt)
        else:
            raw = await self._call_gemini(prompt)

        return self._parse(topic, raw, content_items)

    async def _call_gemini(self, prompt):
        url = ("https://generativelanguage.googleapis.com/v1beta/"
               "models/gemini-2.0-flash:generateContent")
        params = {"key": self.config.gemini_api_key}
        payload = {
            "contents": [{"parts": [{"text": SYSTEM_PROMPT + "\n\n" + prompt}]}],
            "generationConfig": {"temperature": 0.4, "maxOutputTokens": 4096},
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, params=params, json=payload,
                                    timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise RuntimeError(f"Gemini error {resp.status}: {error[:200]}")
                data = await resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError("Gemini returned no candidates")
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts)
        logger.info(f"Gemini: {len(text.split())} words generated")
        return text

    async def _call_groq(self, prompt):
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.config.groq_api_key}",
                    "Content-Type": "application/json"}
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.4, "max_tokens": 4096,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload,
                                    timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise RuntimeError(f"Groq error {resp.status}: {error[:200]}")
                data = await resp.json()
        text = data["choices"][0]["message"]["content"]
        logger.info(f"Groq: {len(text.split())} words generated")
        return text

    def _merge(self, items):
        sections = []
        for item in items:
            header = f"### Source: {item.resource.title} ({item.resource.source})"
            sections.append(f"{header}\n{item.raw_text[:5000]}")
        return "\n\n---\n\n".join(sections)

    def _parse(self, topic, raw, content_items):
        notes_content, summary, key_concepts = raw, "", []

        if "## Notes" in raw:
            after_notes = raw.split("## Notes", 1)[1]
            if "## Summary" in after_notes:
                notes_content = after_notes.split("## Summary")[0].strip()
                after_summary = after_notes.split("## Summary", 1)[1]
                if "## Key Concepts" in after_summary:
                    summary = after_summary.split("## Key Concepts")[0].strip()
                    concepts_raw = after_summary.split("## Key Concepts", 1)[1].strip()
                    try:
                        match = re.search(r"\[.*?\]", concepts_raw, re.DOTALL)
                        if match:
                            key_concepts = json.loads(match.group())
                    except (json.JSONDecodeError, AttributeError):
                        key_concepts = [l.strip().lstrip("- •") for l in concepts_raw.split("\n")
                                        if l.strip() and not l.startswith("[")][:8]
                else:
                    summary = after_summary.strip()
            else:
                notes_content = after_notes.strip()

        if not summary:
            summary = notes_content[:300].rsplit(".", 1)[0] + "."

        return StudyNote(
            topic=topic, content=notes_content,
            resources_used=[item.resource for item in content_items],
            llm_provider=self.config.llm_provider,
            key_concepts=key_concepts, summary=summary,
        )
