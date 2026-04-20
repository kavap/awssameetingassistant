import { useState, useEffect } from "react";
import { MEETING_TYPES, type MeetingType } from "../types";
import { useMeetingStore } from "../store/meetingStore";

const BACKEND = "http://localhost:8000";

interface Props {
  onConfirm: (
    customerId: string,
    meetingType: MeetingType,
    meetingName: string,
    participants: string[],
    selectedRoles: string[],
  ) => void;
  onCancel: () => void;
}

export function StartMeetingModal({ onConfirm, onCancel }: Props) {
  const connectionStatus = useMeetingStore((s) => s.connectionStatus);
  const [customerId, setCustomerId] = useState("");
  const [meetingType, setMeetingType] = useState<MeetingType>("Customer Meeting");
  const [meetingName, setMeetingName] = useState("");
  const [participantsText, setParticipantsText] = useState("");
  const [availableRoles, setAvailableRoles] = useState<string[]>([]);
  const [selectedRoles, setSelectedRoles] = useState<Set<string>>(new Set());
  const [customRole, setCustomRole] = useState("");

  // Fetch default roles from backend
  useEffect(() => {
    fetch(`${BACKEND}/meeting/config`)
      .then((r) => r.json())
      .then((data: { default_roles: string[] }) => {
        setAvailableRoles(data.default_roles ?? []);
      })
      .catch(() => {
        // Fallback if backend not ready
        setAvailableRoles([
          "AWS Account SA", "AWS Analytics Specialist SA", "AWS ML Specialist SA",
          "Customer CDO/CTO", "Customer VP Engineering", "Customer Technical Lead",
          "Partner Architect", "Partner Delivery Lead",
        ]);
      });
  }, []);

  function toggleRole(role: string) {
    setSelectedRoles((prev) => {
      const next = new Set(prev);
      if (next.has(role)) next.delete(role);
      else next.add(role);
      return next;
    });
  }

  function addCustomRole() {
    const r = customRole.trim();
    if (!r) return;
    setAvailableRoles((prev) => [...prev, r]);
    setSelectedRoles((prev) => new Set([...prev, r]));
    setCustomRole("");
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const participants = participantsText
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    onConfirm(
      customerId.trim() || "anonymous",
      meetingType,
      meetingName.trim(),
      participants,
      [...selectedRoles],
    );
  }

  // Group roles by category
  const awsRoles = availableRoles.filter((r) => r.startsWith("AWS"));
  const customerRoles = availableRoles.filter((r) => r.startsWith("Customer"));
  const partnerRoles = availableRoles.filter((r) => r.startsWith("Partner"));
  const otherRoles = availableRoles.filter(
    (r) => !r.startsWith("AWS") && !r.startsWith("Customer") && !r.startsWith("Partner"),
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-slate-800 border border-slate-600 rounded-xl shadow-2xl w-full max-w-2xl mx-4 max-h-[90vh] overflow-y-auto">
        <div className="px-6 pt-6 pb-4 border-b border-slate-700">
          <h2 className="text-base font-semibold text-slate-100">Start Meeting</h2>
          {connectionStatus !== "connected" && (
            <div className="mt-3 px-3 py-2 bg-yellow-900/40 border border-yellow-700 rounded-lg text-xs text-yellow-300">
              Backend {connectionStatus === "connecting" ? "connecting…" : "disconnected"} — make sure the backend is running on port 8000.
            </div>
          )}
        </div>

        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-5">
          {/* Row 1: Meeting Name + Type */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">
                Meeting Name <span className="text-slate-500 font-normal">(optional)</span>
              </label>
              <input
                type="text"
                value={meetingName}
                onChange={(e) => setMeetingName(e.target.value)}
                placeholder="e.g. Data Platform Discovery"
                className="w-full bg-slate-700 border border-slate-600 text-slate-100 text-sm rounded-lg px-3 py-2 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
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
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
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

          {/* Participants */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">
              Participants <span className="text-slate-500 font-normal">(one per line, optional)</span>
            </label>
            <textarea
              value={participantsText}
              onChange={(e) => setParticipantsText(e.target.value)}
              placeholder={"John Smith (AWS SA)\nJane Doe (Acme CTO)\nAlex Lee (Partner Architect)"}
              rows={4}
              className="w-full bg-slate-700 border border-slate-600 text-slate-100 text-sm rounded-lg px-3 py-2 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none font-mono"
            />
            <p className="mt-1 text-xs text-slate-500">
              Paste names or emails. Used to map speaker IDs to people during the meeting.
            </p>
          </div>

          {/* Roles checklist */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-2">
              Roles Present <span className="text-slate-500 font-normal">(select all that apply)</span>
            </label>

            {availableRoles.length > 0 && (
              <div className="bg-slate-900/50 border border-slate-700 rounded-lg p-3 space-y-3 max-h-48 overflow-y-auto">
                {awsRoles.length > 0 && (
                  <RoleGroup label="AWS" roles={awsRoles} selected={selectedRoles} onToggle={toggleRole} color="text-blue-400" />
                )}
                {customerRoles.length > 0 && (
                  <RoleGroup label="Customer" roles={customerRoles} selected={selectedRoles} onToggle={toggleRole} color="text-emerald-400" />
                )}
                {partnerRoles.length > 0 && (
                  <RoleGroup label="Partner" roles={partnerRoles} selected={selectedRoles} onToggle={toggleRole} color="text-violet-400" />
                )}
                {otherRoles.length > 0 && (
                  <RoleGroup label="Other" roles={otherRoles} selected={selectedRoles} onToggle={toggleRole} color="text-slate-400" />
                )}
              </div>
            )}

            {/* Custom role input */}
            <div className="flex gap-2 mt-2">
              <input
                type="text"
                value={customRole}
                onChange={(e) => setCustomRole(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addCustomRole(); } }}
                placeholder="Add custom role..."
                className="flex-1 bg-slate-700 border border-slate-600 text-slate-100 text-xs rounded px-2.5 py-1.5 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
              <button
                type="button"
                onClick={addCustomRole}
                className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 text-xs rounded border border-slate-600"
              >
                Add
              </button>
            </div>

            {selectedRoles.size > 0 && (
              <p className="mt-1.5 text-xs text-slate-500">
                {selectedRoles.size} role{selectedRoles.size !== 1 ? "s" : ""} selected
              </p>
            )}
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-1 border-t border-slate-700">
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

function RoleGroup({
  label,
  roles,
  selected,
  onToggle,
  color,
}: {
  label: string;
  roles: string[];
  selected: Set<string>;
  onToggle: (r: string) => void;
  color: string;
}) {
  return (
    <div>
      <p className={`text-xs font-semibold mb-1.5 ${color}`}>{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {roles.map((r) => (
          <button
            key={r}
            type="button"
            onClick={() => onToggle(r)}
            className={`text-xs px-2 py-0.5 rounded-full border transition-colors ${
              selected.has(r)
                ? "bg-blue-600/30 border-blue-500 text-blue-300"
                : "bg-slate-800 border-slate-600 text-slate-400 hover:border-slate-500"
            }`}
          >
            {r.replace(/^AWS |^Customer |^Partner /, "")}
          </button>
        ))}
      </div>
    </div>
  );
}
