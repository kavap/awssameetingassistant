import { useState } from "react";
import { MEETING_TYPES, type MeetingType } from "../types";

interface Props {
  onConfirm: (customerId: string, meetingType: MeetingType) => void;
  onCancel: () => void;
}

export function StartMeetingModal({ onConfirm, onCancel }: Props) {
  const [customerId, setCustomerId] = useState("");
  const [meetingType, setMeetingType] = useState<MeetingType>("Customer Meeting");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onConfirm(customerId.trim() || "anonymous", meetingType);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-slate-800 border border-slate-600 rounded-xl shadow-2xl w-full max-w-md mx-4 p-6">
        <h2 className="text-base font-semibold text-slate-100 mb-4">Start Meeting</h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Meeting Type */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">
              Meeting Type
            </label>
            <select
              value={meetingType}
              onChange={(e) => setMeetingType(e.target.value as MeetingType)}
              className="w-full bg-slate-700 border border-slate-600 text-slate-100 text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {MEETING_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-slate-500">
              Tailors the analysis focus and recommendations for your context.
            </p>
          </div>

          {/* Customer ID */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">
              Customer ID <span className="text-slate-500 font-normal">(optional)</span>
            </label>
            <input
              type="text"
              value={customerId}
              onChange={(e) => setCustomerId(e.target.value)}
              placeholder="e.g. acme-corp"
              className="w-full bg-slate-700 border border-slate-600 text-slate-100 text-sm rounded-lg px-3 py-2 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <p className="mt-1 text-xs text-slate-500">
              Used to load prior meeting context from memory.
            </p>
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-1">
            <button
              type="button"
              onClick={onCancel}
              className="flex-1 px-4 py-2 text-sm text-slate-400 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-500 text-white text-sm font-medium rounded-lg transition-colors"
            >
              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="10" />
              </svg>
              Start Recording
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
