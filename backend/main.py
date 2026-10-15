"""A small web application demonstrating a doubly circular participant roulette."""

from __future__ import annotations

import argparse
import json
import logging
import secrets
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


LOGGER = logging.getLogger("circle_draw")
BACKEND_ROOT = Path(__file__).resolve().parent
FRONTEND_ROOT = BACKEND_ROOT.parent / "frontend"
DEFAULT_PARTICIPANTS = (
    "Alex Morgan",
    "Jordan Lee",
    "Taylor Reed",
    "Casey Blake",
    "Riley Quinn",
    "Morgan Hayes",
    "Jamie Park",
    "Avery Lane",
)
MAX_PARTICIPANTS = 32
MAX_HISTORY = 18


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class Participant:
    """A participant and its two links in the circular doubly linked list."""

    participant_id: str
    name: str
    next: Participant | None = None
    previous: Participant | None = None


class ParticipantCircle:
    """A doubly linked ring that supports circular traversal and removal."""

    def __init__(self) -> None:
        self.head: Participant | None = None
        self.size = 0

    def __iter__(self) -> Iterator[Participant]:
        current = self.head
        for _ in range(self.size):
            if current is None:
                raise RuntimeError("The participant circle contains a broken link.")
            yield current
            current = current.next

    def find(self, participant_id: str) -> Participant:
        for participant in self:
            if participant.participant_id == participant_id:
                return participant
        raise ValueError("That participant is no longer in the circle.")

    def add(self, name: str) -> Participant:
        participant = Participant(uuid.uuid4().hex, name)
        if self.head is None:
            participant.next = participant
            participant.previous = participant
            self.head = participant
        else:
            tail = self.head.previous
            if tail is None:
                raise RuntimeError("The participant circle contains a broken link.")
            participant.previous = tail
            participant.next = self.head
            tail.next = participant
            self.head.previous = participant
        self.size += 1
        return participant

    def advance(
        self, start: Participant, steps: int, direction: int
    ) -> tuple[Participant, list[str]]:
        current = start
        path: list[str] = []
        link = "next" if direction == 1 else "previous"
        for _ in range(steps):
            next_participant = getattr(current, link)
            if next_participant is None:
                raise RuntimeError("The participant circle contains a broken link.")
            current = next_participant
            path.append(current.participant_id)
        return current, path

    def remove(self, participant: Participant) -> None:
        if self.size == 0:
            raise ValueError("There are no participants to remove.")
        if self.size == 1:
            self.head = None
        else:
            previous = participant.previous
            following = participant.next
            if previous is None or following is None:
                raise RuntimeError("The participant circle contains a broken link.")
            previous.next = following
            following.previous = previous
            if self.head is participant:
                self.head = following
        participant.next = None
        participant.previous = None
        self.size -= 1

    def to_list(self) -> list[dict[str, str]]:
        return [
            {"id": participant.participant_id, "name": participant.name}
            for participant in self
        ]

    @classmethod
    def from_list(cls, participants: list[dict[str, str]]) -> ParticipantCircle:
        circle = cls()
        for participant in participants:
            node = Participant(
                participant_id=participant["id"], name=participant["name"]
            )
            if circle.head is None:
                node.next = node
                node.previous = node
                circle.head = node
            else:
                tail = circle.head.previous
                if tail is None:
                    raise RuntimeError("The participant circle contains a broken link.")
                node.previous = tail
                node.next = circle.head
                tail.next = node
                circle.head.previous = node
            circle.size += 1
        return circle


