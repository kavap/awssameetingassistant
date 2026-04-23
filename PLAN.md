# AWS SA Meeting Intelligence Assistant — Project Plan

## Current State: WORKINGV2 (Phase 1 complete)

Full working stack as of tag `WORKINGV2`:
- **CCM engine** — per-segment entity extraction (AWS services, topics, open questions)
- **Two-phase analysis** — Haiku readiness gate + query gen → Bedrock KB accumulation → Sonnet staged analysis
- **Stage gating** — Stage 1 (<3 segs): context only | Stage 2 (3–7): tentative arch | Stage 3 (8+): full arch + diagrams
- **Track A / Track B** — autonomous analysis always running; steered track fires when SA injects a directive
- **Three mermaid diagrams** — Current State, Future State Auto, Future State Steered (serialised render queue to fix mermaid concurrency)
- **8 meeting types** — Customer Meeting, OneTeam, SA Manager Sync, Internal Arch Review, Competitive Deal, Migration Assessment, GenAI/ML Workshop, Cost Optimization Review
- **Bedrock Knowledge Base** — AOSS-backed, Cohere Embed English v3, hybrid search
- **AWS Docs Search** — supplementary docs search alongside KB
- **AgentCore Runtime** — fast-path recommendation cards (optional, falls back to local RecommendationAgent)
- **AgentCore Memory** — cross-session customer context (optional)
- **FastAPI + WebSocket** — real-time streaming to React frontend
- **Amazon Transcribe Streaming** — cloud STT (or faster-whisper local fallback)
- **React + TypeScript frontend** — Live Analysis panel (Auto/Steered tabs), Diagrams panel, Directives bar, CCM state sidebar

---

## Roadmap

### Phase 2 — Multi-Agent Parallel Search  ← NEXT
**Goal:** Better KB retrieval quality through specialisation instead of generic queries.

- **6 parallel specialist agents** (each fires its own Bedrock KB query set per cycle):
  - `architecture` — AWS service selection, reference architectures
  - `migration` — 7Rs, MGN, DMS, SCT, DataSync, MAP
  - `comparison` — competitor positioning (Azure, GCP, on-prem vs AWS)
  - `code_samples` — CDK/CloudFormation/CLI snippets
  - `cost` — pricing, Savings Plans, rightsizing
  - `security` — Well-Architected security pillar, IAM, compliance
- **Revision Agent** — detects when new KB chunks arrive mid-cycle and triggers a lightweight re-analysis of only the changed sections (avoids full Sonnet re-run)
- Frontend: show which specialist agent sourced each recommendation card

### Phase 3 — Audio & Speaker Improvements
**Goal:** Know who said what; capture remote participants on Mac.

- **Speaker diarization UI** — label transcript lines as SA / Customer / Unknown
- **System audio capture** — BlackHole (Mac) / VB-Cable (Windows) auto-config so Zoom/Teams/Meet audio is captured without a hardware loopback
- **Whisper Apple Silicon** — `WHISPER_DEVICE=mps` tuning guide baked into setup

### Phase 4 — Electron Desktop Overlay
**Goal:** A native Mac/Windows app that floats over Zoom/Teams.

- Wrap React frontend in Electron shell
- Always-on-top overlay window (transparent background option)
- System tray icon with quick start/stop/mute
- Session export: PDF and Markdown (transcript + full analysis + all 3 diagrams)
- Auto-update via GitHub Releases

### Phase 5 — Configurable Knowledge Base Expansion
**Goal:** Keep the KB fresh without manual effort.

- `sources.yaml` — declarative list of sources (S3 prefixes, GitHub repos, YouTube channels, RSS/blog feeds)
- Scheduled ingestion Lambda / cron job — syncs new content → S3 → Bedrock KB ingest
- GitHub repo indexer — indexes README, docs/, architecture docs
- YouTube transcript indexer — AWS re:Invent talks, AWS On Air episodes
- Version-tagged KB snapshots so you can roll back

### Phase 6 — Slack-Integrated AWS Team Assistant
**Goal:** Extend the assistant into an AWS-internal Slack workspace so the full account team can interrogate meeting intelligence asynchronously — without exposing anything to the customer.

**Core concept:**
- Per-meeting Slack channel auto-created on meeting start (e.g. `#mtg-acme-2026-04-23`)
- AWS participants added automatically (SA, manager, specialist SAs, PSA/CSM)
- Slack bot answers questions grounded in the saved meeting record + Bedrock KB
- Full context available: transcript, Track A/B analysis, speaker mapping, directives, action items

**Key use cases:**
- SA Manager: "Summarize the deal risk and blockers" — without reading the full transcript
- Specialist SA joining a follow-up: "What did the customer say about their Redshift usage?"
- PSA/CSM: "List all open action items for the AWS team"
- SA peer review: "What architecture did we propose and why?"

**Design decisions:**
- AWS-only channel → no trust boundary problem, no context filtering needed, full analysis visible
- Slack identity → meeting role mapping (SA who ran the meeting vs. specialist vs. manager) — used for response calibration, not access control
- Two query modes: (1) RAG over saved `meetings/{session_id}.json` + KB for post-meeting, (2) live query against active session context during meeting
- Response always grounded — cites transcript segments or KB sources, no hallucination
- Phase 2 shared `SessionContext` improves live-meeting query quality but is not required to ship Phase 6

**Dependencies:**
- Saved meeting JSON (already implemented)
- Bedrock KB (already implemented)
- Slack API (bot token, channel management, event subscriptions)
- Phase 2 shared context recommended for live-meeting query path (not blocking for post-meeting path)

---

## Key Technical Decisions (do not revisit without reason)

| Decision | Rationale |
|---|---|
| Cadence-based analysis (every N final segs) | Prevents flooding Bedrock on every word; lets KB accumulate |
| Accumulated KB across cycles (top-25 by score) | Better context than per-cycle fresh search |
| Previous analysis fed back into next cycle | Continuity; Sonnet refines rather than restarts |
| max_tokens=15000 for Sonnet | Full analysis + 3 diagrams fits; truncation was breaking diagrams |
| Mermaid render queue (serialised) | Concurrent mermaid.render() corrupts shared state — debug HTML confirmed |
| Track B skips Current State Diagram | Avoids doubling token cost; auto track already produces it |
| StrictMode cancelled flag + renderedRef reset | Prevents double-invoke race where first mount sets renderedRef before cleanup |

---

## Debug Endpoints (always available in dev)

```
GET  /debug/list                    — list all raw Sonnet response files in /tmp
GET  /debug/raw/{cycle}/{track}     — view raw Sonnet output for cycle N, track A or B
```

Debug files: `/tmp/meeting_debug_cycle{N}_track{A|B}.txt`
Debug page: `debug_mermaid.html` in repo root (open in browser, no server needed)
