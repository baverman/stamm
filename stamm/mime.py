"""MIME filtering, opening, tree display, and saving."""

from __future__ import annotations

from dataclasses import dataclass
from email.message import Message
import mimetypes
from pathlib import Path
import shlex
import subprocess
import tempfile
from typing import BinaryIO

from .config import Config, MimeRule
from .message import payload_bytes, payload_text


@dataclass(frozen=True)
class PartRow:
    part: Message
    depth: int
    label: str


@dataclass(frozen=True)
class _OpenProcess:
    directory: tempfile.TemporaryDirectory[str]
    process: subprocess.Popen[bytes]
    output: Path
    command: str


def part_rows(message: Message) -> list[PartRow]:
    rows: list[PartRow] = []
    def walk(part: Message, depth: int) -> None:
        name = part.get_filename()
        size = len(payload_bytes(part)) if not part.is_multipart() else 0
        label = part.get_content_type() + (f"  {name}" if name else "") + (f"  {size} bytes" if size else "")
        rows.append(PartRow(part, depth, label))
        if part.is_multipart():
            for child in part.iter_parts():  # type: ignore[attr-defined]
                walk(child, depth + 1)
    walk(message, 0)
    return rows


class MimeManager:
    def __init__(self, config: Config):
        self.config = config
        self._temporary: list[_OpenProcess] = []

    def rule(self, content_type: str) -> MimeRule | None:
        return next((rule for rule in self.config.mime if rule.matches(content_type)), None)

    def opener_command(self, content_type: str) -> str:
        rule = self.rule(content_type)
        if rule is None:
            return "xdg-open {file}"
        if not rule.open:
            raise ValueError(f"no opener for {content_type}")
        return rule.open

    @staticmethod
    def _run(
        command: str,
        content: bytes,
        temporary: Path | None = None,
        *,
        detached: bool = False,
        output: BinaryIO | None = None,
    ) -> subprocess.Popen[bytes] | subprocess.CompletedProcess[bytes]:
        if "{file}" in command:
            if temporary is None:
                raise ValueError("command requires a file")
            rendered = command.replace("{file}", shlex.quote(str(temporary)))
            stdin = subprocess.DEVNULL
        else:
            rendered, stdin = command, subprocess.PIPE
        if detached:
            input_file = None
            if stdin == subprocess.PIPE:
                input_file = tempfile.TemporaryFile()
                input_file.write(content)
                input_file.seek(0)
                stdin = input_file
            try:
                return subprocess.Popen(
                    rendered,
                    shell=True,
                    stdin=stdin,
                    stdout=output if output is not None else subprocess.DEVNULL,
                    stderr=output if output is not None else subprocess.DEVNULL,
                    start_new_session=True,
                )
            finally:
                if input_file is not None:
                    input_file.close()
        return subprocess.run(rendered, shell=True, input=content if stdin == subprocess.PIPE else None, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

    def display(self, part: Message) -> str:
        content_type = part.get_content_type()
        rule = self.rule(content_type)
        if content_type == "text/plain":
            return payload_text(part)
        if not rule or not rule.display:
            raise ValueError(f"no display filter for {content_type}")
        content = payload_bytes(part)
        with tempfile.TemporaryDirectory(prefix="stamm-view-") as directory:
            path = Path(directory) / safe_filename(part)
            path.write_bytes(content)
            result = self._run(rule.display, content, path)
            assert isinstance(result, subprocess.CompletedProcess)
            return result.stdout.decode("utf-8", errors="replace")

    def open(self, part: Message) -> None:
        command = self.opener_command(part.get_content_type())
        directory = tempfile.TemporaryDirectory(prefix="stamm-open-")
        path = Path(directory.name) / safe_filename(part)
        output = Path(directory.name) / "out"
        content = payload_bytes(part)
        path.write_bytes(content)
        with output.open("wb") as out:
            process = self._run(command, content, path, detached=True, output=out)
        assert isinstance(process, subprocess.Popen)
        self._temporary.append(_OpenProcess(directory, process, output, command))

    def reap(self) -> list[str]:
        active: list[_OpenProcess] = []
        errors: list[str] = []
        for entry in self._temporary:
            status = entry.process.poll()
            if status is None:
                active.append(entry)
                continue
            if status:
                try:
                    output = entry.output.read_text(encoding="utf-8", errors="replace").strip()
                except OSError as exc:
                    output = f"[cannot read opener output: {exc}]"
                errors.append(
                    f"command: {entry.command}\n"
                    f"exit status: {status}\n"
                    f"output:\n{output or '[empty]'}"
                )
            entry.directory.cleanup()
        self._temporary = active
        return errors

    def close(self) -> None:
        for entry in self._temporary:
            entry.directory.cleanup()
        self._temporary.clear()


def safe_filename(part: Message) -> str:
    name = part.get_filename()
    if name:
        name = Path(name).name
    if not name or name in (".", ".."):
        extension = mimetypes.guess_extension(part.get_content_type()) or ".bin"
        name = "part" + extension
    return name


def save_part(part: Message, destination: Path) -> Path:
    if destination.is_dir():
        destination /= safe_filename(part)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload_bytes(part))
    return destination
