# System Design — AWS SA Meeting Intelligence Assistant

This document explains how the application works internally: the full control flow, every prompt in the system, the distinction between deterministic and probabilistic stages, and the meaning of key concepts (segment, cycle, phase, stage, trigger).

---

## Table of Contents

1. [Key Concepts](#key-concepts)
2. [Full Control Flow](#full-control-flow)
3. [Deterministic vs Probabilistic Stages](#deterministic-vs-probabilistic-stages)
4. [Every Prompt in the System](#every-prompt-in-the-system)
5. [Audio Pipeline Fundamentals](#audio-pipeline-fundamentals)
6. [State and Storage](#state-and-storage)

---

## Key Concepts

### Segment

One chunk of transcribed speech that the STT (Speech-To-Text) provider has committed to as final. Not a partial guess — a locked result.

**How STT works:** The STT engine does not wait for you to finish speaking before emitting anything. It streams guesses in real time as audio arrives, updating them continuously. These are called *partials*. When the engine detects a natural pause (silence lasting ~0.3–1.0 seconds, or the speaker taking a breath), it commits to a final result and emits it as a *final segment*. Partials are discarded by this app — only final segments feed the pipeline.

**Typical length in a meeting:** 1–3 sentences, roughly 5–25 words, ~1–5 seconds of audio. If a speaker talks continuously without pausing, Transcribe will force-finalize after ~10–15 seconds regardless.

**In the code:** `_segment_count` in `AnalysisEngine` tracks how many final segments have been received this session. Each segment also carries a `speaker` ID (e.g. `spk_0`, `spk_1`) from the diarization layer.

---

### Cycle

One full run of the three-phase analysis pipeline. Triggered automatically every **3 final segments** (`ANALYZE_EVERY = 3` in `engine.py`). Also triggered immediately (out of cadence) when:

- The SA applies a speaker mapping → immediate full re-analysis
- The SA adds a directive → immediate Track-B-only re-analysis

Each cycle increments `_cycle_count`. A new cycle will not start if the previous one is still running (`_analyzing` guard flag).

**In a typical meeting:** With normal conversational speech (~1 segment per 5 seconds), a cycle fires roughly every 15 seconds.

---

### Phase

The sub-steps within a single cycle. Always exactly 3, always in order:

| Phase | Model | What it does |
|---|---|---|
| Phase 1 | Haiku | Readiness gate + KB search query generation |
| Phase 2 | — | KB retrieval (Bedrock KB + AWS Docs Search), results accumulated |
| Phase 3 | Sonnet | Staged analysis — produces Track A and optionally Track B |

Phase 2 is deterministic (no LLM). The KB results accumulate across cycles — chunks from earlier cycles are kept and re-ranked alongside new ones.

---

### Stage

A level of analysis depth, determined by how many final segments have been received. Purely deterministic — no LLM involved in this decision. Computed once per cycle by `_determine_stage()`.

| Stage | Condition | What Sonnet outputs |
|---|---|---|
| 1 | `ready=false` OR `< 3 segments` | Situation, Current State, Customer Needs, Open Questions only |
| 2 | `3–7 segments` | Adds tentative Proposed Architecture (with `[ASSUMPTION:]` labels) + 2-3 Recommendations + Action Items |
| 3 | `≥ 8 segments` | Full output including 3-5 prioritized Recommendations + Mermaid diagrams (Current State + Future State) |

Stage is injected into the Sonnet prompt as `{stage_label}` and controls which sections Sonnet is instructed to produce or omit.

---

### Trigger

An event that causes something to happen outside the normal segment-counting cadence. Three types:

1. **CCM trigger** — Haiku flags `should_recommend=true` on a segment, or detects a new service/topic/question → emits a `CCMUpdateEvent` → recommendation card is generated
2. **Directive trigger** — SA types a directive in the UI → `POST /meeting/directive` → immediate out-of-cadence analysis cycle for Track B only
3. **Speaker mapping trigger** — SA applies speaker mapping in the Speakers tab → `POST /meeting/speaker-mapping` → immediate full re-analysis cycle (both tracks) with transcript lines now annotated `[Name | Org | Role]:`

---

### STT — Speech-To-Text

The transcription layer. Two providers are supported, selected by `STT_PROVIDER` in `.env`:

| Provider | File | Mode | Best for |
|---|---|---|---|
| Amazon Transcribe Streaming | `transcribe_stream.py` | Cloud, streaming | Best accuracy, built-in diarization (speaker labels) |
| faster-whisper | `whisper_stream.py` | Local, offline | Privacy-first, Apple Silicon GPU, no AWS dependency |

---

### CCM — Conversation Context Map

The running structured state of the meeting. Updated incrementally by a Haiku call on every final segment. Never resets mid-session; only accumulates.

Contains:
- `mentioned_services` — AWS services and competitor tools detected, with mention count
- `active_topics` — up to 5 active topics, ranked by confidence (e.g. `data_warehouse`, `migration`, `cost_optimization`)
- `open_questions` — questions raised but not yet answered (deduplicated by Jaccard similarity)
- `meeting_goal` — one-sentence summary, captured from early segments
- `full_transcript` — rolling list of all final segments

The CCM snapshot is passed into Phase 1 (query gen) to avoid re-searching topics already covered, and broadcast to the frontend via WebSocket as a `ccm_update` event for the live context panel.

---

## Full Control Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  AUDIO LAYER                                                                │
│                                                                             │
│  Microphone or WAV file (USE_FAKE_AUDIO=true)                              │
│    │  16,000 samples/sec, 100ms chunks = 1,600 samples per packet          │
│    ▼                                                                        │
│  STT Provider (Amazon Transcribe Streaming  OR  faster-whisper)            │
│    │  Emits: partial segments (ignored), final segments (forwarded)        │
└──────────────────────┬──────────────────────────────────────────────────────┘
                       │ final segment (text + speaker_id)
           ┌───────────┴────────────────────────────────┐
           ▼                                            ▼
┌─────────────────────────┐               ┌────────────────────────────────────┐
│  CCM ENGINE             │               │  ANALYSIS ENGINE                   │
│  (every final segment)  │               │  (every final segment)             │
│                         │               │                                    │
│  ★ Haiku call           │               │  _segment_count += 1               │
│    Prompt: CCM template │               │                                    │
│    Extracts:            │               │  if segment_count % 3 == 0:        │
│    - aws_services       │               │    fire _analyze_cycle()           │
│    - competitors        │               └──────────────┬─────────────────────┘
│    - questions          │                              │
│    - topics             │                              ▼
│    - meeting_goal       │               ┌────────────────────────────────────┐
│    - should_recommend   │               │  _analyze_cycle()                  │
│                         │               │                                    │
│  CCMState updated       │               │  ┌─── PHASE 1 ──────────────────┐  │
│  (deterministic merge)  │               │  │ ★ Haiku                      │  │
│                         │               │  │   Prompt: QUERY_GEN_PROMPT   │  │
│  CCMUpdateEvent emitted │               │  │   → ready: true/false        │  │
│  if new entity detected │               │  │   → new_queries: [...]       │  │
└──────────┬──────────────┘               │  └──────────────────────────────┘  │
           │                              │                                    │
           ▼                              │  ┌─── PHASE 2 (if ready) ───────┐  │
   handle_ccm_event()                    │  │  Bedrock KB.retrieve(query)  │  │
           │                              │  │  + docs_search(query)        │  │
           ├─ broadcast ccm_update → WS  │  │  Accumulate, dedup, sort     │  │
           │                              │  │  Keep top 25 by score        │  │
           ├─ if AgentCore configured:   │  └──────────────────────────────┘  │
           │    agentcore_client.invoke()│                                    │
           │    → broadcast recommendation│  ┌─── PHASE 3 ──────────────────┐  │
           │                              │  │  _determine_stage()          │  │
           └─ else → event_queue         │  │  (segment thresholds: 3 / 8) │  │
                │                        │  │                              │  │
                ▼                        │  │  ★ Sonnet — Track A          │  │
     RecommendationAgent                 │  │   System: MEETING_TYPE_PROMPTS│  │
       ★ Haiku rerank chunks             │  │   User:   ANALYSIS_PROMPT    │  │
       ★ Sonnet synthesis card           │  │   + participants_context     │  │
       → broadcast recommendation → WS  │  │   + customer_context         │  │
                                         │  │                              │  │
                                         │  │  if directives exist:        │  │
                                         │  │  ★ Sonnet — Track B          │  │
                                         │  │   Same + DIRECTIVE_EXTENSION │  │
                                         │  └──────────────────────────────┘  │
                                         │                                    │
                                         │  broadcast analysis_update → WS   │
                                         │  broadcast steered_analysis → WS  │
                                         └────────────────────────────────────┘
                                                          │
                                         ┌────────────────▼────────────────────┐
                                         │  WebSocket → React Frontend         │
                                         │                                     │
                                         │  Left panel (55%):                  │
                                         │    TranscriptPanel                  │
                                         │    - Final segments with speaker    │
                                         │    - Inline speaker re-attribution  │
                                         │    - Per-speaker filter             │
                                         │                                     │
                                         │  Right panel (45%):                 │
                                         │    AnalysisPanel tabs:              │
                                         │    - Auto (Track A)                 │
                                         │    - Steered (Track B)              │
                                         │    - Diagrams (Mermaid)             │
                                         │    - Speakers (talk-time + mapping) │
                                         └─────────────────────────────────────┘
```

---

## Deterministic vs Probabilistic Stages

| Step | Nature | Detail |
|---|---|---|
| Audio capture | Deterministic | Hardware bytes, no inference |
| STT transcription | Probabilistic (external) | Transcribe/Whisper model; not our prompts |
| CCM merge logic | **Deterministic** | Additive dict updates; Jaccard dedup for questions |
| **CCM Haiku extraction** | **Probabilistic** | `temperature=0.0` — near-deterministic but still an LLM judgment |
| Cycle trigger cadence | **Deterministic** | `segment_count % ANALYZE_EVERY == 0` |
| **Phase 1 — readiness gate** | **Probabilistic** | `temperature=0.0` — Haiku decides if there's enough signal |
| Phase 2 — KB retrieval | **Deterministic** | Vector search + score sort, no LLM |
| Stage determination | **Deterministic** | Segment count thresholds (3 / 8) |
| **Phase 3 — Track A analysis** | **Probabilistic** | `temperature=0.1` — Sonnet generates the full analysis |
| **Phase 3 — Track B analysis** | **Probabilistic** | `temperature=0.1` — Same Sonnet with directive override appended |
| Section parsing | **Deterministic** | Regex against known bold headers |
| Mermaid diagram rendering | **Deterministic** | Frontend renders whatever text Sonnet outputs |
| **Recommendation rerank** | **Probabilistic** | Haiku picks top 3 chunk indices |
| **Recommendation synthesis** | **Probabilistic** | Sonnet generates title, summary, action items |
| Meeting save | **Deterministic** | JSON serialization to disk |

**Temperature choices:**
- `0.0` — used for structural/decision prompts (CCM extraction, query generation, reranking): maximally consistent JSON output, no creativity needed
- `0.1` — used for analysis generation: slight variation in phrasing allowed, high consistency maintained

---

## Every Prompt in the System

### 1. CCM Extraction — `backend/ccm/engine.py`

**Model:** Haiku | **Called:** Every final transcript segment | **Temperature:** 0.0

**System prompt (`_SYSTEM`):**
```
You are a real-time context extraction engine for an AWS Solutions Architect
meeting assistant. Extract structured facts from each transcript segment.
Respond with ONLY valid JSON — no markdown fences, no explanation.
```

**User prompt template (`_PROMPT_TEMPLATE`):**
```
Analyze this AWS customer meeting transcript segment.

Segment: "{text}"

Prior context:
- AWS services already noted: {known_aws}
- Competitors/tools already noted: {known_comp}
- Active topics: {active_topics}
- Meeting goal so far: "{meeting_goal}"

Return JSON matching this schema exactly (no extra keys):
{
  "aws_services": [...],
  "competitors": [...],
  "questions": [...],
  "topics": [...],
  "meeting_goal": "...",
  "should_recommend": true
}
```

**Why temperature=0.0:** This is pure structured extraction. The model has no room to improvise — it either sees a service name or it doesn't.

---

### 2. Phase 1 Query Generation — `backend/analysis/prompts.py`

**Model:** Haiku | **Called:** Once per analysis cycle | **Temperature:** 0.0

**Prompt (`QUERY_GEN_PROMPT`):**

Receives: last 30 transcript segments, known services/topics from CCM, list of queries already sent in prior cycles.

Returns JSON: `{"ready": bool, "reasoning": "...", "new_queries": [...]}`.

Key rules baked in:
- Do not generate queries until there is a clear customer situation, at least one constraint, and some understanding of the goal
- Maximum 3 new queries per cycle
- Never repeat a prior query — deduplication enforced both by prompt instruction and in code

---

### 3. Phase 3 Analysis — `backend/analysis/prompts.py`

**Model:** Sonnet | **Called:** Once per cycle per active track | **Temperature:** 0.1

Three components assembled at call time:

**A. System prompt — `MEETING_TYPE_PROMPTS[meeting_type]`**

Sets the SA persona. One of 8 entries selected based on the meeting type chosen in the Start Meeting modal:

| Meeting Type | Focus areas in system prompt |
|---|---|
| Customer Meeting | Pain points, current architecture, migration paths, competitive positioning |
| OneTeam / Partner | Joint solution design, partner gaps, co-sell opportunities |
| SA Manager Sync | OKR impact, escalation blockers, portfolio patterns |
| Internal Architecture Review | Well-Architected pillars, anti-patterns, service rationale |
| Competitive Deal | Competitor identification, AWS differentiators, migration cost/risk |
| Migration Assessment | 7Rs strategies, MGN/DMS/SCT tools, phased roadmap |
| GenAI / ML Workshop | Bedrock models, RAG patterns, data maturity, responsible AI |
| Cost Optimization Review | Rightsizing, Savings Plans, architectural cost levers |

**B. User prompt — `ANALYSIS_PROMPT`**

Template variables filled at runtime:
- `{stage_label}` — e.g. `"STAGE 2 — Direction emerging, use [ASSUMPTION: ...] for anything unconfirmed"`
- `{previous_analysis}` — prior cycle's output (capped at 2500 chars to preserve output budget)
- `{segment_count}` — number of segments seen
- `{transcript}` — last 50 segments, each line prefixed with `[Name | Org | Role]:` when speaker mapping exists
- `{kb_context}` — top 12 accumulated KB chunks (URL + title + 300-char excerpt)
- `{customer_context_section}` — prior meeting summaries from AgentCore Memory (if configured)
- `{participants_context}` — built by `_build_participants_context()`: participant list grouped by org + role expertise descriptions from `roles.py` + speaker-aware analysis guidelines

Output sections and stage gating:

| Section | Stage 1 | Stage 2 | Stage 3 |
|---|---|---|---|
| Situation | ✅ | ✅ | ✅ |
| Current State | ✅ | ✅ | ✅ |
| Customer Needs | ✅ | ✅ | ✅ |
| Open Questions | ✅ | ✅ | ✅ |
| Proposed Solution Architecture | ❌ | ✅ (with `[ASSUMPTION:]`) | ✅ |
| Key Recommendations | ❌ | 2–3 only | 3–5 prioritized |
| Sources | ❌ | ✅ | ✅ |
| Action Items | ❌ | ✅ | ✅ |
| Current State Diagram (Mermaid) | ❌ | ❌ | ✅ |
| Future State Diagram (Mermaid) | ❌ | ❌ | ✅ |

**C. Track B extension — `DIRECTIVE_EXTENSION`** (appended only when directives exist)

Injects the SA's directives as highest-priority instructions. Instructs Sonnet to follow the directive even if it conflicts with its own reading of the transcript. Suppresses the Current State Diagram (Track A already produced it) but always requires a Future State Diagram shaped by the directive.

---

### 4. Recommendation Agent Rerank — `backend/agent/recommendation_agent.py`

**Model:** Haiku | **Called:** When ≥4 KB chunks retrieved, to pick top 3 | **Temperature:** default

Inline prompt — receives meeting context + query + up to N chunk summaries, returns a JSON array of 3 indices (0-based), most relevant first. Used only when AgentCore is not configured.

---

### 5. Recommendation Agent Synthesis — `backend/agent/recommendation_agent.py`

**Model:** Sonnet | **Called:** After rerank, to generate the card | **Temperature:** default

Inline prompt — receives meeting context, what was just discussed, and the top 3 KB chunks as grounding. Returns JSON:
```json
{
  "title": "...",
  "summary": "...",
  "service_mentioned": [...],
  "action_items": [...],
  "source_urls": [...],
  "confidence": 0.85
}
```

---

## Audio Pipeline Fundamentals

### Sample rate

`AUDIO_SAMPLE_RATE=16000` means 16,000 amplitude measurements per second (16 kHz). Human speech tops out around 8 kHz, so 16 kHz captures everything relevant while avoiding the bandwidth cost of music-grade audio (44.1 kHz).

### Chunk duration

`AUDIO_CHUNK_DURATION_MS=100` means the app sends a new audio packet to the STT service every 100ms. Each packet contains:
```
16,000 samples/sec × 0.1 sec = 1,600 samples
× 2 bytes/sample (16-bit PCM) = 3,200 bytes per packet
```

This controls latency and smoothness, not where segment boundaries fall. The STT provider decides boundaries based on acoustic silence detection.

### Segment boundary

Amazon Transcribe finalizes a segment after detecting ~0.3–1.0 seconds of silence. In practice, most segments in a meeting correspond to one sentence or one short thought. The app has no control over this — it only receives the final committed text.

---

## State and Storage

### Backend session state

All session state lives in `AnalysisEngine` (one instance per meeting, recreated on each `POST /meeting/start`):

| Field | What it holds |
|---|---|
| `_transcript_segments` | `[(text, speaker_id), ...]` — rolling window, max 100 |
| `_accumulated_kb` | KB chunks from all cycles, sorted by score, max 25 |
| `_prior_queries` | All queries ever sent — used to avoid duplicates |
| `_previous_analysis_a/b` | Last cycle's output — fed back as context |
| `_directives` | All active SA directives |
| `_speaker_mapping` | `{"spk_0": {"name": "...", "org": "...", "role": "..."}}` |
| `_cycle_count`, `_segment_count` | Counters |

`CCMEngine` holds `CCMState` separately — also recreated on meeting start.

### Frontend state

All frontend state lives in a Zustand store (`frontend/src/store/meetingStore.ts`). Key slices:

| Slice | What it holds |
|---|---|
| `transcriptChunks` | All final segments with IDs, text, speaker, timestamp |
| `speakerMappings` | Mirror of backend speaker mapping |
| `analysisTrackA/B` | Latest `AnalysisResult` from each track |
| `participants` | Names entered in Start Meeting modal |
| `availableRoles`, `roleDescriptions` | Fetched from `GET /meeting/config` on startup |
| `ownerParticipant` | SA's own name — pinned first in Name dropdown |
| `pendingCorrections` | Speaker corrections not yet flushed to backend |

### Meeting persistence

On `Stop Meeting`, the frontend sends the full snapshot to `POST /meetings/save`. The backend writes a JSON file to `meetings/{session_id}.json`. `GET /meetings` returns an index; `GET /meetings/{id}` returns the full record for the Past Meetings drawer.

---

## WebSocket Message Types

| Event type | Direction | Payload |
|---|---|---|
| `ccm_update` | Server → client | Full CCM state snapshot |
| `analysis_update` | Server → client | `AnalysisResult` for Track A |
| `steered_analysis_update` | Server → client | `AnalysisResult` for Track B |
| `recommendation` | Server → client | Recommendation card |
| `speaker_mapping_update` | Server → client | Current mapping dict |
| `meeting_started` | Server → client | Session ID, type, participants |
| `meeting_stopped` | Server → client | Session ID |

The frontend WebSocket hook (`useWebSocket.ts`) reconnects with exponential backoff on disconnect.
