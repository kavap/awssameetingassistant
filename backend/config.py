from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # AWS
    aws_region: str = "us-east-1"

    # Bedrock LLM models — cross-region inference profile IDs (us-east-1)
    # To find valid IDs: aws bedrock list-foundation-models --region us-east-1
    #   --query "modelSummaries[?contains(modelId,'claude')].modelId"
    bedrock_haiku_model: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    bedrock_sonnet_model: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

    # Bedrock embedding — Cohere embed v3 (1024 dims)
    bedrock_embedding_model: str = "cohere.embed-english-v3"

    # Bedrock Knowledge Base
    bedrock_kb_id: str = ""                  # set after creating KB in AWS console
    bedrock_kb_data_source_id: str = ""      # set after creating the S3 data source
    bedrock_kb_s3_bucket: str = ""           # S3 bucket for KB document storage
    bedrock_kb_search_type: str = "HYBRID"   # HYBRID | SEMANTIC | KEYWORD
    bedrock_kb_num_results: int = 8

    # Transcribe
    transcribe_region: str = "us-east-1"
    transcribe_language: str = "en-US"

    # STT provider: "transcribe" (default, cloud) or "whisper" (local, Mac-friendly)
    stt_provider: str = "transcribe"

    # Whisper (local STT — used when stt_provider=whisper)
    whisper_model: str = "large-v3-turbo"   # large-v3-turbo | large-v3 | medium | small
    whisper_device: str = "cpu"             # cpu | cuda | mps (Apple Silicon)
    whisper_compute_type: str = "int8"      # int8 | float16 | float32
    whisper_buffer_seconds: float = 4.0     # audio buffer before each transcription pass
    whisper_language: str = "en"

    # Audio
    audio_sample_rate: int = 16000
    audio_chunk_duration_ms: int = 100

    # Backend
    backend_port: int = 8000
    backend_host: str = "0.0.0.0"

    # AgentCore Runtime
    agentcore_runtime_arn: str = ""     # set after: agentcore deploy

    # AgentCore Memory
    agentcore_memory_id: str = ""           # set after: scripts/setup_agentcore.py
    agentcore_memory_strategy_id: str = ""  # set after: scripts/setup_agentcore.py

    # Speaker diarization / participant mapping
    # Comma-separated list of roles shown as checkboxes in the Start Meeting modal.
    default_meeting_roles: str = (
        "AWS Account SA,"
        "AWS Analytics Specialist SA,"
        "AWS ML Specialist SA,"
        "AWS Storage Specialist SA,"
        "AWS Database Specialist SA,"
        "AWS Security Specialist SA,"
        "AWS Account Manager,"
        "AWS TAM,"
        "AWS CSM,"
        "AWS Domain Sales Specialist,"
        "AWS Proserve Architect,"
        "AWS Proserve Engagement Manager,"
        "AWS Service PM,"
        "AWS Service Engineer/Architect,"
        "AWS Data and AI Strategist,"
        "AWS SA Manager / Leader,"
        "Customer CDO/CTO,"
        "Customer VP Engineering,"
        "Customer Director,"
        "Customer Data Engineer,"
        "Customer Data Scientist,"
        "Customer Technical Lead,"
        "Customer Project Manager,"
        "Partner Architect,"
        "Partner Delivery Lead,"
        "Partner Practice Lead"
    )

    # SA steering directives shown as quick-click buttons in the DirectivesBar.
    # Comma-separated. Edit here or override via DEFAULT_DIRECTIVES env var.
    default_directives: str = (
        "Serverless preferred,"
        "Cost-sensitive customer,"
        "Security & compliance first,"
        "Focus on migration path,"
        "Lift & shift approach,"
        "Modernize & re-architect,"
        "Competitive displacement,"
        "GenAI / Bedrock focus,"
        "Multi-region required,"
        "Customer is on Azure,"
        "Customer is on GCP,"
        "Open source preferred,"
        "Data sovereignty / on-prem hybrid,"
        "Prioritize managed services"
    )

    # Development / testing
    use_fake_audio: bool = False
    fake_audio_path: str = "data/test_audio.wav"


settings = Settings()
