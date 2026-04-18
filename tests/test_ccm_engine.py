"""Unit tests for the CCM engine. No external I/O required."""
import pytest

from backend.ccm.engine import CCMEngine
from backend.ccm.models import CCMUpdateEvent


def test_aws_service_detection():
    engine = CCMEngine()
    event = engine.process_transcript_segment(
        "We are evaluating Amazon S3 for our data lake storage.", is_final=True
    )
    services = engine.state.mentioned_services
    assert any(v.category == "aws" for v in services.values()), "Should detect an AWS service"
    assert any("s3" in k.lower() for k in services), "Should detect S3"


def test_competitor_detection():
    engine = CCMEngine()
    event = engine.process_transcript_segment(
        "Currently our data warehouse runs on Snowflake.", is_final=True
    )
    services = engine.state.mentioned_services
    comp = [v for v in services.values() if v.category == "competitor"]
    assert len(comp) >= 1, "Should detect at least one competitor"
    assert any("snowflake" in k for k in services), "Should detect Snowflake"


def test_question_detection():
    engine = CCMEngine()
    engine.process_transcript_segment(
        "Should we use DynamoDB or Redshift for this use case?", is_final=True
    )
    questions = engine.state.open_questions
    assert len(questions) >= 1, "Should detect an open question"
    assert "DynamoDB" in questions[0].text or "Redshift" in questions[0].text or "Should" in questions[0].text


def test_question_deduplication():
    engine = CCMEngine()
    engine.process_transcript_segment("How does S3 pricing work?", is_final=True)
    engine.process_transcript_segment("How does S3 pricing work?", is_final=True)
    questions = [q for q in engine.state.open_questions if not q.resolved]
    assert len(questions) == 1, "Duplicate questions should be deduplicated"


def test_state_snapshot_is_serializable():
    import json
    engine = CCMEngine()
    engine.process_transcript_segment("We need to migrate from on-premise to Redshift Serverless.", is_final=True)
    snapshot = engine.get_state_snapshot()
    # Should not raise
    serialized = json.dumps(snapshot)
    assert len(serialized) > 0


def test_ccm_update_event_returned_on_new_service():
    engine = CCMEngine()
    event = engine.process_transcript_segment("Let's talk about AWS Glue.", is_final=True)
    assert event is not None, "Should return CCMUpdateEvent on new service mention"
    assert isinstance(event, CCMUpdateEvent)


def test_reset_clears_state():
    engine = CCMEngine()
    engine.process_transcript_segment("Bedrock is great for GenAI.", is_final=True)
    old_session = engine.state.session_id
    engine.reset()
    assert engine.state.session_id != old_session
    assert len(engine.state.mentioned_services) == 0
    assert len(engine.state.open_questions) == 0


def test_partial_transcript_no_append():
    engine = CCMEngine()
    engine.process_transcript_segment("partial text here", is_final=False)
    # Partial transcripts should not be added to full_transcript
    assert len(engine.state.full_transcript) == 0


def test_topic_detection():
    engine = CCMEngine()
    for seg in [
        "We need to migrate our data warehouse from on-premise to the cloud.",
        "The migration will involve DMS for database migration.",
        "We want to modernize and lift and shift the workload.",
    ]:
        engine.process_transcript_segment(seg, is_final=True)
    topics = engine.state.active_topics
    assert len(topics) > 0, "Should detect at least one topic"
