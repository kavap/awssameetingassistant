#!/usr/bin/env python3
"""One-time setup script: creates S3 bucket + Bedrock Knowledge Base.

Run this ONCE before using the assistant. It:
  1. Creates an S3 bucket for KB documents
  2. Creates a Bedrock Knowledge Base (backed by OpenSearch Serverless)
     with Cohere Embed English v3 as the embedding model
  3. Creates an S3 data source attached to the KB
  4. Prints the IDs to add to your .env file

Prerequisites:
  - AWS credentials configured (instance role or ~/.aws/credentials)
  - IAM permissions:
      bedrock:CreateKnowledgeBase, bedrock:CreateDataSource,
      s3:CreateBucket, s3:PutBucketPolicy,
      iam:CreateRole, iam:AttachRolePolicy (or a pre-existing Bedrock execution role)

Usage:
    uv run python scripts/setup_kb.py
    uv run python scripts/setup_kb.py --region us-west-2 --name my-kb
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

# Cohere Embed English v3 ARN (same in all regions)
COHERE_EMBED_ARN = "arn:aws:bedrock:{region}::foundation-model/cohere.embed-english-v3"

# Bedrock execution role trust policy
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
        {
            "Effect": "Allow",
            "Action": ["bedrock:InvokeModel"],
            "Resource": "*",
        },
        {
            "Effect": "Allow",
            "Action": ["s3:GetObject", "s3:ListBucket"],
            "Resource": "*",
        },
        {
            "Effect": "Allow",
            "Action": [
                "aoss:APIAccessAll",
            ],
            "Resource": "*",
        },
    ],
}


def get_account_id(session) -> str:
    return session.client("sts").get_caller_identity()["Account"]


def create_s3_bucket(s3, bucket_name: str, region: str) -> bool:
    try:
        if region == "us-east-1":
            s3.create_bucket(Bucket=bucket_name)
        else:
            s3.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={"LocationConstraint": region},
            )
        # Block public access
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


def create_bedrock_execution_role(iam, account_id: str, role_name: str, region: str) -> str | None:
    """Create IAM role for Bedrock KB to call Cohere + access S3."""
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
        time.sleep(10)  # IAM propagation delay
        return role_arn
    except iam.exceptions.EntityAlreadyExistsException:
        resp = iam.get_role(RoleName=role_name)
        role_arn = resp["Role"]["Arn"]
        console.print(f"[yellow]→[/yellow] IAM role already exists: [bold]{role_arn}[/bold]")
        return role_arn
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to create IAM role: {e}")
        console.print(
            "[yellow]Hint:[/yellow] If you already have a Bedrock execution role, "
            "set --role-arn <arn> to skip role creation."
        )
        return None


def create_knowledge_base(bedrock_agent, role_arn: str, kb_name: str, region: str) -> tuple[str, str] | None:
    """Create Bedrock KB with OpenSearch Serverless + Cohere embed. Returns (kb_id, kb_arn)."""
    embed_model_arn = COHERE_EMBED_ARN.format(region=region)
    try:
        resp = bedrock_agent.create_knowledge_base(
            name=kb_name,
            description="AWS SA Meeting Intelligence Assistant knowledge base",
            roleArn=role_arn,
            knowledgeBaseConfiguration={
                "type": "VECTOR",
                "vectorKnowledgeBaseConfiguration": {
                    "embeddingModelArn": embed_model_arn,
                    "embeddingModelConfiguration": {
                        "bedrockEmbeddingModelConfiguration": {
                            "dimensions": 1024,
                        }
                    },
                },
            },
            storageConfiguration={
                "type": "OPENSEARCH_SERVERLESS",
                # Bedrock auto-provisions the OpenSearch Serverless collection
                # when using the console. For API creation, we use the managed option.
            },
        )
        kb = resp["knowledgeBase"]
        console.print(f"[green]✓[/green] Knowledge Base created: [bold]{kb['knowledgeBaseId']}[/bold]")
        return kb["knowledgeBaseId"], kb["knowledgeBaseArn"]
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to create Knowledge Base: {e}")
        console.print(
            "\n[yellow]Alternative:[/yellow] Create the KB manually in the AWS Console:\n"
            "  1. Open AWS Console → Bedrock → Knowledge Bases → Create\n"
            "  2. Choose: Amazon OpenSearch Serverless\n"
            "  3. Embedding model: Cohere Embed English v3\n"
            "  4. Data source: Amazon S3 → select your bucket\n"
            "  5. Copy the KB ID and Data Source ID to .env\n"
        )
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
                "chunkingConfiguration": {
                    "chunkingStrategy": "NONE",  # we chunk ourselves in ingest.py
                }
            },
        )
        ds_id = resp["dataSource"]["dataSourceId"]
        console.print(f"[green]✓[/green] Data Source created: [bold]{ds_id}[/bold]")
        return ds_id
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to create data source: {e}")
        return None


def main(region: str, kb_name: str, bucket_suffix: str, role_arn: str | None) -> None:
    console.rule("[bold blue]Bedrock KB Setup — AWS SA Meeting Assistant[/bold blue]")

    session = boto3.Session(region_name=region)
    account_id = get_account_id(session)
    console.print(f"Account: [bold]{account_id}[/bold]  |  Region: [bold]{region}[/bold]")

    bucket_name = f"meeting-assistant-kb-{account_id[:8]}-{bucket_suffix}"
    role_name = "MeetingAssistantBedrockKBRole"
    s3_prefix = "kb-documents/"

    # 1. S3 bucket
    s3 = session.client("s3")
    if not create_s3_bucket(s3, bucket_name, region):
        sys.exit(1)

    # 2. IAM role (skip if provided)
    iam = session.client("iam")
    if not role_arn:
        role_arn = create_bedrock_execution_role(iam, account_id, role_name, region)
        if not role_arn:
            console.print("\n[bold]Manual option:[/bold] Re-run with --role-arn <existing_role_arn>")
            sys.exit(1)

    # 3. Knowledge Base
    bedrock_agent = session.client("bedrock-agent")
    result = create_knowledge_base(bedrock_agent, role_arn, kb_name, region)
    if not result:
        sys.exit(1)
    kb_id, _ = result

    # Wait for KB to be ACTIVE
    console.print("Waiting for KB to become ACTIVE...")
    for _ in range(30):
        kb_info = bedrock_agent.get_knowledge_base(knowledgeBaseId=kb_id)
        status = kb_info["knowledgeBase"]["status"]
        if status == "ACTIVE":
            break
        elif status == "FAILED":
            console.print(f"[red]✗[/red] KB creation failed: {kb_info}")
            sys.exit(1)
        time.sleep(5)
    console.print(f"[green]✓[/green] KB status: ACTIVE")

    # 4. Data source
    ds_id = create_s3_data_source(bedrock_agent, kb_id, bucket_name, s3_prefix, f"{kb_name}-s3-source")
    if not ds_id:
        sys.exit(1)

    # Print .env values
    env_block = (
        f"BEDROCK_KB_S3_BUCKET={bucket_name}\n"
        f"BEDROCK_KB_ID={kb_id}\n"
        f"BEDROCK_KB_DATA_SOURCE_ID={ds_id}\n"
        f"BEDROCK_EMBEDDING_MODEL=cohere.embed-english-v3\n"
    )

    console.print(Panel(
        f"[bold green]Setup complete![/bold green]\n\n"
        f"Add these to your [bold].env[/bold] file:\n\n"
        f"[bold cyan]{env_block}[/bold cyan]\n"
        f"Then run ingestion:\n"
        f"  [bold]uv run python scripts/ingest.py --urls data/urls.txt[/bold]",
        title="Next Steps",
        border_style="green",
    ))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create Bedrock KB for Meeting Assistant.")
    parser.add_argument("--region", default=settings.aws_region)
    parser.add_argument("--name", default="meeting-assistant-kb")
    parser.add_argument("--bucket-suffix", default="prod")
    parser.add_argument("--role-arn", default=None, help="Use existing IAM role ARN")
    args = parser.parse_args()
    main(args.region, args.name, args.bucket_suffix, args.role_arn)
