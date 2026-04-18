# AWS SA Meeting Intelligence Assistant

A real-time AI assistant that listens to live AWS customer and internal meetings, builds a progressive conversation context map, searches a pre-indexed AWS knowledge base, and proactively surfaces answers, architecture patterns, best practices, blog links, and code samples — all in real-time.

---

## Architecture Overview

```
Microphone / System Audio
         │
         ▼
STT Engine (choose one):
  ├─ Amazon Transcribe Streaming  (cloud, best accuracy, partial results)
  └─ faster-whisper large-v3-turbo (local, offline, privacy-first, Mac-friendly)
         │
         ▼
Conversation Context Map Engine  (detects AWS services, open questions, topics)
         │
         ▼
RecommendationAgent
   ├─ Bedrock Knowledge Base      (managed vector store, serverless)
   │   └─ Cohere Embed English v3 (1024-dim embeddings, configured on KB)
   │   └─ Hybrid search           (semantic + keyword, RRF fusion)
   ├─ Claude Haiku                (rerank top results)
   └─ Claude Sonnet               (synthesize recommendation card)
         │
         ▼
WebSocket → React Frontend  (live transcript + recommendation cards)
```

**Key design decisions:**
- Knowledge base populated **offline** via S3 → Bedrock KB sync — no live scraping during meetings
- Bedrock KB handles embedding (Cohere) and hybrid search internally — no self-managed vector store
- STT is configurable: cloud Transcribe for best accuracy or local Whisper for privacy/offline use
- All AWS calls use the instance IAM role or local credentials (no hardcoded secrets)

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | ≥ 3.12 | |
| uv | ≥ 0.11 | [install](https://docs.astral.sh/uv/getting-started/installation/) |
| Node.js | ≥ 18 | For the React frontend |
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
    "transcribe:StartStreamTranscription"
  ],
  "Resource": "*"
}
```

> `transcribe:StartStreamTranscription` is only needed when `STT_PROVIDER=transcribe`.

### Required Bedrock Model Access

Enable in **AWS Console → Bedrock → Model access** (us-east-1):
- `cohere.embed-english-v3` — embeddings for the knowledge base
- `anthropic.claude-3-5-haiku-20241022-v1:0` — reranking
- `anthropic.claude-3-7-sonnet-20250219-v1:0` — recommendation synthesis

---

## Step 0: Create the Bedrock Knowledge Base (one-time)

Before running the assistant, you need a Bedrock Knowledge Base backed by S3.

### Option A — Automated (recommended)

```bash
git clone https://github.com/kavap/awssameetingassistant.git
cd awssameetingassistant
uv sync
uv run python scripts/setup_kb.py
```

This creates:
1. An S3 bucket for document storage
2. An IAM execution role for Bedrock KB
3. A Bedrock Knowledge Base configured with **Cohere Embed English v3**
4. An S3 data source attached to the KB

At the end it prints the three values to add to your `.env`:
```
BEDROCK_KB_S3_BUCKET=meeting-assistant-kb-XXXXXXXX-prod
BEDROCK_KB_ID=ABCD1234EF
BEDROCK_KB_DATA_SOURCE_ID=XY1234ABCD
```

### Option B — AWS Console (manual)

1. **AWS Console → Bedrock → Knowledge Bases → Create**
2. Embedding model: **Cohere Embed English v3**
3. Vector store: **Amazon OpenSearch Serverless** (auto-provisioned)
4. Data source: **Amazon S3** → create a new bucket
5. Chunking strategy: **No chunking** (ingest.py chunks documents itself)
6. Copy the **Knowledge Base ID** and **Data Source ID** into `.env`

---

## Option A: Deploy on AWS (Cloud VM / EC2)

Recommended for persistent always-on deployment or cloud dev environments (Cloud9, SageMaker Studio, EC2).

### 1. Launch an EC2 Instance

Recommended: **t3.medium** or larger, **Amazon Linux 2023** or **Ubuntu 22.04**, `us-east-1`.
Attach an IAM instance profile with the permissions above.

### 2. Install System Dependencies

**Amazon Linux 2023:**
```bash
sudo dnf update -y
sudo dnf install -y git nodejs npm
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

