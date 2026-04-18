# AWS SA Meeting Intelligence Assistant

A real-time AI assistant that listens to live AWS customer and internal meetings, builds a progressive conversation context map, searches a pre-indexed AWS knowledge base, and proactively surfaces answers, architecture patterns, best practices, blog links, and code samples — all in real-time.

---

## Architecture Overview

```
Microphone / System Audio
         │
         ▼
Amazon Transcribe Streaming  (ultra-low latency STT, partial results)
         │
         ▼
Conversation Context Map Engine  (detects AWS services, open questions, topics)
         │
         ▼
RecommendationAgent
   ├─ Bedrock Titan Embed v2  (query embedding)
   ├─ Qdrant Hybrid Search    (KNN dense + BM25 sparse, RRF fusion)
   ├─ Claude Haiku            (rerank top results)
   └─ Claude Sonnet           (synthesize recommendation card)
         │
         ▼
WebSocket → React Frontend  (live transcript + recommendation cards)
```

**Key design decisions:**
- Knowledge base is populated **offline** — no live web scraping during meetings
- Hybrid search (dense + sparse) delivers results in <200ms
- Multi-source, configurable knowledge ingestion pipeline
- All AWS calls use the instance IAM role or local AWS credentials (no hardcoded secrets)

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | ≥ 3.12 | |
| uv | ≥ 0.11 | [install](https://docs.astral.sh/uv/getting-started/installation/) |
| Node.js | ≥ 18 | For the React frontend |
| Docker | any | For running Qdrant |
| AWS access | — | Bedrock + Transcribe permissions required |

### Required AWS IAM Permissions

Your IAM role/user needs:
```json
{
  "Effect": "Allow",
  "Action": [
    "bedrock:InvokeModel",
    "transcribe:StartStreamTranscription"
  ],
  "Resource": "*"
}
```

### Required Bedrock Model Access

Enable the following models in **Amazon Bedrock → Model access** (us-east-1):
- `amazon.titan-embed-text-v2:0`
- `anthropic.claude-3-5-haiku-20241022-v1:0`
- `anthropic.claude-3-7-sonnet-20250219-v1:0`

---

## Option A: Deploy on AWS (Cloud VM / EC2)

This is the recommended path for a persistent always-on deployment, or when running on a cloud development environment (e.g., AWS Cloud9, SageMaker Studio, EC2).

### 1. Launch an EC2 Instance

Recommended: **t3.medium** or larger, **Amazon Linux 2023** or **Ubuntu 22.04**, in `us-east-1`.

Attach an IAM instance profile with the permissions listed above.

### 2. Install System Dependencies

**Amazon Linux 2023:**
```bash
sudo dnf update -y
sudo dnf install -y git nodejs npm docker
sudo systemctl start docker
sudo usermod -aG docker $USER
newgrp docker

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

**Ubuntu 22.04:**
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git nodejs npm docker.io libportaudio2
sudo systemctl start docker
sudo usermod -aG docker $USER
newgrp docker

curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

### 3. Clone and Configure

```bash
git clone https://github.com/kavap/awssameetingassistant.git
cd awssameetingassistant

cp .env.example .env
# Edit .env if needed — defaults work for us-east-1
# Set USE_FAKE_AUDIO=true if no physical microphone is attached to the VM
```

### 4. Install Python Dependencies

```bash
uv sync
```

### 5. Start Qdrant

```bash
docker run -d --name meeting-assistant-qdrant \
  -p 6333:6333 -p 6334:6334 \
  -v qdrant_storage:/qdrant/storage \
  --restart unless-stopped \
  qdrant/qdrant:latest
```

Wait for it to be healthy:
```bash
curl http://localhost:6333/healthz
# Expected: healthz check passed
```

### 6. Seed the Knowledge Base

This step fetches and indexes AWS documentation into Qdrant. Run once, then re-run to refresh.

```bash
uv run python scripts/ingest.py --urls data/urls.txt
```

Expected output: ~200–400 chunks indexed across 20+ AWS doc pages (takes 3–8 minutes depending on Bedrock rate limits).

To reset and re-index from scratch:
```bash
uv run python scripts/ingest.py --urls data/urls.txt --reset
```

### 7. Start the Backend

```bash
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Verify:
```bash
curl http://localhost:8000/health
# Expected: {"status":"ok","qdrant":true,...}
```

### 8. Start the Frontend

```bash
cd frontend
npm install
npm run dev
```

The UI is now available at **http://localhost:5173** (or the EC2 public IP if you opened port 5173 in the security group).

> **Security note:** For production, put a reverse proxy (nginx) in front and restrict access. Port 5173 should not be publicly open without authentication.

### 9. Use the Assistant

1. Open the UI in your browser
2. Click **Start Meeting**
3. Speak into the microphone (or set `USE_FAKE_AUDIO=true` with a test WAV file)
4. Watch the transcript and recommendation cards appear in real-time
5. Type a question in the **Ask** box to manually trigger a recommendation
6. Click **Stop** when the meeting ends

---

## Option B: Deploy on MacBook (Local)

This option runs everything locally. The only AWS services used are Amazon Bedrock and Amazon Transcribe Streaming — both accessed via your local AWS credentials.

### 1. Install Prerequisites

Using [Homebrew](https://brew.sh):

```bash
# Homebrew (if not installed)
/bin/bash -c "$(curl -fsSF https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Dependencies
brew install git node docker portaudio

# uv package manager
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Open **Docker Desktop** and ensure it is running before proceeding.

### 2. Configure AWS Credentials

The app uses standard AWS credential resolution. Choose one:

**Option 1 — AWS CLI profile (recommended for personal accounts):**
```bash
brew install awscli
aws configure
# Enter: Access Key ID, Secret Access Key, region (us-east-1), output (json)
```

**Option 2 — AWS SSO (for corporate/federated accounts):**
```bash
aws configure sso
aws sso login --profile your-profile-name
export AWS_PROFILE=your-profile-name
```

Verify Bedrock access:
```bash
aws bedrock list-foundation-models --region us-east-1 \
  --query 'modelSummaries[?contains(modelId,`titan-embed`)].modelId' \
  --output text
```

### 3. Clone and Configure

```bash
git clone https://github.com/kavap/awssameetingassistant.git
cd awssameetingassistant

cp .env.example .env
# Defaults work for MacBook with a microphone — no changes needed
# USE_FAKE_AUDIO=false (default) uses your Mac's built-in microphone
```

### 4. Install Python Dependencies

```bash
uv sync
```

If sounddevice cannot find PortAudio:
```bash
brew install portaudio
uv sync --reinstall-package sounddevice
```

### 5. Start Qdrant

```bash
docker run -d --name meeting-assistant-qdrant \
  -p 6333:6333 \
  -v qdrant_storage:/qdrant/storage \
  --restart unless-stopped \
  qdrant/qdrant:latest

curl http://localhost:6333/healthz
# Expected: healthz check passed
```

### 6. Seed the Knowledge Base

```bash
uv run python scripts/ingest.py --urls data/urls.txt
```

### 7. Start the Backend

```bash
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### 8. Start the Frontend

In a new terminal tab:
```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser.

### 9. Grant Microphone Permission on macOS

On first use, macOS will prompt for microphone access. If it doesn't:

1. **System Settings → Privacy & Security → Microphone**
2. Enable access for **Terminal** (or iTerm2, Warp, or whatever terminal you use)

### 10. Use the Assistant

1. Join a Zoom / Teams / Google Meet call on your Mac
2. Open **http://localhost:5173**
3. Click **Start Meeting**
4. The assistant captures audio from your microphone
5. Watch transcript and recommendation cards populate in real-time

**Capture both sides of the call (recommended):**

Install [BlackHole](https://existential.audio/blackhole/) (free virtual audio driver):
```bash
brew install --cask blackhole-2ch
```

Then in **Audio MIDI Setup** (Applications → Utilities):
1. Click `+` → **Create Multi-Output Device**
2. Add: **BlackHole 2ch** + your speakers/headphones
3. Set this Multi-Output Device as your system audio output in System Settings
4. In the meeting app (Zoom/Teams), set the microphone input to **BlackHole 2ch**

This routes the full meeting audio through BlackHole so the assistant hears all participants. Phase 2 will add a dedicated `AUDIO_DEVICE_NAME` config option; for now, use the default mic which captures ambient audio adequately in a quiet room.

---

## Adding Custom Knowledge Sources

Edit `data/urls.txt` — add any publicly accessible URL (AWS docs, AWS blogs, re:Post, partner docs):

```text
# Additional AWS services
https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/best-practices.html
https://aws.amazon.com/blogs/big-data/top-10-performance-tuning-tips-for-amazon-redshift/
https://repost.aws/knowledge-center/redshift-serverless-pricing

# Your internal wiki (if accessible from where you run the assistant)
https://wiki.internal.company.com/aws-standards
```

Re-run ingestion:
```bash
uv run python scripts/ingest.py --urls data/urls.txt
# Reset and re-index everything:
uv run python scripts/ingest.py --urls data/urls.txt --reset
```

---

## Project Structure

```
awssameetingassistant/
├── backend/
│   ├── main.py                    # FastAPI app + WebSocket + REST endpoints
│   ├── config.py                  # All config via .env (pydantic-settings)
│   ├── audio/capture.py           # Mic capture, fake audio, silence fallback
│   ├── ccm/
│   │   ├── engine.py              # Conversation Context Map engine (<10ms/call)
│   │   └── models.py              # CCMState, CCMUpdateEvent dataclasses
│   ├── knowledge_base/
│   │   ├── qdrant_client.py       # Hybrid search (KNN + BM25 RRF fusion)
│   │   └── embeddings.py          # Bedrock Titan Embeddings v2 wrapper
│   ├── transcription/
│   │   └── transcribe_stream.py   # Amazon Transcribe Streaming pipeline
│   ├── agent/
│   │   └── recommendation_agent.py # Haiku rerank → Sonnet synthesis
│   └── websocket/manager.py       # WebSocket broadcast manager
├── scripts/
│   └── ingest.py                  # KB ingestion CLI
├── frontend/
│   └── src/
│       ├── App.tsx                # Two-panel layout (transcript + recommendations)
│       ├── store/meetingStore.ts  # Zustand state
│       ├── hooks/useWebSocket.ts  # WS connection with auto-reconnect
│       └── components/            # TranscriptPanel, RecommendationCard, etc.
├── data/
│   └── urls.txt                   # Knowledge source URLs (edit to add more)
├── tests/                         # 12 unit + integration tests
├── .env.example                   # Environment variable template
└── docker-compose.yml             # Qdrant service definition
```

---

## Configuration Reference (`.env`)

| Variable | Default | Description |
|---|---|---|
| `AWS_REGION` | `us-east-1` | AWS region for all services |
| `BEDROCK_EMBEDDING_MODEL` | `amazon.titan-embed-text-v2:0` | Embedding model ID |
| `BEDROCK_HAIKU_MODEL` | `anthropic.claude-3-5-haiku-20241022-v1:0` | Fast reranking model |
| `BEDROCK_SONNET_MODEL` | `anthropic.claude-3-7-sonnet-20250219-v1:0` | Synthesis model |
| `TRANSCRIBE_LANGUAGE` | `en-US` | Meeting language code |
| `QDRANT_HOST` | `localhost` | Qdrant host |
| `QDRANT_COLLECTION` | `aws_kb` | Vector collection name |
| `USE_FAKE_AUDIO` | `false` | `true` = use WAV file instead of mic |
| `FAKE_AUDIO_PATH` | `data/test_audio.wav` | Path to test WAV file |

---

## Running Tests

```bash
# Unit tests (no AWS or Docker required)
uv run pytest tests/test_ccm_engine.py -v

# Integration tests (requires Qdrant running on localhost:6333)
uv run pytest tests/test_qdrant_client.py -v

# All tests
uv run pytest tests/ -v
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `PortAudioError: No Default Input Device` | Set `USE_FAKE_AUDIO=true` in `.env`, or install PortAudio (`brew install portaudio` on Mac) |
| `Bedrock: AccessDeniedException` | Ensure IAM role has `bedrock:InvokeModel` and model access is enabled in Bedrock console (us-east-1) |
| `Transcribe: UnrecognizedClientException` | Check `AWS_REGION=us-east-1` and `transcribe:StartStreamTranscription` IAM permission |
| Qdrant version warning | Run `docker pull qdrant/qdrant:latest` then recreate the container |
| Frontend not connecting to backend | Confirm backend is on port 8000 and no firewall blocks it |
| No recommendations appearing | Run `scripts/ingest.py` first — an empty KB returns no results |
| Recommendations are slow (>15s) | Normal for first call (JIT compilation); subsequent calls are faster. Check Bedrock throttling in CloudWatch. |

---

## Roadmap

- **Phase 2:** Multi-agent parallel search (6 specialized agents), Revision Agent for progressive refinement
- **Phase 3:** System audio capture (BlackHole/VB-Cable), per-speaker diarization UI, competitor comparison agent
- **Phase 4:** Electron desktop overlay (always-on-top), session export (PDF/Markdown)
- **Phase 5:** Configurable `sources.yaml` with scheduled offline ingestion, GitHub repo and YouTube transcript sources

---

## License

MIT
