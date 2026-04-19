#!/usr/bin/env python3
"""AWS Documentation URL collector for KB seeding.

Two modes:
  1. CURATED (default): writes a built-in list of high-value AWS docs URLs.
     Works offline / behind VPN / no external network needed.
  2. LIVE (--live): attempts to discover additional URLs via AWS docs search.
     Falls back to curated list if network access is unavailable.

Usage:
    # Recommended (always works):
    uv run python scripts/scrape_aws_docs.py --output data/urls.txt

    # Try to augment with live search (requires docs.aws.amazon.com access):
    uv run python scripts/scrape_aws_docs.py --output data/urls.txt --live

Then ingest:
    uv run python scripts/ingest.py --urls data/urls.txt
"""
from __future__ import annotations

import argparse
import html
import logging
import re
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import quote_plus

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Curated high-value AWS documentation URLs
# Covers: data migration, data lake, warehouse, analytics, ML, Well-Architected
# ---------------------------------------------------------------------------

CURATED_URLS = [
    # --- Migration ---
    "https://docs.aws.amazon.com/dms/latest/userguide/Welcome.html",
    "https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Target.Redshift.html",
    "https://docs.aws.amazon.com/SchemaConversionTool/latest/userguide/CHAP_Welcome.html",
    "https://aws.amazon.com/solutions/implementations/aws-landing-zone/",
    "https://docs.aws.amazon.com/prescriptive-guidance/latest/patterns/migrate-a-teradata-data-warehouse-to-amazon-redshift.html",
    "https://docs.aws.amazon.com/emr/latest/ManagementGuide/emr-what-is-emr.html",
    "https://docs.aws.amazon.com/emr/latest/ManagementGuide/emr-plan-hadoop-version.html",

    # --- Amazon Redshift ---
    "https://docs.aws.amazon.com/redshift/latest/mgmt/welcome.html",
    "https://docs.aws.amazon.com/redshift/latest/dg/c_best-practices-best-dist-key.html",
    "https://docs.aws.amazon.com/redshift/latest/mgmt/working-with-serverless.html",
    "https://docs.aws.amazon.com/redshift/latest/dg/r_CREATE_EXTERNAL_TABLE.html",
    "https://docs.aws.amazon.com/redshift/latest/dg/c-using-spectrum.html",

    # --- Amazon S3 ---
    "https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html",
    "https://docs.aws.amazon.com/AmazonS3/latest/userguide/intelligent-tiering.html",
    "https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lifecycle-mgmt.html",

    # --- AWS Glue ---
    "https://docs.aws.amazon.com/glue/latest/dg/what-is-glue.html",
    "https://docs.aws.amazon.com/glue/latest/dg/aws-glue-api-catalog.html",
    "https://docs.aws.amazon.com/glue/latest/dg/dev-endpoint.html",
    "https://docs.aws.amazon.com/glue/latest/dg/aws-glue-programming-etl-glue-data-catalog.html",

    # --- Amazon Athena ---
    "https://docs.aws.amazon.com/athena/latest/ug/what-is.html",
    "https://docs.aws.amazon.com/athena/latest/ug/performance-tuning.html",
    "https://docs.aws.amazon.com/athena/latest/ug/querying-iceberg.html",

    # --- AWS Lake Formation ---
    "https://docs.aws.amazon.com/lake-formation/latest/dg/what-is-lake-formation.html",
    "https://docs.aws.amazon.com/lake-formation/latest/dg/access-control-overview.html",
    "https://docs.aws.amazon.com/lake-formation/latest/dg/lf-governed-tables.html",

    # --- Amazon Kinesis ---
    "https://docs.aws.amazon.com/streams/latest/dev/introduction.html",
    "https://docs.aws.amazon.com/firehose/latest/dev/what-is-this-service.html",

    # --- Amazon MSK ---
    "https://docs.aws.amazon.com/msk/latest/developerguide/what-is-msk.html",
    "https://docs.aws.amazon.com/msk/latest/developerguide/msk-connect.html",

    # --- Amazon Bedrock ---
    "https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html",
    "https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html",
    "https://docs.aws.amazon.com/bedrock/latest/userguide/agents.html",
    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-ids.html",

    # --- Amazon SageMaker ---
    "https://docs.aws.amazon.com/sagemaker/latest/dg/whatis.html",
    "https://docs.aws.amazon.com/sagemaker/latest/dg/studio-updated.html",

    # --- AWS Lambda / Serverless ---
    "https://docs.aws.amazon.com/lambda/latest/dg/welcome.html",
    "https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html",
    "https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/what-is-sam.html",

    # --- Amazon EKS / ECS / Fargate ---
    "https://docs.aws.amazon.com/eks/latest/userguide/what-is-eks.html",
    "https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html",

    # --- Amazon DynamoDB ---
    "https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Introduction.html",
    "https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/best-practices.html",

    # --- Amazon RDS / Aurora ---
    "https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Welcome.html",
    "https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/CHAP_AuroraOverview.html",
    "https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy.html",

    # --- Well-Architected ---
    "https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html",
    "https://docs.aws.amazon.com/wellarchitected/latest/cost-optimization-pillar/welcome.html",
    "https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/welcome.html",
    "https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/welcome.html",

    # --- Cost Optimization ---
    "https://docs.aws.amazon.com/savingsplans/latest/userguide/what-is-savings-plans.html",
    "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instance-purchasing-options.html",
    "https://docs.aws.amazon.com/cost-management/latest/userguide/ce-what-is.html",

    # --- IAM & Security ---
    "https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html",
    "https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies.html",

    # --- Networking ---
    "https://docs.aws.amazon.com/vpc/latest/userguide/what-is-amazon-vpc.html",
    "https://docs.aws.amazon.com/directconnect/latest/UserGuide/Welcome.html",
    "https://docs.aws.amazon.com/vpc/latest/tgw/what-is-transit-gateway.html",

    # --- Observability ---
    "https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/WhatIsCloudWatch.html",
    "https://docs.aws.amazon.com/xray/latest/devguide/aws-xray.html",

    # --- Organizations / Control Tower ---
    "https://docs.aws.amazon.com/organizations/latest/userguide/orgs_introduction.html",
    "https://docs.aws.amazon.com/controltower/latest/userguide/what-is-control-tower.html",

    # --- EventBridge / Step Functions ---
    "https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-what-is.html",
    "https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html",

    # --- Data architecture blogs (re:Post / prescriptive guidance) ---
    "https://docs.aws.amazon.com/prescriptive-guidance/latest/serverless-etl-aws-glue/welcome.html",
    "https://docs.aws.amazon.com/prescriptive-guidance/latest/modern-data-centric-use-cases/introduction.html",
    "https://docs.aws.amazon.com/prescriptive-guidance/latest/aws-glue-best-practices-build-efficient-data-pipeline/welcome.html",
]


