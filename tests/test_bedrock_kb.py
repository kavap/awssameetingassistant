"""Unit tests for Bedrock KB client — mocked boto3 calls, no AWS required."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_agent_runtime():
    """Patch the bedrock-agent-runtime boto3 client used inside bedrock_kb."""
    mock_client = MagicMock()
    with patch("backend.knowledge_base.bedrock_kb._agent_runtime", mock_client):
        yield mock_client


def _make_retrieve_response(results: list[dict]) -> dict:
    return {
        "retrievalResults": [
            {
                "content": {"text": r["text"]},
                "score": r.get("score", 0.9),
                "location": {"type": "S3", "s3Location": {"uri": f"s3://bucket/{i}.txt"}},
                "metadata": {
                    "source_url": r.get("url", "https://docs.aws.amazon.com"),
                    "title": r.get("title", "AWS Docs"),
                    "chunk_index": 0,
                },
            }
            for i, r in enumerate(results)
        ]
    }


async def test_retrieve_returns_results(mock_agent_runtime):
    """retrieve() should parse and return KB results correctly."""
    from backend.knowledge_base import bedrock_kb

    mock_agent_runtime.retrieve.return_value = _make_retrieve_response([
        {"text": "Amazon Redshift is a fully managed data warehouse.", "url": "https://docs.aws.amazon.com/redshift/"},
        {"text": "Redshift Serverless automatically scales capacity.", "url": "https://docs.aws.amazon.com/redshift/serverless/"},
    ])

    with patch.object(bedrock_kb.settings, "bedrock_kb_id", "TESTKBID1234"):
        results = await bedrock_kb.retrieve("Redshift data warehouse pricing", limit=5)

    assert len(results) == 2
    assert results[0]["text"] == "Amazon Redshift is a fully managed data warehouse."
    assert results[0]["url"] == "https://docs.aws.amazon.com/redshift/"
    assert isinstance(results[0]["score"], float)


async def test_retrieve_empty_when_kb_not_configured():
    """retrieve() should return [] and log a warning when BEDROCK_KB_ID is unset."""
    from backend.knowledge_base import bedrock_kb

    with patch.object(bedrock_kb.settings, "bedrock_kb_id", ""):
        results = await bedrock_kb.retrieve("any query")

    assert results == []


async def test_retrieve_returns_empty_on_boto3_error(mock_agent_runtime):
    """retrieve() should return [] gracefully on any boto3 exception."""
    from backend.knowledge_base import bedrock_kb

    mock_agent_runtime.retrieve.side_effect = Exception("ServiceUnavailableException")

    with patch.object(bedrock_kb.settings, "bedrock_kb_id", "TESTKBID1234"):
        results = await bedrock_kb.retrieve("Glue ETL best practices")

    assert results == []


async def test_retrieve_uses_hybrid_search_type(mock_agent_runtime):
    """retrieve() should pass overrideSearchType=HYBRID by default."""
    from backend.knowledge_base import bedrock_kb

    mock_agent_runtime.retrieve.return_value = _make_retrieve_response([])

    with patch.object(bedrock_kb.settings, "bedrock_kb_id", "TESTKBID1234"), \
         patch.object(bedrock_kb.settings, "bedrock_kb_search_type", "HYBRID"):
        await bedrock_kb.retrieve("S3 performance tuning")

    call_kwargs = mock_agent_runtime.retrieve.call_args[1]
    search_config = call_kwargs["retrievalConfiguration"]["vectorSearchConfiguration"]
    assert search_config.get("overrideSearchType") == "HYBRID"


def test_is_configured_true_when_kb_id_set():
    from backend.knowledge_base import bedrock_kb
    with patch.object(bedrock_kb.settings, "bedrock_kb_id", "SOMEID"):
        assert bedrock_kb.is_configured() is True


def test_is_configured_false_when_kb_id_empty():
    from backend.knowledge_base import bedrock_kb
    with patch.object(bedrock_kb.settings, "bedrock_kb_id", ""):
        assert bedrock_kb.is_configured() is False
