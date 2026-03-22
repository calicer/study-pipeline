import asyncio
import logging
import re
import aiohttp
from core.config import Config
from core.models import ExtractedContent, Resource, ResourceType

logger = logging.getLogger(__name__)
MAX_CONTENT_CHARS = 15_000


class ContentExtractor:
    def __init__(self, config: Config):
        self.config = config

    async def extract_all(self, resources):
        tasks = [self._extract_one(r) for r in resources]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        extracted = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Extraction failed: {result}")
            elif result and result.word_count > 50:
                extracted.append(result)
        logger.info(f"Extracted from {len(extracted)}/{len(resources)} resources")
        return extracted

    async def _extract_one(self, resource):
        if resource.resource_type == ResourceType.YOUTUBE_VIDEO:
            return await self._extract_youtube(resource)
        elif resource.resource_type == ResourceType.GITHUB_REPO:
            return await self._extract_github_readme(resource)
        else:
            return await self._extract_via_jina(resource)

    async def _extract_via_jina(self, resource):
        jina_url = f"https://r.jina.ai/{resource.url}"
        headers = {"Accept": "text/markdown", "X-No-Cache": "true"}
        if self.config.jina_api_key:
            headers["Authorization"] = f"Bearer {self.config.jina_api_key}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(jina_url, headers=headers,
                                       timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        logger.warning(f"Jina failed for {resource.url}: {resp.status}")
                        return None
                    text = await resp.text()
            text = self._clean(text)[:MAX_CONTENT_CHARS]
            logger.info(f"Jina: {len(text.split())} words from {resource.url}")
            return ExtractedContent(resource=resource, raw_text=text, extraction_method="jina")
        except Exception as e:
            logger.error(f"Jina error: {e}")
            return None

    async def _extract_youtube(self, resource):
        video_id = self._get_video_id(resource.url)
        if not video_id:
            return None
        try:
            text = await asyncio.get_event_loop().run_in_executor(
                None, self._fetch_transcript, video_id
            )
            if not text:
                return None
            text = text[:MAX_CONTENT_CHARS]
            logger.info(f"Transcript: {len(text.split())} words from {video_id}")
            return ExtractedContent(resource=resource, raw_text=text,
                                    extraction_method="youtube_transcript")
        except Exception as e:
            logger.error(f"Transcript error: {e}")
            return None

    @staticmethod
    def _fetch_transcript(video_id):
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            ytt = YouTubeTranscriptApi()
            transcript = ytt.fetch(video_id)
            return " ".join([s.text for s in transcript.snippets])
        except Exception as e:
            logger.warning(f"Transcript unavailable for {video_id}: {e}")
            return None

    async def _extract_github_readme(self, resource):
        match = re.search(r"github\.com/([^/]+/[^/]+)", resource.url)
        if not match:
            return await self._extract_via_jina(resource)
        repo_path = match.group(1).rstrip("/")
        api_url = f"https://api.github.com/repos/{repo_path}/readme"
        headers = {"Accept": "application/vnd.github.v3.raw"}
        if self.config.github_token:
            headers["Authorization"] = f"token {self.config.github_token}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, headers=headers,
                                       timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        return await self._extract_via_jina(resource)
                    text = await resp.text()
            text = self._clean(text)[:MAX_CONTENT_CHARS]
            logger.info(f"GitHub README: {len(text.split())} words from {repo_path}")
            return ExtractedContent(resource=resource, raw_text=text,
                                    extraction_method="github_readme")
        except Exception as e:
            logger.error(f"GitHub README error: {e}")
            return None

    @staticmethod
    def _get_video_id(url):
        patterns = [r"(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})", r"(?:embed/)([a-zA-Z0-9_-]{11})"]
        for p in patterns:
            m = re.search(p, url)
            if m:
                return m.group(1)
        return None

    @staticmethod
    def _clean(text):
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
