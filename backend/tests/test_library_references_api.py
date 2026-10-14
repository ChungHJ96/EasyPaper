"""GET /library/{doc_id}/references HTTP 레벨 테스트.

로컬 PDF 참고문헌 파싱 결과의 캐싱과 소유자 격리를 확인한다.
"""

from unittest.mock import patch


def _create_doc(isolated_dirs, doc_id="doc-1", username="testuser"):
    db = isolated_dirs["db"]
    db.db_save_document(doc_id, username, "paper.pdf", "/x/paper.pdf", 3, {"title": "Test Paper"})


def test_get_references_parses_and_caches(test_client, isolated_dirs):
    _create_doc(isolated_dirs)

    fake_pages = [{"page_num": 1, "text": "References\n\n[1] Someone. A Paper. 2020."}]
    with patch("services.pdf_parser.extract_pages", return_value=fake_pages), \
         patch("routers.library.get_pdf_path", return_value="/fake/path.pdf"):
        res = test_client.get("/api/library/doc-1/references")

    assert res.status_code == 200
    assert res.json()["references"] == {"1": "Someone. A Paper. 2020."}

    # 두 번째 호출은 캐시를 써야 하므로 extract_pages가 다시 호출되지 않아야 한다
    with patch("services.pdf_parser.extract_pages") as mock_extract:
        res2 = test_client.get("/api/library/doc-1/references")
    assert res2.status_code == 200
    assert res2.json()["references"] == {"1": "Someone. A Paper. 2020."}
    mock_extract.assert_not_called()


def test_get_references_other_users_document_returns_404(test_client, isolated_dirs):
    _create_doc(isolated_dirs, doc_id="doc-other", username="otheruser")
    res = test_client.get("/api/library/doc-other/references")
    assert res.status_code == 404
