"""Resolve Zotero/Zotmoov attachment references to local PDF files.

The desktop client deliberately opens Zotero's SQLite database read-only. It
never moves or edits an attachment; the import router copies the resolved PDF
into HJPaper before parsing it.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sqlite3
import urllib.parse
from contextlib import closing
from pathlib import Path
from typing import Iterable, Optional


_PREFERENCE_KEYS = {
    "extensions.zotero.baseAttachmentPath",
    "extensions.zotero.dataDir",
    "extensions.zotfile.dest_dir",
    "extensions.zotmoov.dst_dir",
}


def _default_profile_roots(home: Path) -> list[Path]:
    roots = [
        home / "Library" / "Application Support" / "Zotero" / "Profiles",
        home / ".zotero" / "zotero",
    ]
    appdata = os.getenv("APPDATA")
    if appdata:
        roots.append(Path(appdata) / "Zotero" / "Zotero" / "Profiles")
    return roots


def _profile_preferences(
    home_dir: str | os.PathLike[str] | None = None,
    profile_roots: Iterable[str | os.PathLike[str]] | None = None,
) -> dict[str, list[str]]:
    home = Path(home_dir).expanduser() if home_dir else Path.home()
    roots = [Path(root) for root in profile_roots] if profile_roots is not None else _default_profile_roots(home)
    found: dict[str, list[str]] = {key: [] for key in _PREFERENCE_KEYS}

    for root in roots:
        if not root.is_dir():
            continue
        for prefs_file in root.glob("*/prefs.js"):
            try:
                lines = prefs_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            for line in lines:
                match = re.match(r'^user_pref\("([^"]+)",\s*(.+)\);$', line.strip())
                if not match or match.group(1) not in _PREFERENCE_KEYS:
                    continue
                try:
                    value = json.loads(match.group(2))
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if isinstance(value, str) and value not in found[match.group(1)]:
                    found[match.group(1)].append(value)
    return found


def _expanded_path(value: str, home: Path) -> Path:
    expanded = os.path.expandvars(value)
    if expanded == "~":
        return home
    if expanded.startswith(("~/", "~\\")):
        return home / expanded[2:]
    return Path(expanded).expanduser()


def get_zotero_base_paths(
    home_dir: str | os.PathLike[str] | None = None,
    profile_roots: Iterable[str | os.PathLike[str]] | None = None,
) -> list[str]:
    """Return existing linked-attachment roots from Zotero and common fallbacks."""
    home = Path(home_dir).expanduser() if home_dir else Path.home()
    prefs = _profile_preferences(home, profile_roots)
    candidates = [
        *prefs["extensions.zotero.baseAttachmentPath"],
        *prefs["extensions.zotmoov.dst_dir"],
        *prefs["extensions.zotfile.dest_dir"],
        str(home / "Library" / "CloudStorage" / "Dropbox" / "Zotero_Sync"),
        str(home / "Dropbox" / "Zotero_Sync"),
        str(home / "Dropbox" / "Zotero"),
        str(home / "Zotero" / "storage"),
    ]
    paths: list[str] = []
    for value in candidates:
        path = _expanded_path(value, home)
        if path.is_dir():
            resolved = str(path.resolve())
            if resolved not in paths:
                paths.append(resolved)
    return paths


def get_zotero_data_dirs(
    home_dir: str | os.PathLike[str] | None = None,
    profile_roots: Iterable[str | os.PathLike[str]] | None = None,
) -> list[str]:
    """Return existing Zotero data directories, honoring a custom dataDir."""
    home = Path(home_dir).expanduser() if home_dir else Path.home()
    prefs = _profile_preferences(home, profile_roots)
    candidates = [*prefs["extensions.zotero.dataDir"], str(home / "Zotero")]
    paths: list[str] = []
    for value in candidates:
        path = _expanded_path(value, home)
        if path.is_dir():
            resolved = str(path.resolve())
            if resolved not in paths:
                paths.append(resolved)
    return paths


def extract_zotero_item_key(link: str) -> Optional[str]:
    raw = str(link or "").strip().strip("'\"")
    patterns = [
        r"zotero://(?:select|open-pdf)/(?:library|groups/\d+)/items/([A-Za-z0-9]{8})",
        r"zotero://select/items/(?:\d+_)?([A-Za-z0-9]{8})",
        r"zotero\.org/(?:users|groups)/[^/]+/items/([A-Za-z0-9]{8})",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    if re.fullmatch(r"[A-Za-z0-9]{8}", raw):
        return raw.upper()
    return None


def _existing_pdf(path: Path) -> Optional[str]:
    if path.is_file() and path.suffix.lower() == ".pdf":
        return str(path.resolve())
    return None


def _stored_attachment(zotero_dir: Path, attachment_key: str, attachment_path: str | None = None) -> Optional[str]:
    storage_dir = zotero_dir / "storage" / attachment_key
    if attachment_path and attachment_path.startswith("storage:"):
        exact = _existing_pdf(storage_dir / attachment_path[len("storage:"):])
        if exact:
            return exact
    if storage_dir.is_dir():
        pdfs = sorted(glob.glob(str(storage_dir / "*.pdf")))
        if pdfs:
            return str(Path(pdfs[0]).resolve())
    return None


def _linked_attachment(attachment_path: str | None, base_paths: list[str]) -> Optional[str]:
    if not attachment_path:
        return None
    if attachment_path.startswith("attachments:"):
        relative = attachment_path[len("attachments:"):]
        relative_candidates = [relative]
        decoded = urllib.parse.unquote(relative)
        if decoded != relative:
            relative_candidates.append(decoded)
        for base in base_paths:
            for candidate in relative_candidates:
                resolved = _existing_pdf(Path(base) / candidate)
                if resolved:
                    return resolved
        return None

    direct = Path(attachment_path)
    if direct.is_absolute():
        return _existing_pdf(direct)

    filename = Path(attachment_path).name
    for base in base_paths:
        resolved = _existing_pdf(Path(base) / attachment_path) or _existing_pdf(Path(base) / filename)
        if resolved:
            return resolved
    return None


def resolve_zotero_link(
    link: str,
    home_dir: str | os.PathLike[str] | None = None,
    profile_roots: Iterable[str | os.PathLike[str]] | None = None,
) -> Optional[str]:
    """Resolve a zotero:// URI, Zotero web item, file URL, or local PDF path."""
    if not link:
        return None

    raw = link.strip().strip("'\"")
    if raw.lower().startswith("file://"):
        parsed = urllib.parse.urlparse(raw)
        path = urllib.parse.unquote(parsed.path)
        if parsed.netloc and parsed.netloc not in {"", "localhost"}:
            path = f"//{parsed.netloc}{path}"
        return _existing_pdf(Path(path))

    direct_path = Path(raw)
    if direct_path.is_absolute():
        return _existing_pdf(direct_path)

    key = extract_zotero_item_key(raw)
    if not key:
        return None

    base_paths = get_zotero_base_paths(home_dir, profile_roots)
    for data_dir_value in get_zotero_data_dirs(home_dir, profile_roots):
        zotero_dir = Path(data_dir_value)
        direct = _stored_attachment(zotero_dir, key)
        if direct:
            return direct

        for db_path in (zotero_dir / "zotero.sqlite", zotero_dir / "zotero.sqlite.bak"):
            if not db_path.is_file():
                continue
            try:
                uri = f"{db_path.resolve().as_uri()}?immutable=1"
                with closing(sqlite3.connect(uri, uri=True, timeout=2)) as conn:
                    rows = conn.execute(
                        """
                        SELECT att.linkMode, att.path, att_item.key
                        FROM items p_item
                        JOIN itemAttachments att ON att.parentItemID = p_item.itemID
                        JOIN items att_item ON att_item.itemID = att.itemID
                        WHERE p_item.key = ?
                        """,
                        (key,),
                    ).fetchall()
                    if not rows:
                        rows = conn.execute(
                            """
                            SELECT att.linkMode, att.path, att_item.key
                            FROM items att_item
                            JOIN itemAttachments att ON att.itemID = att_item.itemID
                            WHERE att_item.key = ?
                            """,
                            (key,),
                        ).fetchall()
            except (OSError, sqlite3.Error):
                continue

            for link_mode, attachment_path, attachment_key in rows:
                if link_mode == 2:
                    linked = _linked_attachment(attachment_path, base_paths)
                    if linked:
                        return linked
                stored = _stored_attachment(zotero_dir, attachment_key, attachment_path)
                if stored:
                    return stored
    return None
