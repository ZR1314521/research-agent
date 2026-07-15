from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv(path: Path) -> dict[str, str]:
    """Read the project .env without letting stale shell variables override it."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        values[key] = value
    return values


def _value(values: dict[str, str], key: str, default: str = "") -> str:
    return values.get(key, default).strip()


@dataclass(frozen=True)
class AgentConfig:
    root_dir: Path
    runs_dir: Path
    scripts_dir: Path
    rules_dir: Path
    skills_dir: Path
    knowledge_dir: Path
    llm_provider: str
    llm_protocol: str
    llm_model: str
    llm_base_url: str
    llm_api_key: str
    llm_timeout_seconds: int
    llm_max_tokens: int
    llm_retry: int
    provider_max_concurrency: int
    context_window: int
    context_budget: int
    context_observation_budget: int
    context_output_reserve: int
    semantic_scholar_api_key: str
    openalex_mailto: str
    pubmed_email: str
    pubmed_api_key: str
    agent_emergency_turn_limit: int

    @classmethod
    def load(cls, root_dir: Path | None = None) -> "AgentConfig":
        root = (root_dir or ROOT).resolve()
        values = _load_dotenv(root / ".env")
        return cls(
            root_dir=root,
            runs_dir=root / "runs",
            scripts_dir=root / "scripts",
            rules_dir=root / "rules",
            skills_dir=root / "skills",
            knowledge_dir=root / "knowledge",
            llm_provider=_value(values, "RESEARCH_AGENT_LLM_PROVIDER"),
            llm_protocol=_value(values, "RESEARCH_AGENT_LLM_PROTOCOL", "openai-compatible"),
            llm_model=_value(values, "RESEARCH_AGENT_LLM_MODEL"),
            llm_base_url=_value(values, "RESEARCH_AGENT_LLM_BASE_URL"),
            llm_api_key=_value(values, "RESEARCH_AGENT_LLM_API_KEY"),
            llm_timeout_seconds=max(5, int(_value(values, "RESEARCH_AGENT_LLM_TIMEOUT", "120"))),
            # Zero omits max_tokens so the provider/model applies its native limit.
            llm_max_tokens=max(0, int(_value(values, "RESEARCH_AGENT_LLM_MAX_TOKENS", "0"))),
            llm_retry=max(0, min(5, int(_value(values, "RESEARCH_AGENT_LLM_RETRY", "0")))),
            provider_max_concurrency=max(
                1, int(_value(values, "RESEARCH_AGENT_PROVIDER_MAX_CONCURRENCY", "1"))
            ),
            context_window=max(0, int(_value(values, "RESEARCH_AGENT_CONTEXT_WINDOW", "0"))),
            context_budget=max(0, int(_value(values, "RESEARCH_AGENT_CONTEXT_BUDGET", "32000"))),
            context_observation_budget=max(
                256,
                int(_value(values, "RESEARCH_AGENT_CONTEXT_OBSERVATION_BUDGET", "4000")),
            ),
            context_output_reserve=max(
                0,
                int(_value(values, "RESEARCH_AGENT_CONTEXT_OUTPUT_RESERVE", "8000")),
            ),
            semantic_scholar_api_key=_value(values, "SEMANTIC_SCHOLAR_API_KEY"),
            openalex_mailto=_value(values, "OPENALEX_MAILTO"),
            pubmed_email=_value(values, "PUBMED_EMAIL"),
            pubmed_api_key=_value(values, "PUBMED_API_KEY"),
            agent_emergency_turn_limit=max(
                0,
                int(_value(
                    values,
                    "RESEARCH_AGENT_EMERGENCY_TURN_LIMIT",
                    _value(values, "RESEARCH_AGENT_MAX_STEPS", "50"),
                )),
            ),
        )

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_provider and self.llm_model and self.llm_base_url and self.llm_api_key)
