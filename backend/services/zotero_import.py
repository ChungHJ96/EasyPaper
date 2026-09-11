"""Zotero and Zotmoov local linked attachment resolver.

Resolves zotero:// links, item keys, and file:// URLs to local PDF paths on disk.
Supports both standard Zotero storage and external linked directories (e.g. Zotmoov, ZotFile).
"""
from __future__ import annotations

import glob
import os
import re
import sqlite3
import urllib.parse
from pathlib import Path
from typing import Optional


def get_zotero_base_paths() -> list[str]:
    """Retrieve configured linked attachment base directories from Zotero preferences."""
    paths: list[str] = []
    
    # Check default Zotero profile directory
    profiles_dir = os.path.expanduser("~/Library/Application Support/Zotero/Profiles")
    if os.path.isdir(profiles_dir):
        for root, _dirs, files in os.walk(profiles_dir):
            if "prefs.js" in files:
                prefs_file = os.path.join(root, "prefs.js")
                try:
                    with open(prefs_file, encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            if any(k in line for k in ("baseAttachmentPath", "zotmoov.dst_dir", "zotfile.dest_dir")):
                                m = re.search(r'\"([^\"]+)\"\s*\);?$', line)
                                if m:
                                    p = os.path.expanduser(m.group(1).replace("\\\\", "/"))
                                    if os.path.isdir(p) and p not in paths:
                                        paths.append(p)
                except Exception:
                    pass

    # Common default/cloud storage locations as fallback
    common_candidates = [
        os.path.expanduser("~/Library/CloudStorage/Dropbox/Zotero_Sync"),
        os.path.expanduser("~/Dropbox/Zotero_Sync"),
        os.path.expanduser("~/Dropbox/Zotero"),
        os.path.expanduser("~/Zotero/storage"),
    ]
    for candidate in common_candidates:
        if os.path.isdir(candidate) and candidate not in paths:
            paths.append(candidate)

    return paths


def resolve_zotero_link(link: str) -> Optional[str]:
    """Resolve a zotero:// URI, file:// URL, or local file path to a validated local PDF path."""
    if not link:
        return None

    raw = link.strip().strip("'\"")

    # 1. file:// URL
    if raw.startswith("file://"):
        parsed = urllib.parse.urlparse(raw)
        path = urllib.parse.unquote(parsed.path)
        if os.path.isfile(path) and path.lower().endswith(".pdf"):
            return path
        return None

    # 2. Direct absolute path
    if os.path.isabs(raw) and os.path.isfile(raw) and raw.lower().endswith(".pdf"):
        return raw

    # 3. Zotero link or item key
    key = None
    # Matches: zotero://select/items/0_ABC12345, zotero://select/library/items/ABC12345, zotero://open-pdf/library/items/ABC12345
    # or web links: https://www.zotero.org/users/.../items/ABC12345
    m = re.search(r"(?:zotero://(?:select/(?:(?:library/)?items/(?:\d+_)?|groups/\d+/items/)|open-pdf/library/items/)|zotero\.org/(?:users|groups)/[^/]+/items/)([A-Za-z0-9]{8})", raw, re.IGNORECASE)
    if m:
        key = m.group(1).upper()
    elif re.match(r"^[A-Za-z0-9]{8}$", raw):
        key = raw.upper()

    if not key:
        return None

    zotero_dir = os.path.expanduser("~/Zotero")
    base_paths = get_zotero_base_paths()

    # Step 3a: Direct check in ~/Zotero/storage/<key>/*.pdf
    d_dir = os.path.join(zotero_dir, "storage", key)
    if os.path.isdir(d_dir):
        pdfs = glob.glob(os.path.join(d_dir, "*.pdf"))
        if pdfs:
            return pdfs[0]

    # Step 3b: Query zotero.sqlite (read-only immutable connection to avoid database locks)
    db_candidates = [
        os.path.join(zotero_dir, "zotero.sqlite"),
        os.path.join(zotero_dir, "zotero.sqlite.bak"),
    ]

    for db_path in db_candidates:
        if not os.path.exists(db_path):
            continue
        try:
            conn = sqlite3.connect(f"file:{db_path}?immutable=1", uri=True, timeout=2)
            c = conn.cursor()

            # Check if key is a parent item with child attachments
            c.execute("""
                SELECT att.linkMode, att.path, att_item.key
                FROM items p_item
                JOIN itemAttachments att ON att.parentItemID = p_item.itemID
                JOIN items att_item ON att_item.itemID = att.itemID
                WHERE p_item.key = ?
            """, (key,))
            rows = c.fetchall()

            # If no children, check if key is itself an attachment item
            if not rows:
                c.execute("""
                    SELECT att.linkMode, att.path, att_item.key
                    FROM items att_item
                    JOIN itemAttachments att ON att.itemID = att_item.itemID
                    WHERE att_item.key = ?
                """, (key,))
                rows = c.fetchall()

            for link_mode, att_path, att_key in rows:
                # linkMode 2: linked file (e.g. Zotmoov, ZotFile)
                if link_mode == 2 and att_path:
                    if att_path.startswith("attachments:"):
                        rel = att_path[len("attachments:"):]
                        for base in base_paths:
                            full_p = os.path.join(base, rel)
                            if os.path.isfile(full_p):
                                return full_p
                    elif os.path.isabs(att_path) and os.path.isfile(att_path):
                        return att_path
                    else:
                        # Search by filename across base paths
                        fname = os.path.basename(att_path)
                        for base in base_paths:
                            candidate = os.path.join(base, fname)
                            if os.path.isfile(candidate):
                                return candidate

                # linkMode 0: imported file (stored in ~/Zotero/storage/<att_key>)
                if att_key:
                    att_dir = os.path.join(zotero_dir, "storage", att_key)
                    if os.path.isdir(att_dir):
                        pdfs = glob.glob(os.path.join(att_dir, "*.pdf"))
                        if pdfs:
                            return pdfs[0]
        except Exception:
            continue

    return None
