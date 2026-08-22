from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path
import tempfile
import unittest

from stamm.app import App
from stamm.config import Config
from stamm.index import MessageIndex
from stamm.maildir import ensure_maildir, store


class DeleteTests(unittest.TestCase):
    def test_move_to_trash_moves_file_and_removes_index_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inbox = root / "inbox"
            trash = root / "trash"
            ensure_maildir(inbox)
            ensure_maildir(trash)
            message = EmailMessage()
            message["From"] = "sender@example.com"
            message["To"] = "recipient@example.com"
            message["Subject"] = "delete me"
            message.set_content("body")
            source = store(inbox, message.as_bytes(), flags="FS", seen=True)

            with MessageIndex(inbox) as index:
                item = index.refresh()[0]
                target = index.move_to(item.key, trash)

                self.assertIsNone(index.get(item.key))
                self.assertFalse(source.exists())
                self.assertTrue(target.exists())
                self.assertEqual(target.parent, trash / "cur")
                self.assertTrue(target.name.endswith(":2,FS"))

    def test_message_cannot_move_to_its_current_maildir(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            maildir = Path(directory)
            ensure_maildir(maildir)
            message = EmailMessage()
            message.set_content("body")
            store(maildir, message.as_bytes())
            with MessageIndex(maildir) as index:
                item = index.refresh()[0]
                with self.assertRaisesRegex(ValueError, "already in"):
                    index.move_to(item.key, maildir)


    def test_mark_keeps_message_until_purge(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inbox = root / "inbox"
            trash = root / "trash"
            ensure_maildir(inbox)
            message = EmailMessage()
            message["Subject"] = "delete later"
            message.set_content("body")
            source = store(inbox, message.as_bytes())
            config = Config(
                root=root,
                spool=inbox,
                sent=root / "sent",
                drafts=root / "drafts",
                trash=trash,
                editor="true",
                sendmail="true",
                identities=("sender@example.com",),
            )
            app = App(object(), config, inbox)  # type: ignore[arg-type]
            try:
                app.open_maildir(inbox)
                key = app.rows[0].message.key

                app.mark_deleted()

                self.assertTrue(source.exists())
                self.assertIn(key, app.pending_delete[inbox.resolve()])
                self.assertEqual(app.purge_deleted(), [])
                self.assertFalse(source.exists())
                self.assertFalse(app.pending_delete)
                self.assertEqual(len(list((trash / "new").iterdir())), 1)
            finally:
                if app.index:
                    app.index.close()
                app.mime.close()


if __name__ == "__main__":
    unittest.main()
