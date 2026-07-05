from __future__ import annotations

import argparse
import asyncio
import json
import mimetypes
import shutil
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from src.demo.artifacts import build_summary, load_review_payload
from src.demo.pdf import write_review_pdf
from src.exporters import export_html, export_latex
from src.review_runner import ConfigError, run_literature_review


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = Path(__file__).resolve().parent / "static"
RUNS: dict[str, "RunState"] = {}
TERMINAL_STATUSES = {"completed", "failed"}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass
class RunState:
    run_id: str
    topic: str
    output_dir: Path
    mode: str = "live"
    status: str = "queued"
    error: str = ""
    created_at: str = field(default_factory=_utc_now)
    finished_at: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)
    condition: threading.Condition = field(default_factory=threading.Condition)

    def add_event(self, event: dict[str, Any]) -> None:
        with self.condition:
            self._append_event_locked(event)
            self.condition.notify_all()

    def complete(self, event: dict[str, Any]) -> None:
        with self.condition:
            self.status = "completed"
            self.finished_at = _utc_now()
            self._append_event_locked(event)
            self.condition.notify_all()

    def fail(self, message: str, *, event_type: str = "run_failed", details: Any = None) -> None:
        with self.condition:
            self.status = "failed"
            self.error = message
            self.finished_at = _utc_now()
            self._append_event_locked({"type": event_type, "message": message, "details": details})
            self.condition.notify_all()

    def _append_event_locked(self, event: dict[str, Any]) -> None:
        event = dict(event)
        event.setdefault("ts", _utc_now())
        event["id"] = len(self.events)
        self.events.append(event)


class DemoHandler(BaseHTTPRequestHandler):
    server_version = "LiteratureReviewHarnessDemo/0.1"

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        if path in {"/", "/index.html"}:
            self._serve_file(STATIC_DIR / "index.html")
            return
        if path.startswith("/static/"):
            self._serve_file(STATIC_DIR / path.removeprefix("/static/"))
            return
        if path.startswith("/api/reviews/"):
            self._handle_review_get(path)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/reviews":
            self._create_live_run()
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[demo] {self.address_string()} - {fmt % args}")

    def _handle_review_get(self, path: str) -> None:
        parts = path.strip("/").split("/")
        if len(parts) < 3:
            self.send_error(HTTPStatus.NOT_FOUND, "Missing run id")
            return
        run_id = parts[2]
        state = RUNS.get(run_id)
        if state is None:
            self.send_error(HTTPStatus.NOT_FOUND, "Unknown run id")
            return
        if len(parts) == 4 and parts[3] == "events":
            self._stream_events(state)
            return
        if len(parts) == 5 and parts[3] == "download":
            self._serve_artifact(state, parts[4], attachment=True)
            return
        if len(parts) == 5 and parts[3] == "preview":
            self._serve_artifact(state, parts[4], attachment=False)
            return
        if len(parts) >= 5 and parts[3] == "asset":
            self._serve_run_asset(state, "/".join(parts[4:]))
            return
        if len(parts) == 3:
            payload = load_review_payload(state.run_id, state.output_dir, state.topic, state.status, state.error)
            self._send_json(payload)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def _create_live_run(self) -> None:
        data = self._read_json_body()
        topic = _clean_topic(data.get("topic"))
        if not topic:
            self._send_json({"error": "Topic is required."}, status=HTTPStatus.BAD_REQUEST)
            return
        state = _new_run(topic, mode="live")
        thread = threading.Thread(target=_run_live_review, args=(state,), daemon=True)
        thread.start()
        self._send_json({"run_id": state.run_id, "status": state.status, "events": f"/api/reviews/{state.run_id}/events"})

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("content-length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _stream_events(self, state: RunState) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        index = 0
        try:
            while True:
                with state.condition:
                    while index >= len(state.events) and state.status not in TERMINAL_STATUSES:
                        state.condition.wait(timeout=15)
                        if index >= len(state.events):
                            self.wfile.write(b": ping\n\n")
                            self.wfile.flush()
                    new_events = state.events[index:]
                    index = len(state.events)
                for event in new_events:
                    self.wfile.write(f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8"))
                    self.wfile.flush()
                if state.status in TERMINAL_STATUSES and index >= len(state.events):
                    break
        except (BrokenPipeError, ConnectionResetError):
            return

    def _serve_artifact(self, state: RunState, filename: str, *, attachment: bool) -> None:
        allowed = {
            "survey.md",
            "survey.html",
            "survey.tex",
            "survey.pdf",
            "evidence_pack.json",
            "check_report.json",
            "skill_trace.json",
            "figure_plan.json",
        }
        if filename not in allowed:
            self.send_error(HTTPStatus.NOT_FOUND, "Artifact not found")
            return
        path = state.output_dir / filename
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "Artifact not ready")
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(path.stat().st_size))
        disposition = "attachment" if attachment else "inline"
        self.send_header("Content-Disposition", f'{disposition}; filename="{path.name}"')
        self.end_headers()
        with path.open("rb") as handle:
            shutil.copyfileobj(handle, self.wfile)

    def _serve_run_asset(self, state: RunState, relative_path: str) -> None:
        clean_relative = unquote(relative_path).lstrip("/")
        target = (state.output_dir / clean_relative).resolve()
        root = state.output_dir.resolve()
        if root != target and root not in target.parents:
            self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
            return
        if not target.exists() or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Asset not found")
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(target.stat().st_size))
        self.end_headers()
        with target.open("rb") as handle:
            shutil.copyfileobj(handle, self.wfile)

    def _serve_file(self, path: Path) -> None:
        root = STATIC_DIR.resolve()
        target = path.resolve()
        if root != target and root not in target.parents:
            self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
            return
        if not target.exists() or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(target.stat().st_size))
        self.end_headers()
        with target.open("rb") as handle:
            shutil.copyfileobj(handle, self.wfile)

    def _send_json(self, payload: dict[str, Any], *, status: HTTPStatus = HTTPStatus.OK) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def _new_run(topic: str, *, mode: str) -> RunState:
    run_id = uuid.uuid4().hex[:12]
    output_dir = PROJECT_ROOT / "output" / "demo_runs" / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    state = RunState(run_id=run_id, topic=topic, output_dir=output_dir, mode=mode, status="running")
    RUNS[run_id] = state
    state.add_event({"type": "server_run_created", "mode": mode, "topic": topic, "output_dir": str(output_dir)})
    return state


