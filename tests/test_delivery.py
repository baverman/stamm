from __future__ import annotations

from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from stamm.compose import ComposeData
from stamm.config import Config
from stamm.delivery import DeliveryError, envelope, send


class DeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = Config(
            root=Path("/tmp"), spool=Path("/tmp/inbox"), sent=Path("/tmp/sent"),
            drafts=Path("/tmp/drafts"), trash=Path("/tmp/trash"), editor="true", sendmail="sendmail --mode test",
            identities=("Sender <sender@example.com>",),
        )

    def test_envelope_collects_and_deduplicates_all_recipient_fields(self) -> None:
        data = ComposeData(
            sender="Sender <sender@example.com>",
            to="One <one@example.com>, duplicate@example.com",
            cc="duplicate@example.com",
            bcc="two@example.com",
        )
        self.assertEqual(
            envelope(data),
            ("sender@example.com", ["one@example.com", "duplicate@example.com", "two@example.com"]),
        )

    def test_envelope_rejects_an_empty_recipient_list(self) -> None:
        with self.assertRaisesRegex(DeliveryError, "no envelope recipients"):
            envelope(ComposeData(sender="sender@example.com"))

    @patch("stamm.delivery.store", return_value=Path("/tmp/sent/message"))
    @patch("stamm.delivery.subprocess.run")
    def test_send_passes_sender_and_recipients_as_separate_arguments(self, run, _store) -> None:
        run.return_value = subprocess.CompletedProcess([], 0, b"", b"")
        data = ComposeData(
            sender="Sender <sender@example.com>",
            to="Recipient <recipient@example.com>",
            body="hello",
        )

        send(data, self.config)

        command = run.call_args.args[0]
        self.assertEqual(
            command,
            ["sendmail", "--mode", "test", "-f", "sender@example.com", "recipient@example.com"],
        )
        self.assertNotIn(b"Bcc:", run.call_args.kwargs["input"])


if __name__ == "__main__":
    unittest.main()
