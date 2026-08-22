# Stamm MVP implementation overview

## Goal

Build a fast, mutt-like terminal Maildir client for Unix systems. The MVP uses Python 3.12 and only standard-library modules.

The primary workflow is:

1. Start `stamm` and open the configured spool, or run `stamm MAILDIR`.
2. Load cached message metadata from the Maildir-local SQLite index.
3. Scan that Maildir once for changes.
4. Read threaded mail, mark messages, compose in an external editor, and exit.

## MVP scope

The MVP includes:

- A `curses` terminal interface.
- Maildir index columns for date, flags, sender, and subject.
- Header-based threading.
- Maildir switching through a path prompt with completion.
- Explicit refresh only.
- Message and MIME-part views.
- Configurable inline MIME filters and detached external openers.
- New, reply, reply-all, inline-forward, and draft-resume composition.
- Repeatable attachments with optional output filename changes.
- Sending through a configured sendmail-compatible command.
- Maildir-local SQLite indexes.
- Read/unread and flagged state changes.

Delete, move, and copy are excluded. They need a separate interaction design.

## Command-line behavior

```text
stamm             Open the configured spool Maildir
stamm MAILDIR     Open the specified Maildir
```

Stamm expands `~` and environment variables in configured paths and paths entered in interactive prompts. CLI path expansion remains the shell's responsibility.

## Configuration

Load the first configuration file found in this priority order:

1. `./stamm.toml` in the current working directory.
2. `$XDG_CONFIG_HOME/stamm.toml` when `XDG_CONFIG_HOME` is set.
3. `~/.config/stamm.toml`.

The current-directory file supports fast project-local configuration changes during development.

Use a structure similar to:

```toml
root = "~/mail"
spool = "inbox"
sent = "sent-local"
drafts = "drafts"
editor = "vim"
sendmail = "python3 -m norless.sendmail"
identities = ["Name <user@example.com>", "Name <work@example.com>"]

auto_view = ["text/html", "text/calendar", "application/ics"]
alternative_order = ["text/plain", "text/html"]

[signatures]
"user@example.com" = "~/.signature"
"work@example.com" = "~/.signature-work"

[[mime]]
type = "text/html"
display = "w3m -dump -T text/html"
open = "xdg-open {file}"

[[mime]]
type = "image/*"
open = "xdg-open {file}"
```

Configuration rules:

- `editor` falls back to `$EDITOR` when it is not configured.
- Parse `sendmail` with `shlex.split()`, append `-f`, the envelope sender, and recipient arguments, then execute the argument list without a shell.
- `identities` must contain at least one address. Its first entry supplies `From:` for new messages.
- `root` must resolve to an absolute path after `~` and environment-variable expansion. It is the initial directory for Maildir path completion, but users can enter paths outside it.
- All other path-valued settings, including `spool`, `sent`, `drafts`, and signature files, can be absolute or relative to `root`.
- The folder prompt shows all directories and does not validate them as Maildirs.
- MIME rules are matched in the order stated in the configuration.
- MIME commands are trusted shell command strings.
- `{file}` expands to a shell-quoted temporary-file path.
- A MIME command without `{file}` receives part content through stdin.

## Application structure

Keep UI, storage, mail processing, and process execution separate:

```text
stamm/
  __main__.py       CLI entry point
  config.py         TOML loading and path expansion
  app.py            Screen transitions and application state
  ui.py             curses setup, drawing, prompts, and completion
  maildir.py        Maildir scan and flag-safe file renames
  index.py          SQLite schema and incremental metadata updates
  threads.py        Header-based thread graph construction
  message.py        Header decoding, MIME selection, and rendering
  mime.py           MIME rule matching, filters, openers, and saving
  compose.py        Editor buffers, validation, replies, and forwards
  delivery.py       Message construction, sendmail, Sent, and Drafts
```

Use small model dataclasses for indexed messages, thread rows, MIME parts, compose data, and configuration.

## Maildir indexing

Store one index in each opened Maildir:

```text
<maildir>/.stamm.sqlite3
```

On first open and explicit refresh:

1. Enumerate `new/` and `cur/` and extract each Maildir unique key by removing its `:2,<flags>` suffix.
2. Match entries to cached records by unique key before comparing paths.
3. When only path or flags changed, update those cached fields without parsing the message again.
4. Parse only new entries or entries whose content metadata changed.
5. Remove records for missing unique keys.
6. Commit the update in one transaction.

Cache the fields needed to draw and thread the index without reopening messages:

- Relative file path and Maildir unique key.
- Size and modification time.
- Maildir flags.
- Parsed date and timestamp, with file modification time as fallback.
- Decoded sender and subject.
- `Message-ID`, `In-Reply-To`, and `References`.

Opening another Maildir updates only that Maildir. Stamm does not scan all known folders at startup.

Read/unread and flagged changes rename files with standard Maildir flags:

- `S` for seen.
- `F` for flagged.

Update the cached path and flags in the same operation as each rename. Opening a message adds `S` automatically.

## Thread construction and index rows

Build threads in memory from cached headers:

1. Create visible nodes for indexed messages.
2. Create shared invisible placeholder nodes for referenced message IDs that are absent from the Maildir.
3. Link each ordered `References` chain, then link the message below its last reference.
4. Use `In-Reply-To` when no usable `References` value exists.
5. Do not use subject-based fallback in the MVP.
6. Do not render placeholder nodes; use them only to keep related descendants in one thread.

