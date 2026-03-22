import asyncio
import logging
import aiohttp
from core.config import Config
from core.models import Resource, ResourceType

logger = logging.getLogger(__name__)


class ResourceDiscovery:
    def __init__(self, config: Config):
        self.config = config

    async def discover(self, topic, max_results=None):
        max_results = max_results or self.config.max_resources
        async with aiohttp.ClientSession() as session:
            tasks = []
            if self.config.youtube_api_key:
                tasks.append(self._search_youtube(session, topic, max_results))
            if self.config.google_search_api_key:
                tasks.append(self._search_google(session, topic, max_results))
            tasks.append(self._search_github(session, topic, max_results))

            results = await asyncio.gather(*tasks, return_exceptions=True)

        all_resources = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Search failed: {result}")
            elif isinstance(result, list):
                all_resources.extend(result)

        seen_urls = set()
        unique = []
        for r in sorted(all_resources, key=lambda x: x.relevance_score, reverse=True):
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                unique.append(r)
        return unique[:max_results]

    async def _search_youtube(self, session, topic, max_results):
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "part": "snippet", "q": f"{topic} tutorial explained",
            "type": "video", "maxResults": min(max_results, 10),
            "order": "relevance", "videoDuration": "medium",
            "relevanceLanguage": "en", "key": self.config.youtube_api_key,
        }
        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.error(f"YouTube API error {resp.status}")
                    return []
                data = await resp.json()
            resources = []
            for i, item in enumerate(data.get("items", [])):
                snippet = item.get("snippet", {})
                video_id = item.get("id", {}).get("videoId", "")
                if not video_id:
                    continue
                resources.append(Resource(
                    title=snippet.get("title", "Untitled"),
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    resource_type=ResourceType.YOUTUBE_VIDEO,
                    description=snippet.get("description", "")[:200],
                    source="youtube", relevance_score=1.0 - (i * 0.1),
                ))
            logger.info(f"YouTube: found {len(resources)} videos")
            return resources
        except Exception as e:
            logger.error(f"YouTube search error: {e}")
            return []

    async def _search_google(self, session, topic, max_results):
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": self.config.google_search_api_key,
            "cx": self.config.google_search_engine_id,
            "q": f"{topic} tutorial guide free resource",
            "num": min(max_results, 10),
        }
        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.error(f"Google Search error {resp.status}")
                    return []
                data = await resp.json()
            resources = []
            for i, item in enumerate(data.get("items", [])):
                link = item.get("link", "")
                if "youtube.com" in link or "youtu.be" in link:
                    continue
                resources.append(Resource(
                    title=item.get("title", "Untitled"), url=link,
                    resource_type=ResourceType.ARTICLE,
                    description=item.get("snippet", "")[:200],
                    source="google", relevance_score=0.9 - (i * 0.1),
                ))
            logger.info(f"Google: found {len(resources)} articles")
            return resources
        except Exception as e:
            logger.error(f"Google search error: {e}")
            return []

    async def _search_github(self, session, topic, max_results):
        url = "https://api.github.com/search/repositories"
        headers = {"Accept": "application/vnd.github.v3+json"}
        if self.config.github_token:
            headers["Authorization"] = f"token {self.config.github_token}"
        params = {
            "q": f"{topic} tutorial OR awesome OR guide OR learn",
            "sort": "stars", "order": "desc",
            "per_page": min(max_results, 10),
        }
        try:
            async with session.get(url, params=params, headers=headers) as resp:
                if resp.status != 200:
                    logger.error(f"GitHub API error {resp.status}")
                    return []
                data = await resp.json()
            resources = []
            for i, repo in enumerate(data.get("items", [])):
                stars = repo.get("stargazers_count", 0)
                resources.append(Resource(
                    title=repo.get("full_name", "Untitled"),
                    url=repo.get("html_url", ""),
                    resource_type=ResourceType.GITHUB_REPO,
                    description=(repo.get("description", "") or "")[:200],
                    source="github", relevance_score=min(stars / 10000, 1.0),
                ))
            logger.info(f"GitHub: found {len(resources)} repos")
            return resources
        except Exception as e:
            logger.error(f"GitHub search error: {e}")
            return []