class RouletteSession:
    """Coordinates random draws, participant elimination, and checkpoints."""

    def __init__(self) -> None:
        self.rng = secrets.SystemRandom()
        self.checkpoints: list[dict[str, Any]] = []
        self.reset()

    def reset(self, names: tuple[str, ...] | list[str] = DEFAULT_PARTICIPANTS) -> None:
        if not names or len(names) > MAX_PARTICIPANTS:
            raise ValueError(f"Add between 1 and {MAX_PARTICIPANTS} participants.")
        self.circle = ParticipantCircle()
        for name in names:
            self.circle.add(name)
        first_participant = self.circle.head
        if first_participant is None:
            raise RuntimeError("A round must contain at least one participant.")
        self.current_id = first_participant.participant_id
        self.status = "ready"
        self.round_count = 0
        self.last_result: dict[str, Any] | None = None
        self.history: list[dict[str, str]] = []
        self._record("Round reset", f"{self.circle.size} participants are ready.")

    def _record(self, title: str, detail: str) -> None:
        self.history.insert(0, {"title": title, "detail": detail, "time": timestamp()})
        del self.history[MAX_HISTORY:]

    def state(self) -> dict[str, Any]:
        participants = self.circle.to_list()
        return {
            "participants": [
                {**participant, "is_current": participant["id"] == self.current_id}
                for participant in participants
            ],
            "current_id": self.current_id,
            "status": self.status,
            "round_count": self.round_count,
            "last_result": self.last_result,
            "history": self.history,
            "checkpoints": [
                {
                    "id": checkpoint["id"],
                    "name": checkpoint["name"],
                    "created_at": checkpoint["created_at"],
                }
                for checkpoint in self.checkpoints
            ],
        }

    def add_participant(self, name: str) -> dict[str, Any]:
        clean_name = " ".join(name.split())
        if not clean_name or len(clean_name) > 32:
            raise ValueError("Participant names must contain 1 to 32 characters.")
        if self.status == "finished":
            raise ValueError("Reset the round before adding more participants.")
        if self.circle.size >= MAX_PARTICIPANTS:
            raise ValueError(f"A round can have at most {MAX_PARTICIPANTS} participants.")
        if any(p.name.casefold() == clean_name.casefold() for p in self.circle):
            raise ValueError("That participant is already in the circle.")
        participant = self.circle.add(clean_name)
        self._record("Participant joined", f"{clean_name} joined the circle.")
        return {"participant": {"id": participant.participant_id, "name": clean_name}}

    def spin(self, mode: str, direction: str) -> dict[str, Any]:
        if mode not in {"winner", "eliminate"}:
            raise ValueError("Choose either winner or eliminate mode.")
        if direction not in {"random", "clockwise", "counterclockwise"}:
            raise ValueError("Choose a valid direction.")
        if self.status == "finished" or self.circle.size < 2:
            raise ValueError("Reset the round to start another draw.")

        selected_direction = (
            self.rng.choice((1, -1))
            if direction == "random"
            else (1 if direction == "clockwise" else -1)
        )
        max_steps = min(max(self.circle.size * 2, 2), 24)
        steps = self.rng.randint(1, max_steps)
        starting_participant = self.circle.find(self.current_id)
        selected, path = self.circle.advance(starting_participant, steps, selected_direction)
        direction_name = "clockwise" if selected_direction == 1 else "counterclockwise"
        self.round_count += 1

        result = {
            "mode": mode,
            "steps": steps,
            "direction": direction_name,
            "path": path,
            "participant_id": selected.participant_id,
            "participant_name": selected.name,
            "eliminated": mode == "eliminate",
        }
        if mode == "winner":
            self.status = "finished"
            self.last_result = {**result, "title": "The draw winner"}
            self._record("Winner drawn", f"{selected.name} won after {steps} steps.")
        else:
            next_participant = (
                selected.next if selected_direction == 1 else selected.previous
            )
            if next_participant is None:
                raise RuntimeError("The participant circle contains a broken link.")
            self.circle.remove(selected)
            self.current_id = next_participant.participant_id
            self.status = "finished" if self.circle.size == 1 else "ready"
            self.last_result = {**result, "title": "Participant eliminated"}
            self._record("Participant eliminated", f"{selected.name} left the circle.")
            if self.circle.size == 1:
                remaining = self.circle.find(self.current_id)
                self._record("Last one standing", f"{remaining.name} is the champion.")
        result["state"] = self.state()
        return result

    def create_checkpoint(self, name: str) -> dict[str, str]:
        clean_name = " ".join(name.split())
        if not clean_name or len(clean_name) > 48:
            raise ValueError("Checkpoint names must contain 1 to 48 characters.")
        if len(self.checkpoints) >= 12:
            raise ValueError("Delete an old checkpoint before creating another.")
        snapshot = {
            "participants": self.circle.to_list(),
            "current_id": self.current_id,
            "status": self.status,
            "round_count": self.round_count,
            "last_result": self.last_result,
            "history": [entry.copy() for entry in self.history],
        }
        checkpoint = {
            "id": uuid.uuid4().hex,
            "name": clean_name,
            "created_at": timestamp(),
            "snapshot": snapshot,
        }
        self.checkpoints.insert(0, checkpoint)
        self._record("Checkpoint created", f'"{clean_name}" is ready to restore.')
        return {"id": checkpoint["id"], "name": checkpoint["name"]}

    def restore_checkpoint(self, checkpoint_id: str) -> None:
        checkpoint = next(
            (item for item in self.checkpoints if item["id"] == checkpoint_id), None
        )
        if checkpoint is None:
            raise ValueError("That checkpoint no longer exists.")
        snapshot = checkpoint["snapshot"]
        self.circle = ParticipantCircle.from_list(snapshot["participants"])
        self.current_id = snapshot["current_id"]
        self.status = snapshot["status"]
        self.round_count = snapshot["round_count"]
        self.last_result = snapshot["last_result"]
        self.history = [entry.copy() for entry in snapshot["history"]]
        self._record("Checkpoint restored", f'"{checkpoint["name"]}" was restored.')

    def start_new_round(self) -> None:
        names = [participant.name for participant in self.circle]
        self.reset(names if len(names) >= 2 else DEFAULT_PARTICIPANTS)


