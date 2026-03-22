import asyncio
import logging
import re
import sys
from datetime import datetime

from core.config import Config
from core.models import PipelineResult, Resource, ResourceType
from services.discovery import ResourceDiscovery
from services.extractor import ContentExtractor
from services.note_generator import NoteGenerator
from services.storage import NotesStorage
from services.telegram_notifier import TelegramNotifier
from services.topic_manager import TopicManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-28s │ %(levelname)-5s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pipeline")


def parse_input(raw):
    url_pattern = re.compile(r"https?://[^\s]+")
    urls = url_pattern.findall(raw)
    topic = url_pattern.sub("", raw).strip()
    if not topic and urls:
        topic = "Study Resource"
    return topic, urls


def urls_to_resources(urls):
    resources = []
    for url in urls:
        if "youtube.com" in url or "youtu.be" in url:
            rtype = ResourceType.YOUTUBE_VIDEO
        elif "github.com" in url:
            rtype = ResourceType.GITHUB_REPO
        else:
            rtype = ResourceType.ARTICLE
        resources.append(Resource(
            title=url.split("/")[-1] or "Provided Resource",
            url=url, resource_type=rtype,
            source="user_provided", relevance_score=1.0,
        ))
    return resources


async def run_pipeline(raw_input, config):
    result = PipelineResult(topic=raw_input)

    topic, explicit_urls = parse_input(raw_input)
    result.topic = topic
    logger.info(f"📝 Topic: '{topic}' | URLs: {len(explicit_urls)}")

    logger.info("🔍 Discovering resources...")
    discovery = ResourceDiscovery(config)
    all_resources = urls_to_resources(explicit_urls)
    if topic and topic != "Study Resource":
        discovered = await discovery.discover(topic)
        all_resources.extend(discovered)

    if not all_resources:
        result.errors.append("No resources found")
        logger.error("No resources found")
        return result

    result.resources_found = all_resources
    logger.info(f"📚 Found {len(all_resources)} resources")
    for r in all_resources[:8]:
        logger.info(f"   → [{r.source:8s}] {r.title[:60]}")

    logger.info("📖 Extracting content...")
    extractor = ContentExtractor(config)
    extracted = await extractor.extract_all(all_resources[:config.max_resources])
    if not extracted:
        result.errors.append("Failed to extract any content")
        logger.error("No content extracted")
        return result

    result.content_extracted = extracted
    total_words = sum(e.word_count for e in extracted)
    logger.info(f"📄 Extracted {total_words:,} words from {len(extracted)} resources")

    logger.info(f"🤖 Generating notes with {config.llm_provider}...")
    generator = NoteGenerator(config)
    try:
        notes = await generator.generate(topic, extracted)
        result.notes = notes
        logger.info(f"✅ Notes: {len(notes.content.split()):,} words, "
                     f"{len(notes.key_concepts)} concepts")
    except Exception as e:
        result.errors.append(f"Note generation failed: {e}")
        logger.error(f"Note generation failed: {e}")
        return result

    logger.info("💾 Saving notes...")
    storage = NotesStorage(config)
    save_results = await storage.save(notes)
    for backend, ok in save_results.items():
        logger.info(f"   {'✅' if ok else '❌'} {backend}")

    logger.info("📱 Sending Telegram notification...")
    notifier = TelegramNotifier(config)
    result.telegram_sent = await notifier.send_study_notes(notes)
    logger.info("✅ Telegram sent!" if result.telegram_sent else "⚠️  Telegram failed")

    result.completed_at = datetime.now()
    dur = (result.completed_at - result.started_at).total_seconds()
    logger.info(f"🏁 Done in {dur:.1f}s")
    return result


async def main():
    config = Config.from_env()
    errors = config.validate_minimum()
    if errors:
        print("❌ Configuration errors:")
        for e in errors:
            print(f"   • {e}")
        print("\nFill in .env — see .env.example for guidance.")
        sys.exit(1)

    # ── Handle different modes ─────────────────────────────
    if len(sys.argv) < 2:
        print("Usage:")
        print('  python pipeline.py "Java concurrency"       # specific topic')
        print('  python pipeline.py --auto                    # auto-pick from topics.json')
        print('  python pipeline.py --list                    # show all topics')
        print('  python pipeline.py --add java "new topic"    # add a topic')
        sys.exit(1)

    # List all topics
    if sys.argv[1] == "--list":
        from services.topic_manager import print_all_topics
        print_all_topics()
        return

    # Add a topic
    if sys.argv[1] == "--add":
        if len(sys.argv) < 4:
            print('Usage: python pipeline.py --add <category> "topic text"')
            print('Categories: java_backend, system_design, python_ai, devops')
            sys.exit(1)
        tm = TopicManager()
        category = sys.argv[2]
        topic = " ".join(sys.argv[3:])
        tm.add_topic(category, topic)
        print(f"✅ Added to {category}: {topic}")
        return

    # Auto-pick topic from topics.json
    if sys.argv[1] == "--auto":
        tm = TopicManager()
        raw_input = tm.get_today_topic()
        print(f"📚 Auto-selected: {raw_input}")
    else:
        raw_input = " ".join(sys.argv[1:])

    result = await run_pipeline(raw_input, config)

    if result.success:
        print(f"\n✅ Done! Check Telegram and ./generated_notes/")
    else:
        print(f"\n⚠️  Completed with errors:")
        for e in result.errors:
            print(f"   • {e}")


if __name__ == "__main__":
    asyncio.run(main())
