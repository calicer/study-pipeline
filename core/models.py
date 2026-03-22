from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ResourceType(Enum):
    YOUTUBE_VIDEO = "youtube_video"
    ARTICLE = "article"
    GITHUB_REPO = "github_repo"
    DOCUMENTATION = "documentation"


@dataclass
class Resource:
    title: str
    url: str
    resource_type: ResourceType
    description: str = ""
    source: str = ""
    relevance_score: float = 0.0


@dataclass
class ExtractedContent:
    resource: Resource
    raw_text: str
    word_count: int = 0
    extraction_method: str = ""

    def __post_init__(self):
        if not self.word_count:
            self.word_count = len(self.raw_text.split())


@dataclass
class StudyNote:
    topic: str
    content: str
    resources_used: list = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)
    llm_provider: str = ""
    key_concepts: list = field(default_factory=list)
    summary: str = ""

    def to_telegram_message(self):
        lines = [
            f"📚 *Study Notes: {self.topic}*",
            f"_{self.generated_at.strftime('%B %d, %Y')}_",
            "",
            f"📝 *Summary*",
            self.summary or self.content[:300] + "...",
            "",
        ]
        if self.key_concepts:
            lines.append("🔑 *Key concepts*")
            for c in self.key_concepts[:8]:
                lines.append(f"  • {c}")
            lines.append("")
        if self.resources_used:
            lines.append("📎 *Resources*")
            for r in self.resources_used[:5]:
                lines.append(f"  • [{r.title[:50]}]({r.url})")
        return "\n".join(lines)

    def to_markdown(self):
        lines = [
            f"# {self.topic}",
            f"*Generated on {self.generated_at.strftime('%Y-%m-%d %H:%M')}*",
            "", "---", "",
            self.content,
            "", "---", "",
            "## Resources", "",
        ]
        for r in self.resources_used:
            lines.append(f"- [{r.title}]({r.url}) ({r.resource_type.value})")
        return "\n".join(lines)


@dataclass
class PipelineResult:
    topic: str
    resources_found: list = field(default_factory=list)
    content_extracted: list = field(default_factory=list)
    notes: StudyNote = None
    telegram_sent: bool = False
    errors: list = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime = None

    @property
    def success(self):
        return self.notes is not None and self.telegram_sent
