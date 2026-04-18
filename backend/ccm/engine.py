"""Conversation Context Map engine.

Pure Python, no I/O. Must complete process_transcript_segment in <10ms.
"""
from __future__ import annotations

import re
import time
from collections import Counter

from .models import CCMState, CCMUpdateEvent, MentionedService, OpenQuestion, Topic

# ---------------------------------------------------------------------------
# Service name vocabulary
# ---------------------------------------------------------------------------

AWS_SERVICES: list[str] = [
    # Compute
    "EC2", "Lambda", "ECS", "EKS", "Fargate", "Batch", "Lightsail",
    "Elastic Beanstalk", "App Runner",
    # Storage
    "S3", "EBS", "EFS", "FSx", "Storage Gateway", "S3 Glacier",
    "S3 Tables",
    # Database
    "RDS", "Aurora", "DynamoDB", "ElastiCache", "MemoryDB", "DocumentDB",
    "Neptune", "Timestream", "Keyspaces", "QLDB",
    # Analytics / Data
    "Redshift", "Athena", "Glue", "EMR", "Kinesis", "MSK", "Lake Formation",
    "Data Exchange", "OpenSearch", "QuickSight", "DataZone",
    "Redshift Serverless", "Glue DataBrew",
    # AI / ML
    "Bedrock", "SageMaker", "Rekognition", "Comprehend", "Textract",
    "Transcribe", "Polly", "Lex", "Kendra", "Personalize", "Forecast",
    "Bedrock AgentCore", "Nova",
    # Networking
    "VPC", "CloudFront", "Route 53", "API Gateway", "Direct Connect",
    "Transit Gateway", "Global Accelerator", "PrivateLink",
    # Integration / Messaging
    "SQS", "SNS", "EventBridge", "Step Functions", "AppFlow", "MQ",
    # DevOps / Management
    "CloudFormation", "CDK", "CloudWatch", "Systems Manager", "Config",
    "Control Tower", "Organizations", "IAM",
    # Migration
    "DMS", "SCT", "MGN", "DataSync",
    # Security
    "WAF", "Shield", "GuardDuty", "Security Hub", "Macie", "Inspector",
    # Other
    "Outposts", "Local Zones", "Wavelength",
]

COMPETITOR_SERVICES: list[str] = [
    "Snowflake", "Databricks", "Confluent", "Elastic", "Elasticsearch",
    "ClickHouse", "BigQuery", "Google Cloud", "Azure", "Azure Blob",
    "Azure Synapse", "Azure Data Factory", "dbt", "Terraform", "Pulumi",
    "Starburst", "Trino", "Fivetran", "Airbyte", "Kafka",
    "MongoDB", "Cassandra", "PostgreSQL", "MySQL",
]

# Build regex patterns (longest match first to avoid partial matches)
_aws_sorted = sorted(AWS_SERVICES, key=len, reverse=True)
_comp_sorted = sorted(COMPETITOR_SERVICES, key=len, reverse=True)

_AWS_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(s) for s in _aws_sorted) + r")\b",
    re.IGNORECASE,
)
_COMP_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(s) for s in _comp_sorted) + r")\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Question detection
# ---------------------------------------------------------------------------