Display all messages; threads cannot be collapsed. Order siblings oldest to newest and show replies below their parent. Indent each depth with two spaces in the subject column.

A thread date is the date of its freshest message. Sort thread roots by this date, newest first.

The index screen has these columns:

```text
Date | Flags | Sender | Subject
```

Keep date, flags, and sender fixed-width. The subject column uses the remaining width and truncates content when necessary.

## Terminal interaction

Implement hardcoded, mutt-like MVP bindings. Keep bindings in one constants map so later configuration does not require UI rewrites.

Core actions include:

- `j` / `k`: next or previous message.
- `Enter`: open message.
- `q`: leave the current view or quit from the index.
- `c`: change Maildir through a completed path prompt.
- `m`: compose a new message.
- `r`: reply.
- `g`: reply all.
- `f`: forward inline.
- `F`: toggle flagged state.
- `N`: mark unread.
- `v`: open the MIME-part view.
- `e`: resume the selected message when viewing the configured Drafts Maildir.
- `R`: rescan only the current Maildir.

The path prompt completes filesystem entries. For folder switching it starts in `root`; for attachment saving it starts from the entered path.

## Message and MIME views

Use the `email` package with the modern policy to parse messages and decode headers.

For `multipart/alternative`, select the first available type in `alternative_order`. Render `text/plain` internally. Render types listed in `auto_view` through their matching `display` command.

The MIME-part view is separate from the message view and lists the complete MIME tree, including inline parts and multipart containers. For a selected leaf part it supports:

- `Enter`: open with its matching external `open` command.
- `s`: save through a path prompt with completion.

If a save destination is a directory, append the attachment filename. Use a safe generated filename when the part has none.

Run external openers detached. Track temporary files until their opener exits, or until application shutdown when process status cannot be collected safely.

## Composition

Create a temporary UTF-8 editor buffer with this form:

```text
From:
To:
Cc:
Bcc:
Subject:
Attach:

Message body...
```

`Attach:` is repeatable. Its syntax is:

```text
Attach: /path/to/file with spaces.pdf
Attach: /path/to/file with spaces.pdf -> Display Name.pdf
```

The exact ` -> ` sequence separates the source path from the MIME filename. Without it, use the source basename.

For a new message, initialize `From:` from the first configured identity. For replies, derive `From:` by matching the original message's `To:` and `Cc:` addresses against `identities`. Leave it blank when no identity matches; do not silently use the first identity as a fallback.

Reply behavior:

```text
On <date>, <sender> wrote:
> quoted original text
```

Reply-all excludes the selected sender identity from generated recipients and de-duplicates addresses.

Inline forwards include `From`, `Date`, `Subject`, `To`, and `Cc`, followed by the original rendered body.

After the editor exits, validate:

- `From:` is present and parseable.
- At least one `To:`, `Cc:`, or `Bcc:` recipient exists.
- Address fields are parseable.
- Every attachment path exists and is a readable regular file.
- Each renamed attachment filename is safe and contains no path separator.

On validation failure, show the errors and reopen the editor with the same buffer.

On success, present these actions:

- Send.
- Edit again.
- Save draft.
- Discard.

## Signatures

Map sender addresses to complete signature files. The file includes its own standard `-- ` separator.

Before sending, inspect the final body. If it already contains a line exactly equal to `-- `, do not append a signature. Otherwise, select the signature by the final `From:` address and append its file unchanged. A missing signature mapping is valid.

Do not append a signature when saving a draft; apply it when that draft is eventually sent.

## Message generation, drafts, and delivery

Use `EmailMessage` to generate standards-compliant UTF-8 messages and attachments. Generate `Date` and `Message-ID` when absent. Replies set `In-Reply-To` and extend `References`.

Save Maildir messages safely by writing under `tmp/`, flushing, and atomically moving them to the target `new/` or `cur/` directory.

Draft behavior:

- Save composed content and attachments as a MIME message in the configured Drafts Maildir.
- Mark it with the standard Maildir draft flag.
- From the Drafts Maildir, allow the selected draft to reopen in the editor.
- Extract draft attachments into a temporary compose workspace and recreate `Attach:` fields while preserving their MIME filenames.
- Replace the old draft only after a revised draft is saved or sent successfully.

Delivery behavior:

1. Read the final `From:` address as the envelope sender.
2. Collect and de-duplicate `To:`, `Cc:`, and `Bcc:` envelope recipients.
3. Generate the transport message and omit `Bcc:` from its headers.
4. Save the sent message to the configured Sent Maildir. Abort delivery if storage fails.
5. Parse the configured sendmail command with `shlex.split()`, append `-f`, the sender, and all recipients, then execute the argument list without a shell.
6. Write the complete transport message to stdin.
7. Treat a nonzero exit status as failure and retain the composition for editing or draft saving.

Report success and remove a resumed draft only after sendmail exits successfully.

## Implementation sequence

1. Add package entry point, configuration models, and TOML loading.
2. Implement Maildir scanning, local SQLite indexing, and flag renames.
3. Implement thread construction and index-row models.
4. Build the curses index, message pager, prompts, and Maildir switching.
5. Add MIME selection, filtering, the MIME-part view, external opening, and saving.
6. Add editor-buffer parsing, validation, new/reply/reply-all/forward flows, and signatures.
7. Add MIME generation, drafts, sendmail delivery, Sent storage, and draft resume.
8. Complete error handling, temporary-file cleanup, terminal restoration, and user-facing diagnostics.