**Ubuntu 22.04:**
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git nodejs npm
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

### 3. Clone and Configure

```bash
git clone https://github.com/kavap/awssameetingassistant.git
cd awssameetingassistant
cp .env.example .env
```

Edit `.env` and fill in the KB values from Step 0:
```bash
BEDROCK_KB_S3_BUCKET=meeting-assistant-kb-XXXXXXXX-prod
BEDROCK_KB_ID=ABCD1234EF
BEDROCK_KB_DATA_SOURCE_ID=XY1234ABCD
STT_PROVIDER=transcribe      # use transcribe on EC2
USE_FAKE_AUDIO=true          # no physical mic on a cloud VM
```

### 4. Install Python Dependencies

```bash
uv sync
```

### 5. Seed the Knowledge Base

Fetches AWS docs, uploads chunked text to S3, and triggers a Bedrock KB sync job.

```bash
uv run python scripts/ingest.py --urls data/urls.txt
```

Monitor the sync job: **AWS Console → Bedrock → Knowledge Bases → your KB → Data Sources → Sync history**

To re-upload and re-sync at any time:
```bash
uv run python scripts/ingest.py --urls data/urls.txt
# or just trigger a sync without re-uploading:
uv run python scripts/ingest.py --sync-only
```

### 6. Start the Backend

```bash
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Verify:
```bash
curl http://localhost:8000/health
# Expected: {"status":"ok","bedrock_kb_configured":true,"stt_provider":"transcribe",...}
```

### 7. Start the Frontend

```bash
cd frontend && npm install && npm run dev
```

Open **http://localhost:5173** (open port 5173 in the EC2 security group, or use an SSH tunnel).

> **Security note:** For production, put nginx in front and restrict access. Do not expose 5173 publicly without authentication.

### 8. Use the Assistant

1. Open the UI in your browser
2. Click **Start Meeting**
3. Speak into the microphone (or use `USE_FAKE_AUDIO=true` with a test WAV on a VM)
4. Watch transcript and recommendation cards appear in real-time
5. Type in the **Ask** box to manually trigger a recommendation
6. Click **Stop** when the meeting ends

---

## Option B: Deploy on MacBook (Local)

Two STT options are available on Mac. Use whichever suits your setup.

| | Amazon Transcribe | Whisper (local) |
|---|---|---|
| Accuracy | Excellent, partial results | Very good, final results only |
| Latency | ~1s (streaming) | ~4s (per buffer) |
| Privacy | Audio sent to AWS | Fully on-device |
| Internet | Required | Not required for STT |
| Setup | AWS credentials only | `uv sync --extra whisper` |
| Apple Silicon | — | `WHISPER_DEVICE=mps` (fast) |

### 1. Install Prerequisites

```bash
# Homebrew (if not installed)
/bin/bash -c "$(curl -fsSF https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

brew install git node portaudio awscli
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Open **Docker Desktop** — not needed for the KB (Bedrock KB is serverless), but required if you run any local services.

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

Verify Bedrock access:
```bash
aws bedrock list-foundation-models --region us-east-1 \
  --query 'modelSummaries[?contains(modelId,`cohere.embed`)].modelId' \
  --output text
# Expected: cohere.embed-english-v3
```

### 3. Clone and Configure

```bash
git clone https://github.com/kavap/awssameetingassistant.git
cd awssameetingassistant
cp .env.example .env
```

Set the KB values from Step 0, then choose your STT provider:

**Using Amazon Transcribe (cloud STT):**
```bash
STT_PROVIDER=transcribe
```

**Using Whisper (local, offline STT):**
```bash
STT_PROVIDER=whisper
WHISPER_MODEL=large-v3-turbo
WHISPER_DEVICE=mps        # Apple Silicon GPU — use "cpu" for Intel Mac
WHISPER_COMPUTE_TYPE=int8
```