SESSION = RouletteSession()


class RouletteRequestHandler(SimpleHTTPRequestHandler):
    server_version = "CircleDraw/1.0"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(FRONTEND_ROOT), **kwargs)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/state":
            self._send_json(200, SESSION.state())
            return
        if path.startswith("/api/"):
            self._send_json(404, {"error": "API endpoint not found."})
            return
        if path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
            if path == "/api/participants":
                result = SESSION.add_participant(self._required_string(payload, "name"))
                self._send_json(201, {**result, "state": SESSION.state()})
            elif path == "/api/spin":
                result = SESSION.spin(
                    self._required_string(payload, "mode"),
                    self._required_string(payload, "direction"),
                )
                self._send_json(200, result)
            elif path == "/api/checkpoints":
                result = SESSION.create_checkpoint(
                    self._required_string(payload, "name")
                )
                self._send_json(201, {**result, "state": SESSION.state()})
            elif path == "/api/checkpoints/restore":
                SESSION.restore_checkpoint(
                    self._required_string(payload, "checkpoint_id")
                )
                self._send_json(200, {"state": SESSION.state()})
            elif path == "/api/reset":
                SESSION.reset()
                self._send_json(200, {"state": SESSION.state()})
            elif path == "/api/new-round":
                SESSION.start_new_round()
                self._send_json(200, {"state": SESSION.state()})
            else:
                self._send_json(404, {"error": "API endpoint not found."})
        except (ValueError, json.JSONDecodeError) as error:
            self._send_json(400, {"error": str(error)})
        except (BrokenPipeError, ConnectionResetError):
            LOGGER.info("Client disconnected while receiving a response.")
        except Exception:
            LOGGER.exception("Unexpected request failure for %s", path)
            self._send_json(500, {"error": "The server could not complete that request."})

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("Invalid request body length.") from error
        if length < 1 or length > 32_768:
            raise ValueError("Request bodies must be between 1 and 32,768 bytes.")
        try:
            payload = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Request body must contain valid JSON.") from error
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        return payload

    @staticmethod
    def _required_string(payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str):
            raise ValueError(f'"{key}" must be a string.')
        return value

    def _send_json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format_string: str, *args: Any) -> None:
        LOGGER.info("%s - %s", self.address_string(), format_string % args)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Circle Draw web application.")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to serve on (default: 8000)")
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = ThreadingHTTPServer((arguments.host, arguments.port), RouletteRequestHandler)
    print(f"Circle Draw is running at http://{arguments.host}:{arguments.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Circle Draw.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()