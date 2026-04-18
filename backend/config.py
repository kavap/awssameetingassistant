from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # AWS
    aws_region: str = "us-east-1"

    # Bedrock models
    bedrock_embedding_model: str = "amazon.titan-embed-text-v2:0"
    bedrock_haiku_model: str = "anthropic.claude-3-5-haiku-20241022-v1:0"
    bedrock_sonnet_model: str = "anthropic.claude-3-7-sonnet-20250219-v1:0"

    # Transcribe
    transcribe_region: str = "us-east-1"
    transcribe_language: str = "en-US"

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "aws_kb"

    # Vector
    vector_size: int = 1024

    # Audio
    audio_sample_rate: int = 16000
    audio_chunk_duration_ms: int = 100

    # Backend
    backend_port: int = 8000
    backend_host: str = "0.0.0.0"

    # Development / testing
    use_fake_audio: bool = False
    fake_audio_path: str = "data/test_audio.wav"


settings = Settings()
