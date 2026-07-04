import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    intern_api_base: str = ""
    intern_api_key: str = ""
    sciverse_api_token: str = ""
    mineru_api_token: str = ""
    mineru_enabled: bool = True
    mineru_timeout: int = 600
    mineru_batch_size: int = 1
    mineru_fast: bool = True
    max_iterations: int = 15
    model: str = "intern-s2-preview"

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            intern_api_base=os.getenv("INTERN_API_BASE", "https://chat.intern-ai.org.cn/api/v1"),
            intern_api_key=os.getenv("INTERN_API_KEY", ""),
            sciverse_api_token=os.getenv("SCIVERSE_API_TOKEN", ""),
            mineru_api_token=os.getenv("MINERU_API_TOKEN", os.getenv("MINERU_API_KEY", "")),
            mineru_enabled=os.getenv("MINERU_ENABLED", "true").lower() in {"1", "true", "yes"},
            mineru_timeout=int(os.getenv("MINERU_TIMEOUT", "600")),
            mineru_batch_size=int(os.getenv("MINERU_BATCH_SIZE", "1")),
            mineru_fast=os.getenv("MINERU_FAST", "true").lower() in {"1", "true", "yes"},
            max_iterations=int(os.getenv("MAX_ITERATIONS", "15")),
            model=os.getenv("MODEL", "intern-latest"),
        )

    def validate(self) -> list[str]:
        errors = []
        if not self.intern_api_key:
            errors.append("INTERN_API_KEY is required")
        if not self.sciverse_api_token:
            errors.append("SCIVERSE_API_TOKEN is required")
        return errors
