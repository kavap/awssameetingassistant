import { useState, useRef, useEffect } from "react";
import type { TranscriptChunk } from "../types";
import { useMeetingStore } from "../store/meetingStore";

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
    const parts = displayName.split(/\s+/);
    return parts.length > 1 ? `${parts[0]} ${parts[1][0]}.` : parts[0];
  }
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
  allSpeakerIds?: string[];
}

export function TranscriptChunkItem({ chunk, displayName, allSpeakerIds = [] }: Props) {
  const correctChunkSpeaker = useMeetingStore((s) => s.correctChunkSpeaker);
  const speakerMappings = useMeetingStore((s) => s.speakerMappings);
  const meetingStatus = useMeetingStore((s) => s.meetingStatus);

  const [showPicker, setShowPicker] = useState(false);
  const pickerRef = useRef<HTMLDivElement>(null);

  // Close picker on outside click
  useEffect(() => {
    if (!showPicker) return;
    function handleClick(e: MouseEvent) {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        setShowPicker(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [showPicker]);

  const canCorrect = meetingStatus === "recording" && allSpeakerIds.length > 1;

  function pickSpeaker(newId: string) {
    correctChunkSpeaker(chunk.id, newId);
    setShowPicker(false);
  }

  function speakerOptionLabel(id: string): string {
    const info = speakerMappings[id];
    if (info?.name) return info.name;
    const m = id.match(/(\d+)$/);
    return `Speaker ${m ? parseInt(m[1]) + 1 : id}`;
  }

  return (
    <div className="flex gap-2 py-1 px-2 hover:bg-slate-800/40 rounded text-sm leading-relaxed group">
      <span className="text-slate-500 tabular-nums text-xs pt-0.5 shrink-0 w-[4.5rem]">
        {formatTime(chunk.timestamp)}
      </span>

      {/* Clickable speaker label */}
      <div className="relative shrink-0 w-14" ref={pickerRef}>
        <button
          onClick={() => canCorrect && setShowPicker((v) => !v)}
          disabled={!canCorrect}
          title={canCorrect ? "Click to re-assign speaker" : (displayName ?? chunk.speaker ?? undefined)}
          className={`text-xs pt-0.5 font-medium truncate w-full text-left ${speakerColor(chunk.speaker)} ${
            canCorrect ? "cursor-pointer hover:underline decoration-dotted" : "cursor-default"
          }`}
        >
          {formatSpeaker(chunk.speaker, displayName)}
        </button>

        {showPicker && (
          <div className="absolute left-0 top-full mt-1 z-20 bg-slate-800 border border-slate-600 rounded-lg shadow-xl py-1 min-w-[140px]">
            <p className="text-xs text-slate-500 px-2.5 py-1 border-b border-slate-700">Re-assign to…</p>
            {allSpeakerIds.map((id) => (
              <button
                key={id}
                onClick={() => pickSpeaker(id)}
                className={`w-full text-left text-xs px-2.5 py-1.5 hover:bg-slate-700 transition-colors flex items-center gap-2 ${
                  id === chunk.speaker ? "text-blue-400 font-medium" : "text-slate-300"
                }`}
              >
                <span className={`w-2 h-2 rounded-full shrink-0 ${speakerColor(id).replace("text-", "bg-")}`} />
                {speakerOptionLabel(id)}
                {id === chunk.speaker && <span className="ml-auto text-slate-500">✓</span>}
              </button>
            ))}
          </div>
        )}
      </div>

      <span className="text-slate-200 min-w-0">{highlightText(chunk.text)}</span>
    </div>
  );
}
