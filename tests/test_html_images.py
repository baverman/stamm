from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

from stamm.html_images import prepare_html_images


def image(content: bytes, *, filename: str | None = None, content_id: str | None = None) -> EmailMessage:
    part = EmailMessage()
    part.set_content(content, maintype='image', subtype='png')
    if filename is not None:
        part.add_header('Content-Disposition', 'inline', filename=filename)
    if content_id is not None:
        part['Content-ID'] = f'<{content_id}>'
    return part


def test_preserves_image_filename_and_rewrites_cid(tmp_path: Path) -> None:
    message = EmailMessage()
    message.make_related()
    part = image(b'image content', filename='logo image.png', content_id='logo@example.com')
    message.attach(part)
    html = b'<img src="logo image.png"><img src="cid:logo@example.com">'

    prepared = prepare_html_images(html, message, tmp_path)

    assert (tmp_path / 'logo image.png').read_bytes() == b'image content'
    assert prepared == b'<img src="logo image.png"><img src="logo%20image.png">'


def test_generates_filename_for_cid_image_without_one(tmp_path: Path) -> None:
    message = EmailMessage()
    message.make_related()
    message.attach(image(b'image content', content_id='generated@example.com'))

    prepared = prepare_html_images(b'<img src="CID:generated%40example.com">', message, tmp_path)

    assert (tmp_path / 'image-1.png').read_bytes() == b'image content'
    assert prepared == b'<img src="image-1.png">'
