import type { TranscriptChunk } from "../types";

// AWS service names to highlight in blue
const AWS_TERMS = [
  "EC2","Lambda","ECS","EKS","Fargate","S3","EBS","EFS","RDS","Aurora",
  "DynamoDB","ElastiCache","Redshift","Athena","Glue","EMR","Kinesis","MSK",
  "Bedrock","SageMaker","OpenSearch","QuickSight","CloudFront","Route 53",
  "API Gateway","VPC","CloudFormation","CDK","CloudWatch","IAM","DMS",
  "Lake Formation","Transcribe","DataZone","Kendra","Step Functions","SNS","SQS",
];

// Competitor names to highlight in amber
const COMPETITOR_TERMS = [
  "Snowflake","Databricks","Confluent","Elasticsearch","ClickHouse",
  "BigQuery","Azure","Google Cloud","dbt","Terraform","Fivetran",
];

function highlightText(text: string): React.ReactNode[] {
  const allTerms = [
    ...AWS_TERMS.map((t) => ({ term: t, cls: "text-blue-400 font-medium" })),
    ...COMPETITOR_TERMS.map((t) => ({ term: t, cls: "text-amber-400 font-medium" })),
  ].sort((a, b) => b.term.length - a.term.length);

  // Build combined regex
  const pattern = new RegExp(
    `(${allTerms.map((t) => t.term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`,
    "gi"
  );

  const parts = text.split(pattern);
  return parts.map((part, i) => {
    const match = allTerms.find(
      (t) => t.term.toLowerCase() === part.toLowerCase()
    );
    if (match) {
      return (
        <span key={i} className={match.cls}>
          {part}
        </span>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function speakerColor(speaker: string | null): string {
  if (!speaker) return "text-slate-400";
  const colors = [
    "text-emerald-400",
    "text-violet-400",
    "text-cyan-400",
    "text-pink-400",
    "text-orange-400",
  ];
  const idx = parseInt(speaker.replace(/\D/g, "") || "0") % colors.length;
  return colors[idx];
}

interface Props {
  chunk: TranscriptChunk;
}

export function TranscriptChunkItem({ chunk }: Props) {
  return (
    <div className="flex gap-3 py-1 px-2 hover:bg-slate-800/40 rounded text-sm leading-relaxed">
      <span className="text-slate-500 tabular-nums text-xs pt-0.5 shrink-0 w-20">
        {formatTime(chunk.timestamp)}
      </span>
      {chunk.speaker && (
        <span className={`text-xs pt-0.5 shrink-0 w-14 ${speakerColor(chunk.speaker)}`}>
          {chunk.speaker}
        </span>
      )}
      <span className="text-slate-200">{highlightText(chunk.text)}</span>
    </div>
  );
}
