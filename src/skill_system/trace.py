from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class SkillTraceEvent:
    phase: str
    action: str
    skill_names: list[str] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)
    reason: str = ""
    injected_chars: int = 0
    resources: list[str] = field(default_factory=list)
    scripts: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    ts: str = field(default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z"))


class SkillTraceRecorder:
    """Records skill-system behavior for audit and presentation."""

    def __init__(self, output_path: Path):
        self.output_path = output_path
        self.events: list[SkillTraceEvent] = []

    def record(
        self,
        *,
        phase: str,
        action: str,
        skill_names: list[str] | None = None,
        roles: list[str] | None = None,
        reason: str = "",
        injected_chars: int = 0,
        resources: list[str] | None = None,
        scripts: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.events.append(
            SkillTraceEvent(
                phase=phase,
                action=action,
                skill_names=skill_names or [],
                roles=roles or [],
                reason=reason,
                injected_chars=injected_chars,
                resources=resources or [],
                scripts=scripts or [],
                metadata=metadata or {},
            )
        )

    def save(self) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(
            json.dumps([asdict(event) for event in self.events], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
