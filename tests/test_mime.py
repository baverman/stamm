from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from stamm.config import Config, MimeRule
from stamm.mime import MimeManager, _OpenProcess


class MimeOpenerTests(unittest.TestCase):
    def config(self, rules: tuple[MimeRule, ...] = ()) -> Config:
        return Config(
            root=Path("/tmp"), spool=Path("/tmp/inbox"), sent=Path("/tmp/sent"),
            drafts=Path("/tmp/drafts"), editor="true", sendmail="true",
            identities=("sender@example.com",), mime=rules,
        )

    def test_unknown_mime_type_uses_xdg_open(self) -> None:
        manager = MimeManager(self.config())
        self.assertEqual(manager.opener_command("application/pdf"), "xdg-open {file}")

    def test_configured_opener_takes_priority(self) -> None:
        manager = MimeManager(self.config((MimeRule("application/pdf", open="custom {file}"),)))
        self.assertEqual(manager.opener_command("application/pdf"), "custom {file}")

    def test_one_out_file_captures_stdout_and_stderr(self) -> None:
        manager = MimeManager(self.config())
        directory = tempfile.TemporaryDirectory(prefix="stamm-test-open-")
        output = Path(directory.name) / "out"
        with output.open("wb") as out:
            process = manager._run(
                "printf stdout; printf stderr >&2; exit 7",
                b"",
                detached=True,
                output=out,
            )
        self.assertIsInstance(process, subprocess.Popen)
        process.wait(timeout=5)
        manager._temporary.append(_OpenProcess(directory, process, output, "test opener"))

        errors = manager.reap()

        self.assertEqual(len(errors), 1)
        self.assertIn("exit status: 7", errors[0])
        self.assertIn("output:\nstdoutstderr", errors[0])
        self.assertFalse(Path(directory.name).exists())


if __name__ == "__main__":
    unittest.main()
