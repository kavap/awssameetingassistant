from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # AWS
    aws_region: str = "us-east-1"

    # Bedrock LLM models
    bedrock_haiku_model: str = "anthropic.claude-haiku-4-5-20251001-v1:0"
    bedrock_sonnet_model: str = "anthropic.claude-sonnet-4-6-20250514-v1:0"

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

    # Development / testing
    use_fake_audio: bool = False
    fake_audio_path: str = "data/test_audio.wav"


settings = Settings()
