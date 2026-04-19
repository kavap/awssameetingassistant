#!/usr/bin/env python3
"""One-time setup script: creates AOSS collection + Bedrock Knowledge Base.

Run this ONCE before using the assistant. It:
  1. Creates an S3 bucket for KB documents
  2. Creates an IAM execution role for Bedrock KB
  3. Creates an OpenSearch Serverless collection (vector store)
  4. Creates the vector index inside the collection
  5. Creates a Bedrock Knowledge Base backed by the AOSS collection
  6. Creates an S3 data source attached to the KB
  7. Prints the IDs to add to your .env file

Usage:
    uv run python scripts/setup_kb.py
    uv run python scripts/setup_kb.py --region us-west-2
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import boto3
from rich.console import Console
from rich.panel import Panel

from backend.config import settings

console = Console()

COHERE_EMBED_ARN = "arn:aws:bedrock:{region}::foundation-model/cohere.embed-english-v3"

TRUST_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"Service": "bedrock.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }
    ],
}

BEDROCK_KB_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {"Effect": "Allow", "Action": ["bedrock:InvokeModel"], "Resource": "*"},
        {"Effect": "Allow", "Action": ["s3:GetObject", "s3:ListBucket"], "Resource": "*"},
        {"Effect": "Allow", "Action": ["aoss:APIAccessAll"], "Resource": "*"},
    ],
}

# Vector index name inside the AOSS collection
INDEX_NAME = "meeting-assistant-index"


# ---------------------------------------------------------------------------
# S3 bucket
# ---------------------------------------------------------------------------

def create_s3_bucket(s3, bucket_name: str, region: str) -> bool:
    try:
        if region == "us-east-1":
            s3.create_bucket(Bucket=bucket_name)
        else:
            s3.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={"LocationConstraint": region},
            )
        s3.put_public_access_block(
            Bucket=bucket_name,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            },
        )
        console.print(f"[green]✓[/green] S3 bucket created: [bold]{bucket_name}[/bold]")
        return True
    except s3.exceptions.BucketAlreadyOwnedByYou:
        console.print(f"[yellow]→[/yellow] S3 bucket already exists: [bold]{bucket_name}[/bold]")
        return True
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to create S3 bucket: {e}")
        return False


# ---------------------------------------------------------------------------
# IAM role
# ---------------------------------------------------------------------------

def create_bedrock_execution_role(iam, role_name: str) -> str | None:
    try:
        resp = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(TRUST_POLICY),
            Description="Bedrock Knowledge Base execution role for Meeting Assistant",
        )
        role_arn = resp["Role"]["Arn"]
        iam.put_role_policy(
            RoleName=role_name,
            PolicyName="BedrockKBPolicy",
            PolicyDocument=json.dumps(BEDROCK_KB_POLICY),
        )
        console.print(f"[green]✓[/green] IAM role created: [bold]{role_arn}[/bold]")
        time.sleep(12)  # IAM propagation
        return role_arn
    except iam.exceptions.EntityAlreadyExistsException:
        role_arn = iam.get_role(RoleName=role_name)["Role"]["Arn"]
        console.print(f"[yellow]→[/yellow] IAM role already exists: [bold]{role_arn}[/bold]")
        return role_arn
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to create IAM role: {e}")
        return None


# ---------------------------------------------------------------------------
# OpenSearch Serverless collection
# ---------------------------------------------------------------------------

def create_aoss_collection(
    aoss, collection_name: str, role_arn: str, caller_arn: str, region: str
) -> tuple[str, str] | None:
    """Create AOSS collection with policies. Returns (collection_arn, endpoint)."""

    # 1. Encryption policy (required before collection creation)
    try:
        aoss.create_security_policy(
            name=f"{collection_name}-enc",
            type="encryption",
            policy=json.dumps({
                "Rules": [{"ResourceType": "collection", "Resource": [f"collection/{collection_name}"]}],
                "AWSOwnedKey": True,
            }),
        )
        console.print("[green]✓[/green] AOSS encryption policy created")
    except aoss.exceptions.ConflictException:
        console.print("[yellow]→[/yellow] AOSS encryption policy already exists")

    # 2. Network policy (public access required for Bedrock KB to reach the collection)
    try:
        aoss.create_security_policy(
            name=f"{collection_name}-net",
            type="network",
            policy=json.dumps([{
                "Rules": [
                    {"ResourceType": "collection", "Resource": [f"collection/{collection_name}"]},
                    {"ResourceType": "dashboard", "Resource": [f"collection/{collection_name}"]},
                ],
                "AllowFromPublic": True,
            }]),
        )
        console.print("[green]✓[/green] AOSS network policy created")
    except aoss.exceptions.ConflictException:
        console.print("[yellow]→[/yellow] AOSS network policy already exists")

    # 3. Create collection
    try:
        resp = aoss.create_collection(
            name=collection_name,
            type="VECTORSEARCH",
            description="Meeting assistant KB vector store",
        )
        collection_id = resp["createCollectionDetail"]["id"]
        collection_arn = resp["createCollectionDetail"]["arn"]
        console.print(f"[green]✓[/green] AOSS collection created: [bold]{collection_id}[/bold]")
    except aoss.exceptions.ConflictException:
        resp = aoss.batch_get_collection(names=[collection_name])
        detail = resp["collectionDetails"][0]
        collection_id = detail["id"]
        collection_arn = detail["arn"]
        console.print(f"[yellow]→[/yellow] AOSS collection already exists: [bold]{collection_id}[/bold]")

    # 4. Data access policy — two separate statements (index + collection)
    #    Use aoss:* wildcard to avoid per-permission enum validation issues.
    try:
        aoss.create_access_policy(
            name=f"{collection_name}-access",
            type="data",
            policy=json.dumps([
                {
                    "Rules": [{
                        "ResourceType": "index",
                        "Resource": [f"index/{collection_name}/*"],
                        "Permission": ["aoss:*"],
                    }],
                    "Principal": [role_arn, caller_arn],
                },
                {
                    "Rules": [{
                        "ResourceType": "collection",
                        "Resource": [f"collection/{collection_name}"],
                        "Permission": ["aoss:*"],
                    }],
                    "Principal": [role_arn, caller_arn],
                },
            ]),
        )
        console.print("[green]✓[/green] AOSS data access policy created")
    except aoss.exceptions.ConflictException:
        console.print("[yellow]→[/yellow] AOSS data access policy already exists")

    # 5. Wait for ACTIVE
    console.print("Waiting for AOSS collection to become ACTIVE (may take 2-3 min)...")
    for _ in range(36):
        resp = aoss.batch_get_collection(ids=[collection_id])
        status = resp["collectionDetails"][0]["status"]
        if status == "ACTIVE":
            break
        elif status == "FAILED":
            console.print(f"[red]✗[/red] AOSS collection failed")
            return None
        console.print(f"  status: {status} …")
        time.sleep(10)
    else:
        console.print("[red]✗[/red] Timed out waiting for AOSS collection")
        return None

    endpoint = resp["collectionDetails"][0]["collectionEndpoint"]
    console.print(f"[green]✓[/green] AOSS collection ACTIVE: {endpoint}")
    return collection_arn, endpoint


# ---------------------------------------------------------------------------
# Vector index
# ---------------------------------------------------------------------------

def create_vector_index(endpoint: str, region: str) -> bool:
    """Create 1024-dim KNN vector index in the AOSS collection."""
    try:
        from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection

        credentials = boto3.Session().get_credentials()
        auth = AWSV4SignerAuth(credentials, region, "aoss")

        host = endpoint.replace("https://", "")
        client = OpenSearch(
            hosts=[{"host": host, "port": 443}],
            http_auth=auth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            timeout=30,
        )

        if client.indices.exists(index=INDEX_NAME):
            console.print(f"[yellow]→[/yellow] Vector index already exists: {INDEX_NAME}")
            return True

        index_body = {
            "settings": {"index.knn": True},
            "mappings": {
                "properties": {
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": 1024,
                        "method": {
                            "name": "hnsw",
                            "space_type": "cosinesimil",
                            "engine": "faiss",
                        },
                    },
                    "text": {"type": "text"},
                    "metadata": {"type": "text"},
                }
            },
        }
        client.indices.create(index=INDEX_NAME, body=index_body)
        console.print(f"[green]✓[/green] Vector index created: [bold]{INDEX_NAME}[/bold]")
        return True
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to create vector index: {e}")
        return False


# ---------------------------------------------------------------------------
# Bedrock Knowledge Base
# ---------------------------------------------------------------------------

def create_knowledge_base(
    bedrock_agent, role_arn: str, collection_arn: str, kb_name: str, region: str
) -> tuple[str, str] | None:
    embed_arn = COHERE_EMBED_ARN.format(region=region)
    try:
        resp = bedrock_agent.create_knowledge_base(
            name=kb_name,
            description="AWS SA Meeting Intelligence Assistant knowledge base",
            roleArn=role_arn,
            knowledgeBaseConfiguration={
                "type": "VECTOR",
                "vectorKnowledgeBaseConfiguration": {
                    "embeddingModelArn": embed_arn,
                },
            },
            storageConfiguration={
                "type": "OPENSEARCH_SERVERLESS",
                "opensearchServerlessConfiguration": {
                    "collectionArn": collection_arn,
                    "vectorIndexName": INDEX_NAME,
                    "fieldMapping": {
                        "vectorField": "embedding",
                        "textField": "text",
                        "metadataField": "metadata",
                    },
                },
            },
        )
        kb = resp["knowledgeBase"]
        console.print(f"[green]✓[/green] Knowledge Base created: [bold]{kb['knowledgeBaseId']}[/bold]")
        return kb["knowledgeBaseId"], kb["knowledgeBaseArn"]
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to create Knowledge Base: {e}")
        return None


def create_s3_data_source(bedrock_agent, kb_id: str, bucket_name: str, prefix: str, ds_name: str) -> str | None:
    try:
        resp = bedrock_agent.create_data_source(
            knowledgeBaseId=kb_id,
            name=ds_name,
            description="AWS documentation chunks from ingest.py",
            dataSourceConfiguration={
                "type": "S3",
                "s3Configuration": {
                    "bucketArn": f"arn:aws:s3:::{bucket_name}",
                    "inclusionPrefixes": [prefix],
                },
            },
            vectorIngestionConfiguration={
                "chunkingConfiguration": {"chunkingStrategy": "NONE"}
            },
        )
        ds_id = resp["dataSource"]["dataSourceId"]
        console.print(f"[green]✓[/green] Data Source created: [bold]{ds_id}[/bold]")
        return ds_id
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to create data source: {e}")
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(region: str, kb_name: str, bucket_suffix: str, role_arn: str | None) -> None:
    console.rule("[bold blue]Bedrock KB Setup — AWS SA Meeting Assistant[/bold blue]")

    session = boto3.Session(region_name=region)
    account_id = session.client("sts").get_caller_identity()["Account"]
    caller_arn = session.client("sts").get_caller_identity()["Arn"]
    console.print(f"Account: [bold]{account_id}[/bold]  |  Region: [bold]{region}[/bold]")

    bucket_name = f"meeting-assistant-kb-{account_id[:8]}-{bucket_suffix}"
    role_name = "MeetingAssistantBedrockKBRole"
    collection_name = "meeting-assistant-kb"
    s3_prefix = "kb-documents/"

    # 1. S3 bucket
    if not create_s3_bucket(session.client("s3"), bucket_name, region):
        sys.exit(1)

    # 2. IAM role
    if not role_arn:
        role_arn = create_bedrock_execution_role(session.client("iam"), role_name)
        if not role_arn:
            sys.exit(1)

    # 3. AOSS collection + policies
    aoss = session.client("opensearchserverless")
    result = create_aoss_collection(aoss, collection_name, role_arn, caller_arn, region)
    if not result:
        sys.exit(1)
    collection_arn, endpoint = result

    # 4. Vector index
    if not create_vector_index(endpoint, region):
        sys.exit(1)

    # 5. Bedrock KB
    bedrock_agent = session.client("bedrock-agent")
    kb_result = create_knowledge_base(bedrock_agent, role_arn, collection_arn, kb_name, region)
    if not kb_result:
        sys.exit(1)
    kb_id, _ = kb_result

    # Wait for KB ACTIVE
    console.print("Waiting for KB to become ACTIVE...")
    for _ in range(30):
        status = bedrock_agent.get_knowledge_base(knowledgeBaseId=kb_id)["knowledgeBase"]["status"]
        if status == "ACTIVE":
            break
        elif status == "FAILED":
            console.print("[red]✗[/red] KB failed to activate")
            sys.exit(1)
        time.sleep(5)
    console.print("[green]✓[/green] KB status: ACTIVE")

    # 6. Data source
    ds_id = create_s3_data_source(
        bedrock_agent, kb_id, bucket_name, s3_prefix, f"{kb_name}-s3-source"
    )
    if not ds_id:
        sys.exit(1)

    env_block = (
        f"BEDROCK_KB_S3_BUCKET={bucket_name}\n"
        f"BEDROCK_KB_ID={kb_id}\n"
        f"BEDROCK_KB_DATA_SOURCE_ID={ds_id}\n"
        f"BEDROCK_EMBEDDING_MODEL=cohere.embed-english-v3\n"
    )
    console.print(Panel(
        f"[bold green]Setup complete![/bold green]\n\n"
        f"Add these to your [bold].env[/bold]:\n\n"
        f"[bold cyan]{env_block}[/bold cyan]\n"
        f"Then seed the KB:\n"
        f"  [bold]uv run python scripts/ingest.py --urls data/urls.txt[/bold]",
        title="Next Steps",
        border_style="green",
    ))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default=settings.aws_region)
    parser.add_argument("--name", default="meeting-assistant-kb")
    parser.add_argument("--bucket-suffix", default="prod")
    parser.add_argument("--role-arn", default=None)
    args = parser.parse_args()
    main(args.region, args.name, args.bucket_suffix, args.role_arn)