def _try_live_search(query: str, top_k: int = 2) -> list[str]:
    """Try to discover additional URLs via AWS docs search. Returns [] on any failure."""
    urls: list[str] = []
    try:
        encoded = quote_plus(query)
        search_url = (
            f"https://docs.aws.amazon.com/search/doc-search.html"
            f"?searchPath=documentation&searchQuery={encoded}&this_doc_guide=*"
        )
        req = urllib.request.Request(
            search_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            body = resp.read().decode("utf-8", errors="replace")

        pattern = re.compile(
            r'href="(https://docs\.aws\.amazon\.com/[^"#?]+\.html)"',
        )
        seen: set[str] = set()
        for m in pattern.finditer(body):
            u = html.unescape(m.group(1))
            if u not in seen and "search" not in u:
                seen.add(u)
                urls.append(u)
            if len(urls) >= top_k:
                break
    except Exception as e:
        logger.debug(f"Live search failed for {query!r}: {e}")
    return urls


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect AWS docs URLs for KB seeding")
    parser.add_argument("--output", default="data/urls.txt", help="Output URL list path")
    parser.add_argument(
        "--live", action="store_true",
        help="Attempt live AWS docs search to augment the curated list",
    )
    parser.add_argument("--seeds", default="data/kb_seeds.txt",
                        help="Seeds file (used only with --live)")
    parser.add_argument("--delay", type=float, default=0.3,
                        help="Delay between live search requests (s)")
    args = parser.parse_args()

    all_urls: list[str] = list(CURATED_URLS)
    seen: set[str] = set(all_urls)

    logger.info(f"Starting with {len(all_urls)} curated URLs.")

    if args.live:
        seeds_path = Path(args.seeds)
        if not seeds_path.exists():
            logger.warning(f"Seeds file not found: {seeds_path} — skipping live search")
        else:
            topics = [
                line.strip()
                for line in seeds_path.read_text().splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            logger.info(f"Live search: {len(topics)} topics from {seeds_path}")
            found = 0
            for i, topic in enumerate(topics, 1):
                new_urls = _try_live_search(topic, top_k=2)
                for u in new_urls:
                    if u not in seen:
                        seen.add(u)
                        all_urls.append(u)
                        found += 1
                if i % 5 == 0:
                    logger.info(f"  Progress: {i}/{len(topics)} topics, {found} new URLs found")
                if i < len(topics):
                    time.sleep(args.delay)
            logger.info(f"Live search added {found} additional URLs.")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(all_urls) + "\n")
    logger.info(f"Wrote {len(all_urls)} URLs to {output_path}")
    logger.info(f"Next step: uv run python scripts/ingest.py --urls {output_path}")


if __name__ == "__main__":
    main()
