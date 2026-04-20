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

  const pattern = new RegExp(
    `(${allTerms.map((t) => t.term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`,
    "gi"
  );

  const parts = text.split(pattern);
  return parts.map((part, i) => {
    const match = allTerms.find((t) => t.term.toLowerCase() === part.toLowerCase());
    if (match) return <span key={i} className={match.cls}>{part}</span>;
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

/** Map raw Transcribe speaker IDs ("spk_0", "spk_1") to readable labels. */
function formatSpeaker(speaker: string | null, displayName?: string): string {
  if (!speaker) return "—";
  if (displayName) {
    // Abbreviate to first name or initials if too long
    const parts = displayName.split(/\s+/);
    return parts.length > 1 ? `${parts[0]} ${parts[1][0]}.` : parts[0];
  }
  // Transcribe format: "spk_0", "spk_1", etc.
  const m = speaker.match(/(\d+)$/);
  if (m) return `Spk ${parseInt(m[1]) + 1}`;
  return speaker;
}

const SPEAKER_COLORS = [
  "text-emerald-400",
  "text-violet-400",
  "text-cyan-400",
  "text-pink-400",
  "text-orange-400",
];

function speakerColor(speaker: string | null): string {
  if (!speaker) return "text-slate-600";
  const m = speaker.match(/(\d+)$/);
  const idx = m ? parseInt(m[1]) % SPEAKER_COLORS.length : 0;
  return SPEAKER_COLORS[idx];
}

interface Props {
  chunk: TranscriptChunk;
  displayName?: string;
}

export function TranscriptChunkItem({ chunk, displayName }: Props) {
  return (
    <div className="flex gap-2 py-1 px-2 hover:bg-slate-800/40 rounded text-sm leading-relaxed">
      <span className="text-slate-500 tabular-nums text-xs pt-0.5 shrink-0 w-[4.5rem]">
        {formatTime(chunk.timestamp)}
      </span>
      <span
        className={`text-xs pt-0.5 shrink-0 w-14 font-medium truncate ${speakerColor(chunk.speaker)}`}
        title={displayName ?? chunk.speaker ?? undefined}
      >
        {formatSpeaker(chunk.speaker, displayName)}
      </span>
      <span className="text-slate-200 min-w-0">{highlightText(chunk.text)}</span>
    </div>
  );
}
