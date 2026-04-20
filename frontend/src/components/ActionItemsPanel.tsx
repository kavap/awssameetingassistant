import { useMeetingStore } from "../store/meetingStore";

interface ActionGroup {
  label: string;
  key: "aws" | "partner" | "customer";
  color: string;
  dotColor: string;
  borderColor: string;
  bgColor: string;
}

const GROUPS: ActionGroup[] = [
  {
    label: "AWS",
    key: "aws",
    color: "text-orange-300",
    dotColor: "bg-orange-500",
    borderColor: "border-orange-700",
    bgColor: "bg-orange-900/20",
  },
  {
    label: "Customer",
    key: "customer",
    color: "text-emerald-300",
    dotColor: "bg-emerald-500",
    borderColor: "border-emerald-700",
    bgColor: "bg-emerald-900/20",
  },
  {
    label: "Partner",
    key: "partner",
    color: "text-violet-300",
    dotColor: "bg-violet-500",
    borderColor: "border-violet-700",
    bgColor: "bg-violet-900/20",
  },
];

export function ActionItemsPanel() {
  const trackA = useMeetingStore((s) => s.analysisTrackA);
  const trackB = useMeetingStore((s) => s.analysisTrackB);

  // Merge action items from both tracks, deduplicating by text
  const merged: Record<string, Set<string>> = { aws: new Set(), customer: new Set(), partner: new Set() };
  for (const result of [trackA, trackB]) {
    if (!result?.action_items) continue;
    for (const key of ["aws", "customer", "partner"] as const) {
      for (const item of result.action_items[key] ?? []) {
        merged[key].add(item);
      }
    }
  }

  const hasAny = Object.values(merged).some((s) => s.size > 0);

  if (!hasAny) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-4 text-slate-500 text-sm gap-2">
        <svg className="w-8 h-8 text-slate-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
        </svg>
        <p>Action items appear once the analysis reaches Stage 2.</p>
      </div>
    );
  }

  return (
    <div className="overflow-y-auto h-full px-3 py-3 space-y-3">
      {GROUPS.map(({ label, key, color, dotColor, borderColor, bgColor }) => {
        const items = Array.from(merged[key]);
        if (items.length === 0) return null;
        return (
          <div key={key} className={`rounded-lg border ${borderColor} ${bgColor} p-3`}>
            <div className="flex items-center gap-2 mb-2.5">
              <span className={`w-2 h-2 rounded-full shrink-0 ${dotColor}`} />
              <span className={`text-xs font-semibold uppercase tracking-wider ${color}`}>
                {label}
              </span>
              <span className="ml-auto text-xs text-slate-500">{items.length} item{items.length !== 1 ? "s" : ""}</span>
            </div>
            <ul className="space-y-1.5">
              {items.map((item, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-slate-200">
                  <svg className={`w-3.5 h-3.5 mt-0.5 shrink-0 ${color}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
