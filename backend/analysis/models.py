"""Data models for the cadence-based staged analysis engine."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Literal


AnalysisStage = Literal[1, 2, 3]

MEETING_TYPES = [
    "Customer Meeting",
    "OneTeam / Partner Meeting",
    "SA Manager Sync",
    "Internal Architecture Review",
    "Competitive Deal",
    "Migration Assessment",
    "GenAI / ML Workshop",
    "Cost Optimization Review",
]


@dataclass
class AnalysisResult:
    """Output of one full analysis cycle (Track A or Track B)."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    stage: AnalysisStage = 1
    ready: bool = False
    reasoning: str = ""          # readiness reasoning from Phase 1
    situation: str = ""
    current_state: str = ""
    customer_needs: str = ""
    open_questions: str = ""
    proposed_architecture: str = ""
    key_recommendations: str = ""
    sources: list[str] = field(default_factory=list)
    current_state_diagram: str = ""   # Mermaid: customer's current architecture (Stage 3)
    mermaid_diagram: str = ""         # Mermaid: proposed future state (Stage 3)
    action_items: dict = field(default_factory=lambda: {"aws": [], "partner": [], "customer": []})
    cycle_count: int = 0
    segment_count: int = 0         # AnalysisEngine final-segment count (for stage debug)
    is_steered: bool = False      # True = Track B (directive-influenced)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "stage": self.stage,
            "ready": self.ready,
            "reasoning": self.reasoning,
            "situation": self.situation,
            "current_state": self.current_state,
            "customer_needs": self.customer_needs,
            "open_questions": self.open_questions,
            "proposed_architecture": self.proposed_architecture,
            "key_recommendations": self.key_recommendations,
            "sources": self.sources,
            "current_state_diagram": self.current_state_diagram,
            "mermaid_diagram": self.mermaid_diagram,
            "action_items": self.action_items,
            "cycle_count": self.cycle_count,
            "segment_count": self.segment_count,
            "is_steered": self.is_steered,
            "timestamp": self.timestamp,
        }