### 4. Install Python Dependencies

**Transcribe only:**
```bash
uv sync
```

**With Whisper (local STT):**
```bash
uv sync --extra whisper
```

> First run with Whisper will download the `large-v3-turbo` model (~800MB) from HuggingFace. Subsequent starts are instant.

If sounddevice cannot find PortAudio:
```bash
brew install portaudio && uv sync --reinstall-package sounddevice
```

### 5. Seed the Knowledge Base

```bash
uv run python scripts/ingest.py --urls data/urls.txt
```

### 6. Start the Backend

```bash
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### 7. Start the Frontend

```bash
cd frontend && npm install && npm run dev
```

Open **http://localhost:5173**.

### 8. Grant Microphone Permission on macOS

**System Settings → Privacy & Security → Microphone** → enable for Terminal (or iTerm2/Warp).

### 9. Use the Assistant

1. Join a Zoom / Teams / Google Meet call on your Mac
2. Open **http://localhost:5173** and click **Start Meeting**
3. Watch transcript and recommendations appear

**Capture both sides of the call (recommended):**

Install [BlackHole](https://existential.audio/blackhole/) (free virtual audio driver):
```bash
brew install --cask blackhole-2ch
```

In **Audio MIDI Setup** (Applications → Utilities):
1. `+` → **Create Multi-Output Device**
2. Add **BlackHole 2ch** + your speakers/headphones
3. Set as system audio output in System Settings
4. In Zoom/Teams, set microphone input to **BlackHole 2ch**

This routes all meeting audio through BlackHole so the assistant hears every participant.

---

## Adding Custom Knowledge Sources

Edit `data/urls.txt` — any publicly accessible URL works:

```text
# AWS docs and blogs
https://docs.aws.amazon.com/redshift/latest/mgmt/serverless-whatis.html
https://aws.amazon.com/blogs/big-data/top-10-performance-tuning-tips-for-amazon-redshift/
https://repost.aws/knowledge-center/redshift-serverless-pricing

