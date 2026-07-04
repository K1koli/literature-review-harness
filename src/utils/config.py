import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv() -> None:
        return None

load_dotenv()


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_toml() -> dict:
    path = PROJECT_ROOT / "configs" / "config.toml"
    if not path.exists():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def _cfg(config: dict, section: str, key: str, default: str = "") -> str:
    value = config.get(section, {}).get(key, default)
    return "" if value is None else str(value)


def _secret(value_or_env: str, default_env: str) -> str:
    value_or_env = (value_or_env or "").strip()
    if value_or_env and value_or_env in os.environ:
        return os.environ.get(value_or_env, "")
    env_value = os.environ.get(default_env, "")
    if env_value:
        return env_value
    if value_or_env and value_or_env != default_env:
        return value_or_env
    return ""


def _value(value_or_env: str, default_env: str, default_value: str = "") -> str:
    value_or_env = (value_or_env or "").strip()
    if value_or_env and value_or_env in os.environ:
        return os.environ.get(value_or_env, default_value)
    env_value = os.environ.get(default_env)
    if env_value is not None:
        return env_value
    if value_or_env and value_or_env != default_env:
        return value_or_env
    return default_value


def _chat_base_url(url: str) -> str:
    clean = (url or "").rstrip("/")
    suffix = "/chat/completions"
    if clean.endswith(suffix):
        clean = clean[: -len(suffix)]
    return clean


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
        file_cfg = _load_toml()
        runtime_cfg = file_cfg.get("runtime", {})
        skip_mineru = str(runtime_cfg.get("skip_mineru", "false")).lower() in {"1", "true", "yes"}
        mineru_enabled_default = "false" if skip_mineru else "true"
        intern_base = _chat_base_url(
            _value(
                _cfg(file_cfg, "llm", "base_url_env", "INTERN_API_BASE"),
                "INTERN_API_BASE",
                "https://chat.intern-ai.org.cn/api/v1",
            )
        )
        return cls(
            intern_api_base=intern_base,
            intern_api_key=_secret(_cfg(file_cfg, "llm", "api_key_env", "INTERN_API_KEY"), "INTERN_API_KEY") or os.getenv("API_KEY", ""),
            sciverse_api_token=_secret(_cfg(file_cfg, "sciverse", "token_env", "SCIVERSE_API_TOKEN"), "SCIVERSE_API_TOKEN") or os.getenv("SCIVERSE_API_KEY", ""),
            mineru_api_token=_secret(_cfg(file_cfg, "mineru", "token_env", "MINERU_API_TOKEN"), "MINERU_API_TOKEN") or os.getenv("MINERU_API_KEY", ""),
            mineru_enabled=os.getenv("MINERU_ENABLED", mineru_enabled_default).lower() in {"1", "true", "yes"},
            mineru_timeout=int(os.getenv("MINERU_TIMEOUT", str(runtime_cfg.get("timeout_seconds", "600")))),
            mineru_batch_size=int(os.getenv("MINERU_BATCH_SIZE", "1")),
            mineru_fast=os.getenv("MINERU_FAST", "true").lower() in {"1", "true", "yes"},
            max_iterations=int(os.getenv("MAX_ITERATIONS", "15")),
            model=os.getenv("MODEL", _cfg(file_cfg, "llm", "model", "intern-s2-preview")),
        )

    def validate(self) -> list[str]:
        errors = []
        if not self.intern_api_key:
            errors.append("INTERN_API_KEY is required")
        if not self.sciverse_api_token:
            errors.append("SCIVERSE_API_TOKEN is required")
        return errors
