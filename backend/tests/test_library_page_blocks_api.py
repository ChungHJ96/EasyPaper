"""Tests for GET & PUT /api/library/{doc_id}/pages/{page_num}/blocks."""

from unittest.mock import patch


def _create_doc(isolated_dirs, doc_id="doc-blocks-1", username="testuser"):
    db = isolated_dirs["db"]
    db.db_save_document(doc_id, username, "paper.pdf", "/x/paper.pdf", 3, {"title": "Test Paper"}, parser_engine="mineru")


def test_get_library_page_blocks_success(test_client, isolated_dirs, tmp_path):
    _create_doc(isolated_dirs)
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake" + b"\0" * 200)

    fake_pages = [
        {
            "page_num": 1,
            "text": "Hello world",
            "blocks": [
                {"bbox": [100.0, 100.0, 900.0, 200.0], "text": "Hello world", "type": 0, "raw_type": "text"},
            ],
            "ignored_blocks": [
                {"bbox": [50.0, 20.0, 300.0, 40.0], "text": "Downloaded from Wiley", "type": 2, "raw_type": "header"},
            ],
            "parser_engine": "mineru",
        }
    ]

    with patch("routers.library.get_pdf_path", return_value=str(pdf_path)), \
         patch("services.cache.get_cached_pages", return_value=fake_pages):
        res = test_client.get("/api/library/doc-blocks-1/pages/1/blocks")

    assert res.status_code == 200
    data = res.json()
    assert data["page_num"] == 1
    assert data["parser_engine"] == "mineru"
    blocks = data["blocks"]
    assert len(blocks) == 2
    # Verify pct_bbox calculation for MinerU (0-1000 scale / 10)
    assert blocks[0]["type"] == 0
    assert blocks[0]["pct_bbox"] == [10.0, 10.0, 80.0, 10.0]
    assert blocks[1]["type"] == 2
    assert blocks[1]["pct_bbox"] == [5.0, 2.0, 25.0, 2.0]


def test_put_library_page_blocks_updates_and_clears_translation(test_client, isolated_dirs, tmp_path):
    _create_doc(isolated_dirs, doc_id="doc-blocks-put")
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake" + b"\0" * 200)

    from services.cache import save_translation_cache, get_cached_translation
    from services.db import db_save_translation, db_get_translation

    save_translation_cache("doc-blocks-put", 1, "Page 1 Old Trans", suffix="ko_academic")
    db_save_translation("doc-blocks-put", 1, "Page 1 Old Trans", suffix="ko_academic")

    fake_pages = [
        {
            "page_num": 1,
            "text": "Hello world",
            "blocks": [
                {"bbox": [100.0, 100.0, 900.0, 200.0], "text": "Hello world", "type": 0, "raw_type": "text"},
            ],
            "ignored_blocks": [
                {"bbox": [50.0, 20.0, 300.0, 40.0], "text": "Downloaded from Wiley", "type": 2, "raw_type": "header"},
            ],
            "parser_engine": "mineru",
        }
    ]

    payload = {
        "blocks": [
            {"bbox": [50.0, 20.0, 300.0, 40.0], "text": "Downloaded from Wiley", "type": 0, "raw_type": "header"},
            {"bbox": [100.0, 100.0, 900.0, 200.0], "text": "Hello world", "type": 2, "raw_type": "text"},
        ]
    }

    with patch("routers.library.get_pdf_path", return_value=str(pdf_path)), \
         patch("services.cache.get_cached_pages", return_value=fake_pages), \
         patch("services.cache.save_pages_cache") as mock_save_pages:
        res = test_client.put("/api/library/doc-blocks-put/pages/1/blocks", json=payload)

    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["blocks_count"] == 1
    assert data["ignored_count"] == 1
    assert "Downloaded from Wiley" in data["text"]
    assert "Hello world" not in data["text"]

    # Verify translation cache was cleared
    assert get_cached_translation("doc-blocks-put", 1, suffix="ko_academic") is None
    assert db_get_translation("doc-blocks-put", 1, suffix="ko_academic") is None
