from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Literal


@dataclass(slots=True)
class MentionedService:
    name: str
    category: Literal["aws", "competitor", "generic"]
    mention_count: int = 1
    first_seen_at: float = field(default_factory=time.time)
    last_seen_at: float = field(default_factory=time.time)


@dataclass(slots=True)
class OpenQuestion:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    text: str = ""
    raised_at: float = field(default_factory=time.time)
    resolved: bool = False


@dataclass(slots=True)
class Topic:
    name: str
    keywords: list[str] = field(default_factory=list)
    confidence: float = 0.5
    first_seen_at: float = field(default_factory=time.time)
    last_seen_at: float = field(default_factory=time.time)


@dataclass
class CCMState:
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    meeting_goal: str = ""
    active_topics: list[Topic] = field(default_factory=list)
    open_questions: list[OpenQuestion] = field(default_factory=list)
    mentioned_services: dict[str, MentionedService] = field(default_factory=dict)
    full_transcript: list[str] = field(default_factory=list)
    last_updated_at: float = field(default_factory=time.time)
    recommendation_trigger_count: int = 0

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "meeting_goal": self.meeting_goal,
            "active_topics": [
                {
                    "name": t.name,
                    "keywords": t.keywords,
                    "confidence": t.confidence,
                    "first_seen_at": t.first_seen_at,
                }
                for t in self.active_topics
            ],
            "open_questions": [
                {
                    "id": q.id,
                    "text": q.text,
                    "raised_at": q.raised_at,
                    "resolved": q.resolved,
                }
                for q in self.open_questions
                if not q.resolved
            ],
            "mentioned_services": {
                k: {
                    "name": v.name,
                    "category": v.category,
                    "mention_count": v.mention_count,
                }
                for k, v in self.mentioned_services.items()
            },
            "last_updated_at": self.last_updated_at,
        }


@dataclass(slots=True)
class CCMUpdateEvent:
    event_type: Literal[
        "service_mentioned",
        "question_detected",
        "topic_shift",
        "competitor_mentioned",
    ]
    session_id: str
    context_snapshot: dict
    trigger_text: str
    timestamp: float = field(default_factory=time.time)
