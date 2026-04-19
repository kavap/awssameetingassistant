"""Unit tests for the CCM engine.

Haiku calls are mocked — no AWS required.
All tests are async (pytest-asyncio asyncio_mode=auto).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.ccm.engine import CCMEngine, _call_haiku_sync
from backend.ccm.models import CCMUpdateEvent


def _haiku_response(
    aws_services: list[str] | None = None,
    competitors: list[str] | None = None,
    questions: list[str] | None = None,
    topics: list[str] | None = None,
    meeting_goal: str = "",
    should_recommend: bool = True,
) -> dict:
    """Build a fake Haiku extraction response."""
    return {
        "aws_services": aws_services or [],
        "competitors": competitors or [],
        "questions": questions or [],
        "topics": topics or [],
        "meeting_goal": meeting_goal,
        "should_recommend": should_recommend,
    }


async def test_aws_service_detection():
    engine = CCMEngine()
    with patch("backend.ccm.engine._call_haiku_sync", return_value=_haiku_response(
        aws_services=["S3"],
        topics=["data_lake"],
    )):
        await engine.process_transcript_segment(
            "We are evaluating Amazon S3 for our data lake storage.", is_final=True
        )

    services = engine.state.mentioned_services
    assert any(v.category == "aws" for v in services.values())
    assert "s3" in services


async def test_competitor_detection():
    engine = CCMEngine()
    with patch("backend.ccm.engine._call_haiku_sync", return_value=_haiku_response(
        competitors=["Snowflake"],
        topics=["data_warehouse"],
    )):
        await engine.process_transcript_segment(
            "Currently our data warehouse runs on Snowflake.", is_final=True
        )

    services = engine.state.mentioned_services
    comp = [v for v in services.values() if v.category == "competitor"]
    assert len(comp) >= 1
    assert "snowflake" in services


async def test_question_detection():
    engine = CCMEngine()
    with patch("backend.ccm.engine._call_haiku_sync", return_value=_haiku_response(
        aws_services=["DynamoDB", "Redshift"],
        questions=["Should we use DynamoDB or Redshift for this use case?"],
        topics=["database"],
    )):
        await engine.process_transcript_segment(
            "Should we use DynamoDB or Redshift for this use case?", is_final=True
        )

    questions = engine.state.open_questions
    assert len(questions) >= 1
    assert "DynamoDB" in questions[0].text or "Redshift" in questions[0].text


async def test_question_deduplication():
    engine = CCMEngine()
    response = _haiku_response(questions=["How does S3 pricing work?"])
    with patch("backend.ccm.engine._call_haiku_sync", return_value=response):
        await engine.process_transcript_segment("How does S3 pricing work?", is_final=True)
        await engine.process_transcript_segment("How does S3 pricing work?", is_final=True)

    active = [q for q in engine.state.open_questions if not q.resolved]
    assert len(active) == 1, "Duplicate questions should be deduplicated"


async def test_state_snapshot_is_serializable():
    import json
    engine = CCMEngine()
    with patch("backend.ccm.engine._call_haiku_sync", return_value=_haiku_response(
        aws_services=["Redshift Serverless"],
        topics=["migration", "data_warehouse"],
        meeting_goal="Migrate on-premise data warehouse to Redshift Serverless",
    )):
        await engine.process_transcript_segment(
            "We need to migrate from on-premise to Redshift Serverless.", is_final=True
        )

    snapshot = engine.get_state_snapshot()
    serialized = json.dumps(snapshot)
    assert len(serialized) > 0


async def test_ccm_update_event_returned_on_new_service():
    engine = CCMEngine()
    with patch("backend.ccm.engine._call_haiku_sync", return_value=_haiku_response(
        aws_services=["Glue"],
        topics=["data_lake"],
    )):
        event = await engine.process_transcript_segment("Let's talk about AWS Glue.", is_final=True)

    assert event is not None, "Should return CCMUpdateEvent on new service mention"
    assert isinstance(event, CCMUpdateEvent)


async def test_reset_clears_state():
    engine = CCMEngine()
    with patch("backend.ccm.engine._call_haiku_sync", return_value=_haiku_response(
        aws_services=["Bedrock"],
        topics=["machine_learning"],
    )):
        await engine.process_transcript_segment("Bedrock is great for GenAI.", is_final=True)

    old_session = engine.state.session_id
    engine.reset()
    assert engine.state.session_id != old_session
    assert len(engine.state.mentioned_services) == 0
    assert len(engine.state.open_questions) == 0


async def test_partial_transcript_no_haiku_call():
    """Partial segments must not trigger a Haiku call."""
    engine = CCMEngine()
    with patch("backend.ccm.engine._call_haiku_sync") as mock_haiku:
        result = await engine.process_transcript_segment("partial text here", is_final=False)
        mock_haiku.assert_not_called()

    assert result is None
    assert len(engine.state.full_transcript) == 0


async def test_topic_detection():
    engine = CCMEngine()
    with patch("backend.ccm.engine._call_haiku_sync", return_value=_haiku_response(
        aws_services=["DMS"],
        topics=["migration", "data_warehouse"],
        meeting_goal="Migrate on-premise data warehouse to AWS",
    )):
        for seg in [
            "We need to migrate our data warehouse from on-premise to the cloud.",
            "The migration will involve DMS for database migration.",
            "We want to modernize and lift and shift the workload.",
        ]:
            await engine.process_transcript_segment(seg, is_final=True)

    assert len(engine.state.active_topics) > 0


async def test_haiku_failure_returns_none():
    """If Haiku errors, engine returns None gracefully without crashing."""
    engine = CCMEngine()
    with patch("backend.ccm.engine._call_haiku_sync", side_effect=Exception("Bedrock timeout")):
        result = await engine.process_transcript_segment(
            "We are evaluating SageMaker for our ML workloads.", is_final=True
        )
    assert result is None
