# AWS SA Meeting Intelligence Assistant

A real-time AI assistant for AWS Solutions Architects. Listens to live customer meetings, builds a progressive context map, searches a pre-indexed AWS knowledge base, runs two-track staged analysis (auto + SA-steered), and surfaces architecture diagrams, recommendations, and key insights — all in real-time.

---

## What It Does

| Feature | Description |
|---|---|
| **Live Transcript** | Real-time speech-to-text with speaker labels, full session history |
| **Speaker Diarization + Mapping** | Per-speaker talk-time bars, map speaker IDs to names/org/role mid-meeting; dropdowns sorted alphabetically |
| **Speaker Re-attribution** | Click any transcript line's speaker label to correct mis-attributed segments inline |
| **Role-Aware Analysis** | Speaker roles injected into Sonnet prompt with domain expertise context |
| **Action Items** | Extracted AWS / Customer / Partner action items shown in dedicated tab (Stage 2+) |
| **Stage Labels** | Header shows stage number + description (e.g. `Stage 2 · Direction emerging`) |
| **Owner Profile** | SA's own name auto-pinned as first option in speaker Name dropdown; set via `USER_*` env vars |
| **Conversation Context Map (CCM)** | Per-segment extraction of AWS services, topics, open questions |
| **Two-Track Analysis** | Track A (auto) + Track B (SA-steered via directives); 3-stage progression |
| **Architecture Diagrams** | Mermaid diagrams: current state, future state auto, future state steered |
| **Recommendation Cards** | Instant cards with AWS docs links, action items, code references |
| **SA Directives** | Pre-canned or custom directives to steer Track B mid-meeting; configurable via `.env` |
| **Resizable Panels** | Drag the divider between transcript and analysis panels (20–80% range) |
| **Past Meetings** | All meetings auto-saved as JSON; browse, replay, and compare (with speaker names) |
| **Meeting Types** | 8 types (Customer Meeting, OneTeam, SA Manager Sync, etc.) |
| **AgentCore** | Optional: deploy recommendation agent to Bedrock AgentCore Runtime + cross-session Memory |

---

## Architecture

