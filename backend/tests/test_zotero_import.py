import sqlite3
from pathlib import Path

from services.zotero_import import extract_zotero_item_key, resolve_zotero_link


def _write_preferences(profile_root: Path, data_dir: Path, attachments_dir: Path) -> None:
    profile = profile_root / "test.default"
    profile.mkdir(parents=True)
    (profile / "prefs.js").write_text(
        '\n'.join([
            f'user_pref("extensions.zotero.dataDir", "{data_dir}");',
            f'user_pref("extensions.zotero.baseAttachmentPath", "{attachments_dir}");',
        ]),
        encoding="utf-8",
    )


def _write_zotero_db(data_dir: Path, *, link_mode: int, attachment_path: str) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(data_dir / "zotero.sqlite") as conn:
        conn.executescript("""
            CREATE TABLE items (itemID INTEGER PRIMARY KEY, key TEXT NOT NULL);
            CREATE TABLE itemAttachments (
                itemID INTEGER PRIMARY KEY,
                parentItemID INTEGER,
                linkMode INTEGER NOT NULL,
                path TEXT
            );
            INSERT INTO items VALUES (1, 'XZPQ7TKQ');
            INSERT INTO items VALUES (2, '5C3FM777');
        """)
        conn.execute(
            "INSERT INTO itemAttachments VALUES (2, 1, ?, ?)",
            (link_mode, attachment_path),
        )


def test_extracts_current_and_legacy_zotero_item_uris():
    assert extract_zotero_item_key("zotero://select/library/items/5c3fm777") == "5C3FM777"
    assert extract_zotero_item_key("zotero://open-pdf/groups/42/items/5C3FM777?page=8") == "5C3FM777"
    assert extract_zotero_item_key("zotero://select/items/0_XZPQ7TKQ") == "XZPQ7TKQ"


def test_resolves_linked_attachment_from_parent_or_attachment_item(tmp_path):
    home = tmp_path / "home"
    profile_root = home / "profiles"
    data_dir = home / "custom-zotero"
    attachments_dir = home / "Zotero Sync"
    attachments_dir.mkdir(parents=True)
    pdf = attachments_dir / "McClintock et al. - 2013 - paper.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    _write_preferences(profile_root, data_dir, attachments_dir)
    _write_zotero_db(data_dir, link_mode=2, attachment_path=f"attachments:{pdf.name}")

    for key in ("XZPQ7TKQ", "5C3FM777"):
        resolved = resolve_zotero_link(
            f"zotero://select/library/items/{key}",
            home_dir=home,
            profile_roots=[profile_root],
        )
        assert resolved == str(pdf.resolve())


def test_resolves_stored_attachment_and_percent_encoded_file_url(tmp_path):
    home = tmp_path / "home"
    profile_root = home / "profiles"
    data_dir = home / "Zotero"
    attachments_dir = home / "attachments"
    attachments_dir.mkdir(parents=True)
    _write_preferences(profile_root, data_dir, attachments_dir)
    stored_dir = data_dir / "storage" / "5C3FM777"
    stored_dir.mkdir(parents=True)
    pdf = stored_dir / "Paper with spaces.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    _write_zotero_db(data_dir, link_mode=0, attachment_path=f"storage:{pdf.name}")

    assert resolve_zotero_link(
        "zotero://open-pdf/library/items/5C3FM777",
        home_dir=home,
        profile_roots=[profile_root],
    ) == str(pdf.resolve())
    assert resolve_zotero_link(pdf.as_uri(), home_dir=home, profile_roots=[profile_root]) == str(pdf.resolve())