_QUESTION_STARTERS = re.compile(
    r"^(what|how|why|when|where|who|which|should|can|could|would|is there|"
    r"are there|do we|does|will|shall|isn't|aren't|won't)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Topic vocabulary (domain-specific keyword clusters)
# ---------------------------------------------------------------------------

TOPIC_CLUSTERS: dict[str, list[str]] = {
    "data_warehouse": ["warehouse", "redshift", "snowflake", "etl", "schema", "query", "bi", "analytics"],
    "data_lake": ["lake", "s3", "parquet", "delta", "iceberg", "glue", "athena", "hudi"],
    "streaming": ["kinesis", "kafka", "msk", "streaming", "realtime", "real-time", "event", "firehose"],
    "machine_learning": ["ml", "model", "training", "inference", "sagemaker", "bedrock", "llm", "genai", "generative"],
    "migration": ["migrate", "migration", "on-premise", "on-prem", "lift", "shift", "modernize", "dms"],
    "cost_optimization": ["cost", "pricing", "optimize", "savings", "reserved", "spot", "budget"],
    "security": ["security", "iam", "encryption", "compliance", "audit", "gdpr", "hipaa", "waf", "guard"],
    "serverless": ["serverless", "lambda", "fargate", "app runner", "no server"],
    "networking": ["vpc", "network", "subnet", "peering", "direct connect", "transit", "latency"],
    "database": ["database", "rds", "aurora", "dynamodb", "nosql", "sql", "postgres", "mysql"],
    "comparison": ["versus", "vs", "compare", "comparison", "better", "difference", "pros", "cons"],
}


def _jaccard_similarity(text_a: str, text_b: str) -> float:
    tokens_a = set(text_a.lower().split())
    tokens_b = set(text_b.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


class CCMEngine:
    """Stateful Conversation Context Map engine.

    All methods are synchronous and must complete in <10ms per call.
    """

    def __init__(self) -> None:
        self._state = CCMState()
        self._recent_window: list[str] = []  # last 10 final segments

    @property
    def state(self) -> CCMState:
        return self._state

    def reset(self) -> None:
        self._state = CCMState()
        self._recent_window = []

    def process_transcript_segment(
        self, text: str, is_final: bool
    ) -> CCMUpdateEvent | None:
        """Process one transcript segment. Returns an event if something significant changed."""
        if not text.strip():
            return None

        event_type: str | None = None

        # --- Service detection ---
        aws_matches = _AWS_PATTERN.findall(text)
        comp_matches = _COMP_PATTERN.findall(text)

        for match in aws_matches:
            key = match.lower()
            if key in self._state.mentioned_services:
                svc = self._state.mentioned_services[key]
                svc.mention_count += 1
                svc.last_seen_at = time.time()
            else:
                self._state.mentioned_services[key] = MentionedService(
                    name=match, category="aws"
                )
                event_type = "service_mentioned"

        for match in comp_matches:
            key = match.lower()
            if key in self._state.mentioned_services:
                svc = self._state.mentioned_services[key]
                svc.mention_count += 1
                svc.last_seen_at = time.time()
            else:
                self._state.mentioned_services[key] = MentionedService(
                    name=match, category="competitor"
                )
                event_type = "competitor_mentioned"

        if is_final:
            # --- Append to transcript and rolling window ---
            self._state.full_transcript.append(text)
            self._recent_window.append(text)
            if len(self._recent_window) > 10:
                self._recent_window.pop(0)

            # --- Question detection ---
            stripped = text.strip()
            is_question = stripped.endswith("?") or bool(
                _QUESTION_STARTERS.match(stripped)
            )
            if is_question:
                # Dedup: skip if similar question already exists
                is_duplicate = any(
                    _jaccard_similarity(q.text, stripped) > 0.5
                    for q in self._state.open_questions
                    if not q.resolved
                )
                if not is_duplicate:
                    self._state.open_questions.append(
                        OpenQuestion(text=stripped)
                    )
                    event_type = "question_detected"

            # --- Topic extraction ---
            window_text = " ".join(self._recent_window).lower()
            window_tokens = window_text.split()
            token_counts = Counter(window_tokens)

            topic_scores: dict[str, float] = {}
            for topic_name, keywords in TOPIC_CLUSTERS.items():
                score = sum(token_counts.get(kw, 0) for kw in keywords)
                if score > 0:
                    topic_scores[topic_name] = score

            if topic_scores:
                top_topic = max(topic_scores, key=lambda k: topic_scores[k])
                top_score = topic_scores[top_topic]
                # Normalize confidence (max reasonable score ~= 10)
                confidence = min(top_score / 10.0, 1.0)

                existing = next(
                    (t for t in self._state.active_topics if t.name == top_topic),
                    None,
                )
                if existing:
                    existing.confidence = confidence
                    existing.last_seen_at = time.time()
                else:
                    self._state.active_topics.append(
                        Topic(
                            name=top_topic,
                            keywords=TOPIC_CLUSTERS[top_topic],
                            confidence=confidence,
                        )
                    )
                    if event_type is None:
                        event_type = "topic_shift"

                # Keep only top 5 topics sorted by confidence
                self._state.active_topics.sort(key=lambda t: -t.confidence)
                self._state.active_topics = self._state.active_topics[:5]

            # --- Set meeting goal from first 60s of transcript ---
            if (
                not self._state.meeting_goal
                and len(self._state.full_transcript) >= 3
            ):
                combined = " ".join(self._state.full_transcript[:5])
                # Simple heuristic: first 100 chars of combined transcript
                self._state.meeting_goal = combined[:120].strip()

        self._state.last_updated_at = time.time()

        if event_type:
            self._state.recommendation_trigger_count += 1
            return CCMUpdateEvent(
                event_type=event_type,  # type: ignore[arg-type]
                session_id=self._state.session_id,
                context_snapshot=self._state.to_dict(),
                trigger_text=text[:200],
            )

        return None

    def get_state_snapshot(self) -> dict:
        return self._state.to_dict()
