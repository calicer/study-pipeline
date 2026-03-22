"""
Topic Manager — decides what to study today.

Sources (in priority order):
1. CLI argument       → python pipeline.py "specific topic"
2. topics.json file   → curated list you maintain, rotates daily
3. Auto-suggest       → based on your profile/interests

Usage:
    topic = TopicManager(config).get_today_topic()
"""
import json
import logging
import random
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

TOPICS_FILE = Path("topics.json")

# ── Default curated topics ─────────────────────────────────
# Edit topics.json to customize. Organized by category.
DEFAULT_TOPICS = {
    "categories": {
        "java_backend": [
            "Java concurrency — threads, locks, and CompletableFuture",
            "Java memory model and garbage collection tuning",
            "Spring Boot auto-configuration internals",
            "Spring Security — OAuth2 and JWT authentication",
            "JPA and Hibernate performance — N+1 queries, batch fetching, caching",
            "Java functional programming — streams, Optional, and collectors",
            "Spring Boot actuator and production monitoring",
            "Microservices communication — REST vs gRPC vs message queues",
            "Database connection pooling with HikariCP",
            "Java records, sealed classes, and pattern matching",
        ],
        "system_design": [
            "CAP theorem and distributed consistency models",
            "Database indexing strategies — B-tree, hash, GIN, GiST",
            "Load balancing algorithms — round robin, least connections, consistent hashing",
            "Caching strategies — write-through, write-back, cache-aside",
            "Message queues — Kafka vs RabbitMQ vs Redis Streams",
            "API rate limiting and throttling patterns",
            "Database sharding strategies and trade-offs",
            "Circuit breaker pattern and resilience in microservices",
            "Event sourcing and CQRS pattern",
            "Distributed tracing with OpenTelemetry",
        ],
        "python_ai": [
            "Python asyncio — event loop, tasks, and gather patterns",
            "Building AI agents with tool calling and function execution",
            "RAG pipeline — retrieval augmented generation from scratch",
            "LangChain expression language (LCEL) chains and runnables",
            "Vector databases — embeddings, similarity search, and HNSW",
            "Prompt engineering — chain of thought, few-shot, and structured output",
            "Python decorators and metaclasses deep dive",
            "FastAPI — async endpoints, dependency injection, and middleware",
        ],
        "devops": [
            "Docker multi-stage builds and image optimization",
            "Kubernetes pods, services, and deployments explained",
            "CI/CD pipeline design — GitHub Actions advanced workflows",
            "PostgreSQL query optimization and EXPLAIN ANALYZE",
            "Linux performance debugging — top, strace, perf, flamegraphs",
            "Terraform infrastructure as code fundamentals",
            "Nginx reverse proxy and load balancing configuration",
        ],
    },
    "settings": {
        "rotation": "sequential",
        "current_index": 0,
        "last_run_date": None,
    }
}


class TopicManager:
    def __init__(self):
        self.data = self._load_topics()

    def get_today_topic(self) -> str:
        """Pick today's topic based on rotation strategy."""
        all_topics = self._get_all_topics()
        settings = self.data.get("settings", {})
        rotation = settings.get("rotation", "sequential")

        if rotation == "random":
            topic = random.choice(all_topics)
        elif rotation == "category_round_robin":
            topic = self._category_round_robin()
        else:
            # Sequential — go through the list in order
            idx = settings.get("current_index", 0) % len(all_topics)
            topic = all_topics[idx]
            settings["current_index"] = idx + 1

        # Save updated index
        settings["last_run_date"] = datetime.now().strftime("%Y-%m-%d")
        self._save_topics()

        logger.info(f"Today's topic: {topic}")
        return topic

    def get_topics_by_category(self, category: str) -> list[str]:
        """Get all topics in a specific category."""
        return self.data.get("categories", {}).get(category, [])

    def list_categories(self) -> list[str]:
        """List all available categories."""
        return list(self.data.get("categories", {}).keys())

    def add_topic(self, category: str, topic: str):
        """Add a new topic to a category."""
        if category not in self.data["categories"]:
            self.data["categories"][category] = []
        if topic not in self.data["categories"][category]:
            self.data["categories"][category].append(topic)
            self._save_topics()
            logger.info(f"Added topic to {category}: {topic}")

    def _get_all_topics(self) -> list[str]:
        """Flatten all categories into a single list."""
        all_topics = []
        for topics in self.data.get("categories", {}).values():
            all_topics.extend(topics)
        return all_topics

    def _category_round_robin(self) -> str:
        """Pick one topic from each category in rotation."""
        categories = self.data.get("categories", {})
        cat_names = list(categories.keys())
        settings = self.data.get("settings", {})
        idx = settings.get("current_index", 0)

        # Which category today
        cat = cat_names[idx % len(cat_names)]
        # Which topic within that category
        topic_idx = (idx // len(cat_names)) % len(categories[cat])
        topic = categories[cat][topic_idx]

        settings["current_index"] = idx + 1
        return topic

    def _load_topics(self) -> dict:
        """Load topics from JSON file, or create default."""
        if TOPICS_FILE.exists():
            try:
                with open(TOPICS_FILE, "r") as f:
                    data = json.load(f)
                logger.info(f"Loaded {sum(len(v) for v in data.get('categories', {}).values())} topics from {TOPICS_FILE}")
                return data
            except Exception as e:
                logger.error(f"Error loading {TOPICS_FILE}: {e}")

        # Create default file
        logger.info(f"Creating default {TOPICS_FILE}")
        self.data = DEFAULT_TOPICS
        self._save_topics()
        return self.data

    def _save_topics(self):
        """Persist topics to JSON file."""
        try:
            with open(TOPICS_FILE, "w") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving {TOPICS_FILE}: {e}")


# ── CLI helper ─────────────────────────────────────────────

def print_all_topics():
    """Pretty-print all topics by category."""
    tm = TopicManager()
    for cat, topics in tm.data.get("categories", {}).items():
        print(f"\n📂 {cat} ({len(topics)} topics)")
        for i, t in enumerate(topics):
            print(f"   {i+1:2d}. {t}")
    print(f"\n📊 Total: {sum(len(v) for v in tm.data['categories'].values())} topics")
    print(f"🔄 Rotation: {tm.data['settings']['rotation']}")
    print(f"📍 Next index: {tm.data['settings']['current_index']}")


if __name__ == "__main__":
    print_all_topics()