def _run_live_review(state: RunState) -> None:
    def emit(event: dict[str, Any]) -> None:
        state.add_event(event)

    try:
        asyncio.run(run_literature_review(state.topic, output_dir=state.output_dir, verbose=False, event_sink=emit))
        _finalize_artifacts(state)
    except ConfigError as exc:
        state.fail(
            "Missing required API configuration. Fill .env or use the bundled sample output.",
            event_type="config_error",
            details=exc.errors,
        )
    except Exception as exc:
        state.fail(str(exc))


def _finalize_artifacts(state: RunState) -> None:
    markdown = (state.output_dir / "survey.md").read_text(encoding="utf-8")
    evidence_pack = json.loads((state.output_dir / "evidence_pack.json").read_text(encoding="utf-8"))
    check_report = json.loads((state.output_dir / "check_report.json").read_text(encoding="utf-8"))
    skill_trace_path = state.output_dir / "skill_trace.json"
    skill_trace = json.loads(skill_trace_path.read_text(encoding="utf-8")) if skill_trace_path.exists() else []
    summary = build_summary(markdown, evidence_pack, check_report, skill_trace)
    if not (state.output_dir / "survey.html").exists():
        export_html(state.output_dir / "survey.md", state.output_dir / "survey.html", title=state.topic)
    if not (state.output_dir / "survey.tex").exists():
        export_latex(state.output_dir / "survey.md", state.output_dir / "survey.tex", title=state.topic)
    write_review_pdf(
        markdown=markdown,
        summary=summary,
        check_report=check_report,
        topic=state.topic,
        output_path=state.output_dir / "survey.pdf",
    )
    state.add_event({"type": "pdf_ready", "path": str(state.output_dir / "survey.pdf")})
    state.complete(
        {
            "type": "artifacts_ready",
            "summary": {
                "paper_count": summary["paper_count"],
                "evidence_count": summary["evidence_count"],
                "cited_evidence_count": summary["cited_evidence_count"],
                "citation_status": summary["citation_status"],
            },
        }
    )


def _clean_topic(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().split())[:220]


def run_server(host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), DemoHandler)
    print(f"Literature Review Harness demo: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Literature Review Harness demo server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    run_server(args.host, args.port)


if __name__ == "__main__":
    main()