```
Microphone / System Audio  (BlackHole for capturing both sides of a Zoom/Teams call)
         │
         ▼
STT Engine ─┬─ Amazon Transcribe Streaming  (cloud, best accuracy, speaker labels + diarization)
             └─ faster-whisper large-v3-turbo (local, offline, Apple Silicon GPU)
         │
         ▼  (every final segment, with speaker ID)
Conversation Context Map Engine  — extracts services, topics, questions  (<10ms)
         │
         ├──▶  CCM state → WebSocket → frontend (live)
         │
         ▼  (every 3 segments)
Analysis Engine ──────────────────────────────────────────────────────────
  Speaker Mapping  — name/org/role per speaker ID, injected into prompts
  Phase 1 (Haiku):  readiness check + KB search query generation
  Phase 2 (Sonnet): staged analysis with accumulated KB context + participant context
    ├─ Track A  (auto)    → analysis_update  WebSocket
    └─ Track B  (steered) → steered_analysis_update  WebSocket
         │
         ├──▶ Bedrock KB (AOSS + Cohere Embed v3 + Hybrid search)
         └──▶ AWS Docs Search API
         │
         ▼
Recommendation Agent ─┬─ Local (Haiku → Sonnet)  when AgentCore not configured
                       └─ AgentCore Runtime        when AGENTCORE_RUNTIME_ARN is set
         │
         ▼
WebSocket → React/TypeScript Frontend
  ├─ Transcript panel (55%)    — full history, mapped speaker names, inline re-attribution
  └─ Live Analysis panel (45%) — Auto | Steered | Diagrams | Speakers tabs
         │
         ▼
Meeting Storage  — auto-saved JSON on stop (includes speaker mapping), browsable in Past Meetings drawer
```

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | ≥ 3.12 | |
| uv | ≥ 0.11 | [install](https://docs.astral.sh/uv/getting-started/installation/) |
| Node.js | ≥ 18 | For the React frontend |
| AWS CLI | ≥ 2 | Configured with credentials |
| AWS access | — | Bedrock + Bedrock KB + optionally Transcribe |

### Required AWS IAM Permissions

```json
{
  "Effect": "Allow",
  "Action": [
    "bedrock:InvokeModel",
    "bedrock-agent-runtime:Retrieve",
    "bedrock-agent:StartIngestionJob",
    "s3:PutObject", "s3:GetObject", "s3:ListBucket",
    "transcribe:StartStreamTranscription",
    "iam:CreateRole", "iam:PutRolePolicy", "iam:AttachRolePolicy",
    "aoss:APIAccessAll",
    "aoss:CreateCollection", "aoss:CreateAccessPolicy",
    "aoss:CreateSecurityPolicy"
  ],
  "Resource": "*"
}
```

> `transcribe:StartStreamTranscription` only needed when `STT_PROVIDER=transcribe`.  
> `iam:*` and `aoss:*` only needed to run `scripts/setup_kb.py`.

### Required Bedrock Model Access

Enable in **AWS Console → Bedrock → Model access** (must be in the same region):

- `cohere.embed-english-v3` — KB embeddings
- `anthropic.claude-haiku-4-5-*` — fast phase-1 analysis
- `anthropic.claude-sonnet-4-6-*` — staged analysis + recommendation synthesis

---

## Step 0 — Create the Bedrock Knowledge Base (one-time per AWS account)

### Option A — Automated (recommended)

```bash
git clone https://github.com/kavap/awssameetingassistant.git
cd awssameetingassistant
uv sync
uv run python scripts/setup_kb.py
```

This creates: S3 bucket + IAM role + OpenSearch Serverless collection + Bedrock KB.  
At the end it prints three values — add them to your `.env`:

```
BEDROCK_KB_S3_BUCKET=meeting-assistant-kb-XXXXXXXX-prod
BEDROCK_KB_ID=ABCD1234EF
BEDROCK_KB_DATA_SOURCE_ID=XY1234ABCD
```

### Option B — AWS Console (manual)

1. **Bedrock → Knowledge Bases → Create**
2. Embedding model: **Cohere Embed English v3**
3. Vector store: **Amazon OpenSearch Serverless** (auto-provisioned)
4. Data source: **Amazon S3** → new bucket
5. Chunking: **No chunking** (ingest.py chunks documents itself)
6. Copy KB ID and Data Source ID into `.env`

### Seed the Knowledge Base

```bash
uv run python scripts/ingest.py --urls data/urls.txt
```

Monitor sync: **AWS Console → Bedrock → Knowledge Bases → your KB → Data Sources → Sync history**.

To add more sources, edit `data/urls.txt` and re-run.

---

## Option A — Deploy on MacBook (Local)

### 1. Install System Dependencies

```bash
# Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

brew install git node portaudio awscli
curl -LsSf https://astral.sh/uv/install.sh | sh && source $HOME/.local/bin/env
```

### 2. Configure AWS Credentials

```bash
aws configure
# Enter: Access Key ID, Secret Access Key, region (us-east-1), output (json)
```

For SSO / federated accounts:
```bash
aws configure sso
aws sso login --profile your-profile-name
export AWS_PROFILE=your-profile-name
```

### 3. Clone and Configure

```bash
git clone https://github.com/kavap/awssameetingassistant.git
cd awssameetingassistant
cp .env.example .env
# Edit .env — fill in BEDROCK_KB_* values from Step 0
```

### 4. Choose STT Provider

**Amazon Transcribe (cloud, best accuracy):**
```
STT_PROVIDER=transcribe
```

**Whisper (local, offline, privacy-first):**
```
STT_PROVIDER=whisper
WHISPER_MODEL=large-v3-turbo
WHISPER_DEVICE=mps        # Apple Silicon GPU — use "cpu" for Intel Mac
WHISPER_COMPUTE_TYPE=int8
```

### 5. Install Python Dependencies

```bash
uv sync                          # Transcribe only
uv sync --extra whisper          # add local Whisper STT
uv sync --extra agentcore        # add AgentCore Runtime + Memory (optional)
```

> First Whisper run downloads the model (~800 MB from HuggingFace). Subsequent starts are instant.

If `sounddevice` fails to find PortAudio:
```bash
brew install portaudio && uv sync --reinstall-package sounddevice
```

### 6. Start the Backend

```bash
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### 7. Start the Frontend

```bash
cd frontend && npm install && npm run dev
```

Open **http://localhost:5173**

### 8. Grant Microphone Permission (macOS)

**System Settings → Privacy & Security → Microphone** → enable for Terminal / iTerm2 / Warp.

### 9. Capture Both Sides of a Call (recommended)

Install [BlackHole](https://existential.audio/blackhole/) (free virtual audio driver):
```bash
brew install --cask blackhole-2ch
```

In **Audio MIDI Setup** (Applications → Utilities):
1. `+` → **Create Multi-Output Device**
2. Add **BlackHole 2ch** + your speakers/headphones
3. Set as system output in System Settings
4. In Zoom/Teams: set microphone input to **BlackHole 2ch**

This routes all meeting audio (both sides) through BlackHole.

---

## Option B — Deploy on AWS Cloud VM

Recommended for persistent, always-on deployment (EC2, Cloud9, SageMaker Studio).

### 1. Launch EC2

- Type: **t3.medium** or larger
- AMI: Amazon Linux 2023 or Ubuntu 22.04
- Region: `us-east-1`
- IAM instance profile: attach the permissions from Prerequisites

### 2. Install System Dependencies

**Amazon Linux 2023:**
```bash
sudo dnf update -y && sudo dnf install -y git nodejs npm
curl -LsSf https://astral.sh/uv/install.sh | sh && source $HOME/.local/bin/env
```

**Ubuntu 22.04:**
```bash
sudo apt update && sudo apt install -y git nodejs npm
curl -LsSf https://astral.sh/uv/install.sh | sh && source $HOME/.local/bin/env
```

### 3. Clone and Configure

```bash
git clone https://github.com/kavap/awssameetingassistant.git
cd awssameetingassistant
cp .env.example .env
```

Edit `.env`:
```
BEDROCK_KB_S3_BUCKET=...
BEDROCK_KB_ID=...
BEDROCK_KB_DATA_SOURCE_ID=...
STT_PROVIDER=transcribe     # no local mic on cloud VM
USE_FAKE_AUDIO=true          # set to false if you pipe audio via your laptop
```

### 4. Install and Start

```bash
uv sync
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

```bash
# In a second terminal
cd frontend && npm install && npm run dev
```

Verify backend:
```bash
curl http://localhost:8000/health
# {"status":"ok","bedrock_kb_configured":true,"stt_provider":"transcribe",...}
```

> Open port 5173 in the EC2 security group, or use an SSH tunnel:
> `ssh -L 5173:localhost:5173 -L 8000:localhost:8000 ec2-user@<ip>`

---

## Optional — AgentCore Runtime + Memory

AgentCore replaces the local `RecommendationAgent` with a cloud-hosted agent and adds cross-session customer memory. Requires `uv sync --extra agentcore`.

### Create Memory Resource

```bash
uv run python scripts/setup_agentcore.py
# Prints AGENTCORE_MEMORY_ID and AGENTCORE_MEMORY_STRATEGY_ID — add to .env
```

### Deploy the Recommendation Agent

```bash
npm install -g @aws/agentcore
cd backend/agentcore
agentcore deploy --name recommendation-agent --defaults
# Prints AGENTCORE_RUNTIME_ARN — add to .env
```

When both are configured, the backend uses AgentCore for recommendations and stores a session summary after each meeting stop (per customer ID).

---

## Moving to a New AWS Account

To redeploy in a different AWS account or region:

1. **Enable Bedrock model access** in the new account/region (Cohere Embed, Haiku, Sonnet)
2. Re-run `scripts/setup_kb.py` — creates new S3, IAM role, AOSS collection, KB
3. Re-run `scripts/ingest.py` — re-uploads documents and triggers sync
4. Update `.env` with the new `BEDROCK_KB_*` values (and `AWS_REGION` if different)
5. No other infrastructure to migrate — all state is in the KB and local `meetings/` directory

If you also use AgentCore:
1. Re-run `scripts/setup_agentcore.py` — creates new Memory resource
2. Re-run `agentcore deploy` — deploys agent to new account
3. Update `AGENTCORE_RUNTIME_ARN`, `AGENTCORE_MEMORY_ID`, `AGENTCORE_MEMORY_STRATEGY_ID` in `.env`

---

## Using the Assistant

1. Open **http://localhost:5173**
2. Click **Start Meeting** → fill in the modal:
   - **Meeting Name** (optional, shown in history)
   - **Meeting Type** (Customer Meeting, OneTeam, etc.)
   - **Customer ID** (optional, used to load prior context from AgentCore Memory)
   - **Participants** — paste names/emails separated by `;` (Outlook copy-paste) or new lines; used to map speaker IDs during the call
   - **Roles Present** — select all roles attending (AWS / Customer / Partner); used to enrich analysis prompts
3. Watch the transcript stream in real-time (left panel)
   - Speaker labels show mapped names (e.g. "John S.") once mapped in the Speakers tab
   - Click any speaker label to correct mis-attributed segments inline
4. **Live Analysis** panel (right):
   - **Auto tab** — autonomous 3-stage analysis (situation → architecture → recommendations)
   - **Steered tab** — SA-directed analysis (type a directive in the bar below)
   - **Diagrams tab** — Mermaid architecture diagrams (current state + future state)
   - **Speakers tab** — talk-time bars + map each diarized speaker ID to a name, org, and role
5. Use the **directive bar** to steer Track B mid-meeting (e.g. "focus on data lake migration")
6. Click **Stop** — meeting is auto-saved (includes speaker mapping)
7. Click **History** in the header to browse past meetings (transcript with mapped names + analysis + diagrams)

### Speaker Mapping

Open the **Speakers tab** in the analysis panel during a meeting:

- **Talk-time bars** show word count per speaker (updates live)
- For each detected speaker, set their **Name** (select from participants list or type), **Organization** (AWS / Customer / AWS Partner / Other), and **Role** (filtered by org)
- Role dropdowns show a tooltip with the role's domain expertise description
- Click **Apply Mapping & Re-analyze** to persist the mapping and trigger a fresh analysis with participant context

Speaker corrections made in the transcript panel are batched and synced to the backend on each new segment.

### SA Directives (steering Track B)

Use the pre-canned buttons or type any directive into the bar at the bottom of the analysis panel. Examples:
- `Focus on data lake migration to S3 + Glue`
- `Customer is price sensitive — emphasize cost optimization`
- `Compare with on-prem Databricks`

Track B runs a separate Sonnet analysis cycle with your directive injected into the prompt.

The pre-canned directive buttons are configurable — see `DEFAULT_DIRECTIVES` in the Configuration Reference below.

---

## Adding Custom Knowledge Sources

Edit `data/urls.txt` — any publicly accessible URL works:

```text
# AWS docs
https://docs.aws.amazon.com/redshift/latest/mgmt/serverless-whatis.html
https://aws.amazon.com/blogs/big-data/top-10-performance-tuning-tips-for-amazon-redshift/

# Internal wiki (accessible from where you run ingest.py)
https://wiki.internal.company.com/aws-reference-architectures
```

Re-run ingestion:
```bash
uv run python scripts/ingest.py --urls data/urls.txt
# Trigger sync only (after manual S3 upload):
uv run python scripts/ingest.py --sync-only
```

---

## Project Structure

```
awssameetingassistant/
├── backend/
│   ├── main.py                      # FastAPI app — REST + WebSocket endpoints
│   ├── config.py                    # All settings from .env (pydantic-settings)
│   ├── roles.py                     # Role expertise descriptions (26 roles, injected into Sonnet prompts)
│   ├── storage.py                   # Meeting JSON persistence (meetings/ dir)
│   ├── audio/capture.py             # Mic capture, fake audio fallback
│   ├── ccm/
│   │   ├── engine.py                # Conversation Context Map engine (<10ms/call)
│   │   └── models.py                # CCMState, CCMUpdateEvent dataclasses
│   ├── analysis/
│   │   ├── engine.py                # Two-track staged analysis (Haiku + Sonnet) + speaker mapping
│   │   ├── models.py                # AnalysisResult, meeting types
│   │   └── prompts.py               # All LLM prompts (query gen, analysis, directives)
│   ├── knowledge_base/
│   │   ├── bedrock_kb.py            # Bedrock KB retrieval
│   │   └── docs_search.py           # AWS Docs Search API
│   ├── transcription/
│   │   ├── transcribe_stream.py     # Amazon Transcribe Streaming
│   │   └── whisper_stream.py        # faster-whisper local STT
│   ├── agent/
│   │   └── recommendation_agent.py  # Local agent (used when AgentCore not configured)
│   ├── agentcore/
│   │   ├── client.py                # AgentCore Runtime invocation
│   │   └── memory.py                # AgentCore cross-session Memory
│   └── websocket/manager.py         # WebSocket broadcast manager
├── frontend/
│   ├── src/
│   │   ├── App.tsx                  # Two-panel layout, history button, save-on-stop
│   │   ├── store/meetingStore.ts    # Zustand state (transcript, analysis, speaker mappings, session meta)
│   │   ├── hooks/useWebSocket.ts    # WS with exponential-backoff reconnect
│   │   ├── types/index.ts           # All TypeScript types (ParticipantInfo, SpeakerMappings, etc.)
│   │   └── components/
│   │       ├── TranscriptPanel.tsx  # Full transcript, auto-scroll, speaker filter, correction flush
│   │       ├── TranscriptChunkItem.tsx # Per-line chunk with clickable speaker re-attribution
│   │       ├── AnalysisPanel.tsx    # Auto | Steered | Diagrams | Speakers tabs
│   │       ├── SpeakerMappingPanel.tsx # Talk-time bars + speaker-to-person mapping table
│   │       ├── AnalysisView.tsx     # Shared analysis renderer (live + past meetings)
│   │       ├── DiagramsPanel.tsx    # Three-diagram tab switcher
│   │       ├── MermaidRender.tsx    # Mermaid render queue + DiagramView component
│   │       ├── DirectivesBar.tsx    # SA directive input + config-driven pre-canned buttons
│   │       ├── PastMeetingsDrawer.tsx # History drawer + MeetingDetail viewer (speaker names)
│   │       ├── RecommendationsPanel.tsx
│   │       ├── RecommendationCard.tsx
│   │       └── StartMeetingModal.tsx # Meeting name, type, customer ID, participants, roles checklist
│   └── package.json
├── scripts/
│   ├── setup_kb.py                  # One-time: create Bedrock KB infrastructure
│   ├── setup_agentcore.py           # One-time: create AgentCore Memory resource
│   ├── ingest.py                    # Upload docs to S3 + trigger KB sync
│   └── scrape_aws_docs.py           # Optional: bulk scrape AWS docs pages
├── meetings/                        # Auto-created; saved meeting JSON files
├── data/
│   └── urls.txt                     # Knowledge source URLs for ingestion
├── tests/                           # Unit tests (pytest)
├── .env.example                     # All config variables with comments
├── pyproject.toml                   # Python deps (uv)
└── PLAN.md                          # Full phased roadmap
```

---

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `AWS_REGION` | `us-east-1` | AWS region for all services |
| `BEDROCK_HAIKU_MODEL` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | Phase-1 analysis model |
| `BEDROCK_SONNET_MODEL` | `us.anthropic.claude-sonnet-4-6-20250514-v1:0` | Phase-2 analysis + recommendations |
| `BEDROCK_EMBEDDING_MODEL` | `cohere.embed-english-v3` | KB embedding model |
| `BEDROCK_KB_ID` | *(required)* | Bedrock KB ID from `setup_kb.py` |
| `BEDROCK_KB_S3_BUCKET` | *(required)* | S3 bucket for KB documents |
| `BEDROCK_KB_DATA_SOURCE_ID` | *(required)* | KB data source ID |
| `BEDROCK_KB_SEARCH_TYPE` | `HYBRID` | `HYBRID` / `SEMANTIC` / `KEYWORD` |
| `BEDROCK_KB_NUM_RESULTS` | `8` | Top-K results per KB query |
| `STT_PROVIDER` | `transcribe` | `transcribe` or `whisper` |
| `WHISPER_MODEL` | `large-v3-turbo` | Whisper model size |
| `WHISPER_DEVICE` | `cpu` | `cpu` / `mps` (Apple Silicon) / `cuda` |
| `WHISPER_COMPUTE_TYPE` | `int8` | `int8` (CPU) / `float16` (GPU) |
| `WHISPER_BUFFER_SECONDS` | `4.0` | Audio buffer per transcription pass |
| `TRANSCRIBE_LANGUAGE` | `en-US` | Language code for Transcribe |
| `USE_FAKE_AUDIO` | `false` | `true` = use WAV file (cloud VMs with no mic) |
| `FAKE_AUDIO_PATH` | `data/test_audio.wav` | WAV file path for fake audio |
| `AGENTCORE_RUNTIME_ARN` | *(optional)* | AgentCore Runtime ARN after `agentcore deploy` |
| `AGENTCORE_MEMORY_ID` | *(optional)* | AgentCore Memory ID from `setup_agentcore.py` |
| `AGENTCORE_MEMORY_STRATEGY_ID` | *(optional)* | Memory strategy ID from `setup_agentcore.py` |
| `DEFAULT_MEETING_ROLES` | *(26 built-in roles)* | Comma-separated roles shown in Start Meeting modal checklist |
| `DEFAULT_DIRECTIVES` | *(14 built-in directives)* | Comma-separated SA steering tags shown as quick-click buttons in the directives bar |

---

## Running Tests

```bash
uv run pytest tests/ -v
```

No AWS credentials needed — KB and Bedrock calls are mocked.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `PortAudioError: No Default Input Device` | Set `USE_FAKE_AUDIO=true`, or `brew install portaudio && uv sync --reinstall-package sounddevice` |
| `Bedrock: AccessDeniedException` | Check IAM permissions and model access is enabled in Bedrock console |
| `ResourceNotFoundException` on KB retrieve | `BEDROCK_KB_ID` wrong or KB is in a different region than `AWS_REGION` |
| No analysis after speaking | Analysis triggers after 3 final segments; check backend logs for `[analysis]` lines |
| No diagrams appearing | Diagrams appear at Stage 3 (≥8 segments); check Sonnet `max_tokens` isn't truncating |
| `Transcribe: UnrecognizedClientException` | Verify `AWS_REGION`, `TRANSCRIBE_REGION`, and `transcribe:StartStreamTranscription` IAM permission |
| Whisper not found | Run `uv sync --extra whisper` |
| Whisper slow | Set `WHISPER_DEVICE=mps` on Apple Silicon; use `large-v3-turbo` not `large-v3` |
| Whisper model download fails | Check internet — model downloads from HuggingFace on first run (~800 MB) |
| Frontend not connecting | Confirm backend is on port 8000; check browser console for WS errors |
| Mermaid diagram not rendering | Open DevTools (F12) → Console for render errors; click "Source" to inspect raw diagram |
| Past meetings drawer empty | Meetings are saved on Stop — start and stop a meeting first |
| Speaker labels show `spk_0` not names | Open the **Speakers tab**, map each speaker, then click **Apply Mapping** |
| Speaker tab shows no speakers | Diarization data appears after the first final transcript segment; check `STT_PROVIDER=transcribe` (Whisper diarization requires pyannote) |
| AgentCore: no recommendations | Verify `AGENTCORE_RUNTIME_ARN` is set and agent is deployed and healthy |

---

## Roadmap

See **[PLAN.md](PLAN.md)** for the full phased roadmap. Summary:

- **Phase 1** ✅ — Live transcript, CCM, two-track analysis, diagrams, SA directives, meeting persistence
- **Phase 2** — Multi-agent parallel search (architecture, migration, cost, security agents), Revision Agent
- **Phase 3** ✅ — Speaker diarization UI: talk-time bars, speaker-to-person mapping, inline re-attribution, role-aware analysis prompts, config-driven directives
- **Phase 3b** — System audio auto-config wizard (BlackHole/VB-Cable setup guide)
- **Phase 4** — Electron desktop overlay (always-on-top, picture-in-picture)
- **Phase 5** — Configurable `sources.yaml`, scheduled ingestion, GitHub + YouTube indexing

---

## License

MIT