# Internal wiki (if accessible from where you run ingest.py)
https://wiki.internal.company.com/aws-standards
```

Re-run ingestion to upload new content and trigger a KB sync:
```bash
uv run python scripts/ingest.py --urls data/urls.txt
```

To trigger a sync without re-uploading (e.g., after a manual S3 upload):
```bash
uv run python scripts/ingest.py --sync-only
```

---

## Project Structure

```
awssameetingassistant/
├── backend/
│   ├── main.py                      # FastAPI app, WebSocket, REST endpoints
│   ├── config.py                    # All config via .env (pydantic-settings)
│   ├── audio/capture.py             # Mic, fake audio, silence fallback
│   ├── ccm/
│   │   ├── engine.py                # Conversation Context Map (<10ms/call)
│   │   └── models.py                # CCMState, CCMUpdateEvent dataclasses
│   ├── knowledge_base/
│   │   ├── bedrock_kb.py            # Bedrock KB retrieval (bedrock-agent-runtime)
│   │   └── embeddings.py            # Cohere Embed English v3 wrapper (for ingestion)
│   ├── transcription/
│   │   ├── transcribe_stream.py     # Amazon Transcribe Streaming (STT_PROVIDER=transcribe)
│   │   └── whisper_stream.py        # faster-whisper local STT (STT_PROVIDER=whisper)
│   ├── agent/
│   │   └── recommendation_agent.py  # KB retrieve → Haiku rerank → Sonnet synthesis
│   └── websocket/manager.py         # WebSocket broadcast manager
├── scripts/
│   ├── setup_kb.py                  # One-time: create S3 + IAM role + Bedrock KB
│   └── ingest.py                    # Upload docs to S3 + trigger KB sync
├── frontend/src/
│   ├── App.tsx                      # Two-panel layout
│   ├── store/meetingStore.ts        # Zustand state
│   ├── hooks/useWebSocket.ts        # WS with auto-reconnect
│   └── components/                  # TranscriptPanel, RecommendationCard, etc.
├── data/
│   └── urls.txt                     # Knowledge source URLs
├── tests/                           # 15 unit tests (all passing)
├── .env.example                     # All config variables documented
└── docker-compose.yml               # Optional: local services reference
```

---

## Configuration Reference (`.env`)

| Variable | Default | Description |
|---|---|---|
| `AWS_REGION` | `us-east-1` | AWS region for all services |
| `BEDROCK_EMBEDDING_MODEL` | `cohere.embed-english-v3` | Cohere embedding model |
| `BEDROCK_HAIKU_MODEL` | `claude-3-5-haiku-20241022-v1:0` | Fast reranking model |
| `BEDROCK_SONNET_MODEL` | `claude-3-7-sonnet-20250219-v1:0` | Synthesis model |
| `BEDROCK_KB_ID` | *(required)* | Bedrock KB ID from setup_kb.py |
| `BEDROCK_KB_S3_BUCKET` | *(required)* | S3 bucket for KB documents |
| `BEDROCK_KB_DATA_SOURCE_ID` | *(required)* | KB data source ID |
| `BEDROCK_KB_SEARCH_TYPE` | `HYBRID` | `HYBRID` / `SEMANTIC` / `KEYWORD` |
| `STT_PROVIDER` | `transcribe` | `transcribe` or `whisper` |
| `WHISPER_MODEL` | `large-v3-turbo` | Whisper model size |
| `WHISPER_DEVICE` | `cpu` | `cpu` / `cuda` / `mps` (Apple Silicon) |
| `WHISPER_COMPUTE_TYPE` | `int8` | `int8` / `float16` / `float32` |
| `WHISPER_BUFFER_SECONDS` | `4.0` | Audio buffer length per transcription pass |
| `TRANSCRIBE_LANGUAGE` | `en-US` | Language for Amazon Transcribe |
| `USE_FAKE_AUDIO` | `false` | `true` = use WAV file instead of mic |

---

## Running Tests

```bash
# All tests (no AWS calls required — Bedrock KB is mocked)
uv run pytest tests/ -v

# CCM engine unit tests only
uv run pytest tests/test_ccm_engine.py -v

# Bedrock KB client tests (mocked)
uv run pytest tests/test_bedrock_kb.py -v
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `PortAudioError: No Default Input Device` | Set `USE_FAKE_AUDIO=true`, or `brew install portaudio` on Mac |
| `Bedrock: AccessDeniedException` | Check IAM permissions and that Cohere + Claude model access is enabled in Bedrock console |
| `bedrock-agent-runtime: ResourceNotFoundException` | `BEDROCK_KB_ID` is wrong or KB is in a different region |
| No recommendations after speaking | Check KB sync completed in AWS Console; verify `BEDROCK_KB_ID` is set in `.env` |
| `Transcribe: UnrecognizedClientException` | Check `AWS_REGION` and `transcribe:StartStreamTranscription` IAM permission |
| Whisper not found | Run `uv sync --extra whisper` to install faster-whisper |
| Whisper slow on Mac | Set `WHISPER_DEVICE=mps` for Apple Silicon GPU acceleration |
| Whisper model download fails | Check internet connection — model downloads from HuggingFace on first run |
| Frontend not connecting | Confirm backend is running on port 8000 |

---

## Roadmap

- **Phase 2:** Multi-agent parallel search (6 specialized agents: architecture, migration, comparison, code, cost, security), Revision Agent
- **Phase 3:** Speaker diarization UI, system audio capture (BlackHole/VB-Cable auto-config)
- **Phase 4:** Electron desktop overlay (always-on-top), session export (PDF/Markdown)
- **Phase 5:** Configurable `sources.yaml` with scheduled ingestion, GitHub repo and YouTube transcript indexing

---

## License

MIT
