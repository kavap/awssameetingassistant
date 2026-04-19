"""One-time setup: create AgentCore Memory resource.

Run:
    uv run python scripts/setup_agentcore.py

This creates:
    1. An AgentCore Memory resource with SEMANTIC strategy
    2. Prints the values to add to your .env

After running, add to .env:
    AGENTCORE_MEMORY_ID=...
    AGENTCORE_MEMORY_STRATEGY_ID=...

Then deploy the recommendation agent to AgentCore Runtime:
    npm install -g @aws/agentcore
    cd backend/agentcore
    agentcore deploy --name recommendation-agent --defaults

After deploy, add to .env:
    AGENTCORE_RUNTIME_ARN=arn:aws:bedrock:us-east-1:ACCOUNT:agent-runtime/...
"""
from __future__ import annotations

import sys
import time

import boto3
from rich.console import Console
from rich.panel import Panel

console = Console()


def setup_memory(region: str = "us-east-1", iam_role_arn: str | None = None) -> dict:
    control = boto3.client("bedrock-agentcore-control", region_name=region)
    iam = boto3.client("iam")

    # ---------------------------------------------------------------------------
    # Create or reuse IAM role for AgentCore Memory
    # ---------------------------------------------------------------------------
    role_name = "meeting-assistant-agentcore-memory-role"

    if not iam_role_arn:
        console.print(f"[cyan]Creating IAM role: {role_name}[/cyan]")
        try:
            trust = """{
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                    "Action": "sts:AssumeRole"
                }]
            }"""
            role_resp = iam.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=trust,
                Description="AgentCore Memory execution role for meeting assistant",
            )
            iam_role_arn = role_resp["Role"]["Arn"]

            # Attach Bedrock full access for memory operations
            iam.attach_role_policy(
                RoleName=role_name,
                PolicyArn="arn:aws:iam::aws:policy/AmazonBedrockFullAccess",
            )
            console.print(f"[green]IAM role created: {iam_role_arn}[/green]")
            time.sleep(10)  # IAM propagation
        except iam.exceptions.EntityAlreadyExistsException:
            iam_role_arn = iam.get_role(RoleName=role_name)["Role"]["Arn"]
            console.print(f"[yellow]IAM role already exists: {iam_role_arn}[/yellow]")

    # ---------------------------------------------------------------------------
    # Create Memory resource
    # ---------------------------------------------------------------------------
    memory_name = "meeting-assistant-customer-memory"
    console.print(f"[cyan]Creating AgentCore Memory: {memory_name}[/cyan]")

    resp = control.create_memory(
        name=memory_name,
        description="Cross-session customer context for AWS SA Meeting Assistant",
        memoryExecutionRoleArn=iam_role_arn,
        eventExpiryDuration=365,   # keep events for 1 year
        memoryStrategies=[
            {
                "builtInStrategy": {
                    "semanticMemoryStrategy": {
                        "name": "customer-context",
                        "description": (
                            "Extracts and stores key facts about the customer: "
                            "AWS services in use, architecture preferences, pain points, "
                            "open questions, and decisions made in past meetings."
                        ),
                    }
                }
            }
        ],
    )

    memory_id = resp["memory"]["memoryId"]
    strategies = resp["memory"].get("memoryStrategies", [])
    strategy_id = strategies[0]["memoryStrategyId"] if strategies else ""

    console.print(f"[green]Memory created: {memory_id}[/green]")
    return {"memory_id": memory_id, "strategy_id": strategy_id, "iam_role_arn": iam_role_arn}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Set up AgentCore Memory for meeting assistant")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--iam-role-arn", default=None, help="Existing IAM role ARN (skips creation)")
    args = parser.parse_args()

    console.print(Panel("[bold]AgentCore Memory Setup[/bold]", expand=False))

    try:
        result = setup_memory(region=args.region, iam_role_arn=args.iam_role_arn)
    except Exception as e:
        console.print(f"[red]Setup failed: {e}[/red]")
        sys.exit(1)

    console.print("\n[bold green]Add these to your .env:[/bold green]")
    console.print(f"AGENTCORE_MEMORY_ID={result['memory_id']}")
    console.print(f"AGENTCORE_MEMORY_STRATEGY_ID={result['strategy_id']}")
    console.print()
    console.print("[bold]Next: deploy the Recommendation Agent to AgentCore Runtime:[/bold]")
    console.print("  npm install -g @aws/agentcore")
    console.print("  cd backend/agentcore")
    console.print("  agentcore deploy --name recommendation-agent --defaults")
    console.print("Then add AGENTCORE_RUNTIME_ARN to your .env.")


if __name__ == "__main__":
    main()
