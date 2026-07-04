from __future__ import annotations

import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PHASE_ROLES: dict[str, list[str]] = {
    "literature_review": ["research_framing", "survey_writing", "citation_grounding"],
    "retrieve": ["academic_search"],
    "write": ["research_framing", "survey_writing"],
    "verify": ["citation_grounding"],
    "export": ["latex_arxiv_export"],
}


@dataclass(frozen=True)
class SkillMetadata:
    name: str
    description: str
    path: Path
    roles: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    source: str = "builtin"
    enabled: bool = True
    max_chars: int = 6000
    allow_scripts: bool = False


@dataclass(frozen=True)
class LoadedSkill:
    name: str
    path: Path
    content: str
    metadata: SkillMetadata
    loaded_resources: list[str] = field(default_factory=list)


@dataclass
class SkillContext:
    phase: str
    active: list[LoadedSkill] = field(default_factory=list)

    @property
    def names(self) -> list[str]:
        return [skill.name for skill in self.active]

    def render(self) -> str:
        parts = []
        for skill in self.active:
            parts.append(
                f"<!-- loaded-skill name:{skill.name} source:{skill.metadata.source} path:{skill.path} -->\n"
                + skill.content.strip()
            )
        return "\n\n".join(parts)


class SkillManager:
    """Progressive-disclosure loader for markdown skills.

    Discovery reads only metadata. Full skill instructions are loaded only for
    the current phase and can be unloaded immediately afterward.
    """

    def __init__(self, skill_dir: Path, external_config: Path | None = None):
        self.skill_dir = skill_dir
        self.external_config = external_config
        self._skills = self._discover()
        self._active = SkillContext(phase="none")

    def list(self) -> list[SkillMetadata]:
        return sorted(self._skills.values(), key=lambda item: (item.source, item.name))

    def select(self, phase: str, extra_roles: list[str] | None = None) -> list[SkillMetadata]:
        roles = list(PHASE_ROLES.get(phase, []))
        if extra_roles:
            roles.extend(extra_roles)
        if not roles:
            return []
        return self._filter_by_roles(self.list(), roles)

    def load(self, name: str) -> LoadedSkill:
        if name not in self._skills:
            raise FileNotFoundError(f"Skill not found: {name}")
        meta = self._skills[name]
        body, resources = self._read_skill_with_static_resources(meta)
        content = body[: meta.max_chars]
        if len(body) > meta.max_chars:
            content += "\n\n<!-- skill content truncated by max_chars policy -->"
        return LoadedSkill(name=meta.name, path=meta.path, content=content, metadata=meta, loaded_resources=resources)

    def load_names(self, names: list[str], phase: str = "manual") -> SkillContext:
        self._active = SkillContext(phase=phase, active=[self.load(name) for name in names])
        return self._active

    def load_for_phase(self, phase: str, extra_roles: list[str] | None = None) -> SkillContext:
        selected = self.select(phase, extra_roles=extra_roles)
        return self.load_names([meta.name for meta in selected], phase=phase)

    def unload(self) -> list[str]:
        before = self._active.names
        self._active = SkillContext(phase="none")
        return before

    @property
    def active_names(self) -> list[str]:
        return self._active.names

    def resource_index(self, name: str) -> list[dict[str, object]]:
        meta = self._require(name)
        root = meta.path.parent
        resources: list[dict[str, object]] = []
        for folder in ["references", "templates", "assets", "static", "config", "scripts"]:
            base = root / folder
            if not base.exists():
                continue
            for path in sorted(item for item in base.rglob("*") if item.is_file()):
                resources.append(
                    {
                        "path": str(path.relative_to(root)),
                        "kind": folder,
                        "size": path.stat().st_size,
                        "executable": folder == "scripts" and path.suffix in {".py", ".sh", ".js", ".mjs"},
                    }
                )
        manifest = root / "manifest.yaml"
        if manifest.exists():
            resources.insert(0, {"path": "manifest.yaml", "kind": "manifest", "size": manifest.stat().st_size, "executable": False})
        return resources

    def read_resource(self, name: str, relative_path: str, max_chars: int = 12000) -> str:
        meta = self._require(name)
        path = _safe_child(meta.path.parent, relative_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Skill resource not found: {name}:{relative_path}")
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > max_chars:
            return text[:max_chars] + "\n\n<!-- skill resource truncated by max_chars policy -->"
        return text

    def run_script(
        self,
        name: str,
        relative_path: str,
        args: list[str] | None = None,
        timeout_seconds: int = 60,
    ) -> dict[str, object]:
        meta = self._require(name)
        if not meta.allow_scripts:
            raise PermissionError(f"Scripts are disabled for skill: {name}")
        script = _safe_child(meta.path.parent, relative_path)
        if not script.exists() or not script.is_file():
            raise FileNotFoundError(f"Skill script not found: {name}:{relative_path}")
        skill_root = meta.path.parent.resolve()
        if "scripts" not in script.relative_to(skill_root).parts:
            raise PermissionError(f"Refusing to run non-scripts resource: {relative_path}")
        proc = subprocess.run(
            _script_command(script, args or []),
            cwd=str(script.parent),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return {"skill": name, "script": relative_path, "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}

    def _discover(self) -> dict[str, SkillMetadata]:
        skills: dict[str, SkillMetadata] = {}
        if self.skill_dir.exists():
            for path in sorted(self.skill_dir.iterdir()):
                skill_path = _skill_file(path)
                if not skill_path:
                    continue
                meta = _metadata_from_file(skill_path, source="builtin")
                skills[meta.name] = meta
        for meta in self._discover_external():
            skills.setdefault(meta.name, meta)
        return skills

    def _discover_external(self) -> list[SkillMetadata]:
        if not self.external_config or not self.external_config.exists():
            return []
        with self.external_config.open("rb") as f:
            data = tomllib.load(f)
        result: list[SkillMetadata] = []
        for item in data.get("skills", []):
            if not item.get("enabled", True):
                continue
            raw_path = Path(str(item.get("path", ""))).expanduser()
            path = raw_path if raw_path.is_absolute() else (self.external_config.parent.parent / raw_path)
            skill_path = _skill_file(path)
            if not skill_path:
                continue
            meta = _metadata_from_file(skill_path, source="external")
            result.append(
                SkillMetadata(
                    name=str(item.get("name") or meta.name),
                    description=str(item.get("description") or meta.description),
                    path=skill_path,
                    roles=_as_list(item.get("roles") or item.get("role") or meta.roles),
                    triggers=_as_list(item.get("triggers") or meta.triggers),
                    source="external",
                    enabled=bool(item.get("enabled", True)),
                    max_chars=int(item.get("max_chars", meta.max_chars)),
                    allow_scripts=bool(item.get("allow_scripts", meta.allow_scripts)),
                )
            )
        return result

    def _filter_by_roles(self, metas: list[SkillMetadata], roles: list[str] | None) -> list[SkillMetadata]:
        if not roles:
            return [meta for meta in metas if meta.enabled]
        wanted = {_normalize_role(role) for role in roles}
        return [meta for meta in metas if meta.enabled and ({_normalize_role(role) for role in meta.roles} & wanted)]

    def _require(self, name: str) -> SkillMetadata:
        if name not in self._skills:
            raise FileNotFoundError(f"Skill not found: {name}")
        return self._skills[name]

    def _read_skill_with_static_resources(self, meta: SkillMetadata) -> tuple[str, list[str]]:
        root = meta.path.parent
        body = _read_skill_body(meta.path)
        resources: list[str] = []
        manifest = root / "manifest.yaml"
        if manifest.exists():
            manifest_text = manifest.read_text(encoding="utf-8", errors="replace")
            body += "\n\n## Skill Manifest\n\n```yaml\n" + manifest_text[:4000] + "\n```"
            resources.append("manifest.yaml")
            for rel in _manifest_always_load(manifest_text):
                path = _safe_child(root, rel)
                if path.exists() and path.is_file():
                    body += f"\n\n## Skill Resource: {rel}\n\n" + path.read_text(encoding="utf-8", errors="replace")[:4000]
                    resources.append(rel)
        return body, resources


def _skill_file(path: Path) -> Path | None:
    if path.is_file() and path.suffix == ".md":
        return path
    if path.is_dir():
        for name in ["SKILL.md", "skill.md"]:
            candidate = path / name
            if candidate.exists():
                return candidate
    return None


def _metadata_from_file(path: Path, source: str) -> SkillMetadata:
    text = path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(text)
    title = _first_heading(body) or path.stem
    name = str(frontmatter.get("name") or _slug(path.parent.name if path.name.lower() == "skill.md" else path.stem))
    return SkillMetadata(
        name=name,
        description=str(frontmatter.get("description") or _first_paragraph(body) or title),
        path=path,
        roles=_as_list(frontmatter.get("roles") or frontmatter.get("role") or _infer_role(name)),
        triggers=_as_list(frontmatter.get("triggers")),
        source=source,
        max_chars=int(frontmatter.get("max_chars") or 6000),
        allow_scripts=str(frontmatter.get("allow_scripts") or "false").lower() in {"1", "true", "yes", "on"},
    )


def _read_skill_body(path: Path) -> str:
    _, body = _split_frontmatter(path.read_text(encoding="utf-8"))
    return body.strip()


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = None
    for idx, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = idx
            break
    if end is None:
        return {}, text
    return _parse_simple_yaml(lines[1:end]), "\n".join(lines[end + 1 :])


def _parse_simple_yaml(lines: list[str]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_key: str | None = None
    for raw in lines:
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("  - ") and current_key:
            data.setdefault(current_key, []).append(_strip_quotes(line[4:].strip()))
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        current_key = key
        if not value:
            data[key] = []
        elif value.startswith("[") and value.endswith("]"):
            data[key] = [_strip_quotes(item.strip()) for item in value[1:-1].split(",") if item.strip()]
        else:
            data[key] = _strip_quotes(value)
    return data


def _strip_quotes(value: str) -> str:
    return value.strip().strip('"').strip("'")


def _as_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    return [str(value)]


def _infer_role(name: str) -> list[str]:
    normalized = _normalize_role(name)
    for role in ["research_framing", "survey_writing", "citation_grounding", "latex_arxiv_export", "academic_polishing", "academic_search"]:
        if role in normalized:
            return [role]
    return ["general"]


def _normalize_role(value: str) -> str:
    return value.lower().replace("-", "_").replace(" ", "_")


def _slug(value: str) -> str:
    return value.lower().replace("_", "-").replace(" ", "-")


def _first_heading(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _first_paragraph(text: str) -> str:
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            if lines:
                break
            continue
        lines.append(line)
        if len(" ".join(lines)) > 240:
            break
    return " ".join(lines)[:500]


def _manifest_always_load(text: str) -> list[str]:
    result: list[str] = []
    in_always = False
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if stripped == "always_load:":
            in_always = True
            continue
        if in_always:
            if stripped.startswith("- "):
                result.append(_strip_quotes(stripped[2:].strip()))
                continue
            if stripped and not line.startswith(" "):
                break
    return result


def _safe_child(root: Path, relative_path: str) -> Path:
    root = root.resolve()
    path = (root / relative_path).resolve()
    if root != path and root not in path.parents:
        raise PermissionError(f"Path escapes skill root: {relative_path}")
    return path


def _script_command(script: Path, args: list[str]) -> list[str]:
    suffix = script.suffix.lower()
    if suffix == ".py":
        return ["python3", str(script), *args]
    if suffix == ".sh":
        return ["bash", str(script), *args]
    if suffix in {".js", ".mjs"}:
        return ["node", str(script), *args]
    return [str(script), *args]
