"""Import a directly linked PDF or a readable web article."""
from __future__ import annotations

import asyncio
import ipaddress
import os
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from config import LIBRARY_DIR, UPLOAD_DIR
from models.schemas import UploadResponse, UrlImportRequest
from services.auth import get_current_user
from services.rate_limiter import enforce_rate_limit
from services.web_import import WebImportError, extract_article, fetch_url
from services.zotero_import import extract_zotero_item_key, resolve_zotero_link

router = APIRouter()


def _is_local_request(request: Request) -> bool:
    if os.getenv("HJPAPER_DESKTOP") == "1" or os.getenv("EASYPAPER_DESKTOP") == "1":
        return True
    host = request.client.host if request.client else ""
    if host in {"localhost", "testclient"}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _looks_like_local_reference(value: str) -> bool:
    raw = value.strip()
    return bool(
        raw.lower().startswith(("zotero://", "file://"))
        or Path(raw).is_absolute()
        or extract_zotero_item_key(raw)
    )


def _capabilities(kind: str) -> dict:
    common = {"translation": True, "search": True, "annotations": True, "memos": True, "chat": True, "export_pdf": True}
    return {**common, "coordinate_crop": kind == "pdf", "text_anchor_capture": kind == "html_article", "original_site": kind == "html_article"}


def _validate_options(body: UrlImportRequest) -> tuple[str, str]:
    from services.document_policy import feature_enabled, validate_classification
    from services.languages import normalize_document_language
    try:
        validate_classification(body.document_mode, body.document_type, allow_deprecated=False)
        if body.classification_method not in {"manual", "ai"}:
            raise ValueError("유효하지 않은 문서 분류 방식입니다.")
        if body.document_mode == "general" and not feature_enabled("general_document_mode"):
            raise ValueError("일반 문서 모드가 아직 활성화되지 않았습니다.")
        target = normalize_document_language(body.target_lang, allow_legacy=True)
        source = normalize_document_language(body.source_lang, allow_auto=True)
        return target, source
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _import_local_pdf(
    body: UrlImportRequest,
    current_user: str,
    doc_id: str,
    local_pdf: str,
    source_origin: str,
    target_lang: str,
    source_lang: str,
) -> UploadResponse:
    """Copy a resolved local PDF into HJPaper, then run the normal parser."""
    session_dir = Path(UPLOAD_DIR) / doc_id
    try:
        session_dir.mkdir(parents=True, exist_ok=False)
        pdf_path = session_dir / "document.pdf"
        partial_path = session_dir / "document.pdf.part"
        shutil.copyfile(local_pdf, partial_path)
        with partial_path.open("rb+") as copied:
            os.fsync(copied.fileno())
        os.replace(partial_path, pdf_path)
        file_size_bytes = pdf_path.stat().st_size

        from services.document_tasks import create_task
        from services.parse_job import execute_parse_task
        from services.pdf_parser import extract_pages, get_pdf_metadata
        from services.translation_job import start_job
        from services.insight_job import start_keyword_job, start_summary_job
        from routers.upload import sessions

        filename = Path(local_pdf).name or "document.pdf"
        options = body.model_dump(exclude={"url", "upload_id"}) | {
            "filename": filename,
            "username": current_user,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "file_size_mb": file_size_bytes / 1048576,
        }
        task = create_task(doc_id, "parse", options, status="queued")
        parsed = await execute_parse_task(
            task["id"],
            sessions,
            page_extractor=extract_pages,
            metadata_reader=get_pdf_metadata,
            translation_starter=start_job,
            keyword_starter=start_keyword_job,
            summary_starter=start_summary_job,
            upload_root=UPLOAD_DIR,
        )

        from datetime import datetime, timezone
        from services.db import get_db

        fetched_at = datetime.now(timezone.utc).isoformat()
        canonical_path = str(Path(local_pdf).resolve())
        with get_db() as conn:
            conn.execute(
                "UPDATE documents SET source_origin=?, source_url=?, canonical_url=?, fetched_at=?, content_unit_count=total_pages WHERE id=?",
                (source_origin, body.url, canonical_path, fetched_at, doc_id),
            )
            conn.commit()
        parsed.update(
            file_size_mb=round(file_size_bytes / 1048576, 2),
            source_origin=source_origin,
            content_kind="pdf",
            source_url=body.url,
            canonical_url=canonical_path,
            fetched_at=fetched_at,
            total_units=parsed["total_pages"],
            capabilities=_capabilities("pdf"),
        )
        return UploadResponse(**parsed)
    except HTTPException:
        shutil.rmtree(session_dir, ignore_errors=True)
        raise
    except Exception as exc:
        from services.db import db_delete_document

        db_delete_document(doc_id)
        shutil.rmtree(Path(LIBRARY_DIR) / doc_id, ignore_errors=True)
        shutil.rmtree(session_dir, ignore_errors=True)
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_pdf", "message": f"Zotero PDF 가져오기 실패: {exc}"},
        ) from exc


@router.post("/import-url", response_model=UploadResponse)
async def import_url(body: UrlImportRequest, request: Request, current_user: str = Depends(get_current_user)):
    enforce_rate_limit("upload", current_user)
    target_lang, source_lang = _validate_options(body)
    if body.upload_id:
        try:
            doc_id = str(uuid.UUID(body.upload_id))
        except (ValueError, AttributeError):
            raise HTTPException(status_code=400, detail={"code": "invalid_upload_id"})
        from routers.upload import sessions
        from services.db import db_get_document
        if doc_id in sessions or db_get_document(doc_id):
            raise HTTPException(status_code=409, detail={"code": "upload_id_conflict"})
    else:
        doc_id = str(uuid.uuid4())

    if _looks_like_local_reference(body.url):
        if not _is_local_request(request):
            raise HTTPException(
                status_code=403,
                detail={"code": "local_import_forbidden", "message": "로컬 Zotero 파일은 HJPaper가 실행 중인 컴퓨터에서만 가져올 수 있습니다."},
            )
        local_pdf = await asyncio.to_thread(resolve_zotero_link, body.url)
        if not local_pdf:
            raise HTTPException(
                status_code=404,
                detail={"code": "zotero_not_found", "message": "Zotero에서 해당 PDF 파일을 찾을 수 없습니다. Zotero에서 PDF가 정상적으로 열리는지 확인해주세요."},
            )
        source_origin = "zotero" if extract_zotero_item_key(body.url) else "local"
        return await _import_local_pdf(
            body,
            current_user,
            doc_id,
            local_pdf,
            source_origin,
            target_lang,
            source_lang,
        )

    try:
        fetched = await asyncio.to_thread(fetch_url, body.url)
    except WebImportError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc)}) from exc

    if fetched.kind == "remote_pdf":
        session_dir = Path(UPLOAD_DIR) / doc_id
        try:
            session_dir.mkdir(parents=True, exist_ok=False)
            pdf_path = session_dir / "document.pdf"
            partial_path = session_dir / "document.pdf.part"
            shutil.copyfile(fetched.temp_path, partial_path)
            with partial_path.open("rb+") as source:
                os.fsync(source.fileno())
            os.replace(partial_path, pdf_path)
            downloaded_size = pdf_path.stat().st_size
            fetched.cleanup()
            from services.document_tasks import create_task
            from services.parse_job import execute_parse_task
            from services.pdf_parser import extract_pages, get_pdf_metadata
            from services.translation_job import start_job
            from services.insight_job import start_keyword_job, start_summary_job
            from routers.upload import sessions
            filename = Path(fetched.final_url.split("?", 1)[0]).name or "remote-document.pdf"
            if not filename.lower().endswith(".pdf"):
                filename += ".pdf"
            options = body.model_dump(exclude={"url", "upload_id"}) | {"filename": filename, "username": current_user, "source_lang": source_lang, "target_lang": target_lang, "file_size_mb": downloaded_size / 1048576}
            task = create_task(doc_id, "parse", options, status="queued")
            parsed = await execute_parse_task(task["id"], sessions, page_extractor=extract_pages, metadata_reader=get_pdf_metadata, translation_starter=start_job, keyword_starter=start_keyword_job, summary_starter=start_summary_job, upload_root=UPLOAD_DIR)
            from services.db import get_db
            from datetime import datetime, timezone
            fetched_at = datetime.now(timezone.utc).isoformat()
            with get_db() as conn:
                conn.execute("UPDATE documents SET source_origin='web', source_url=?, canonical_url=?, fetched_at=?, content_unit_count=total_pages WHERE id=?", (body.url, fetched.final_url, fetched_at, doc_id))
                conn.commit()
            parsed.update(file_size_mb=round(downloaded_size / 1048576, 2), source_origin="web", content_kind="pdf", source_url=body.url, canonical_url=fetched.final_url, fetched_at=fetched_at, total_units=parsed["total_pages"], capabilities=_capabilities("pdf"))
            return UploadResponse(**parsed)
        except HTTPException:
            fetched.cleanup()
            shutil.rmtree(session_dir, ignore_errors=True)
            raise
        except Exception as exc:
            fetched.cleanup()
            from services.db import db_delete_document
            db_delete_document(doc_id)
            shutil.rmtree(Path(LIBRARY_DIR) / doc_id, ignore_errors=True)
            shutil.rmtree(session_dir, ignore_errors=True)
            raise HTTPException(status_code=422, detail={"code": "invalid_pdf", "message": f"PDF 처리 실패: {exc}"}) from exc

    staging = Path(LIBRARY_DIR) / f".{doc_id}.importing"
    final_dir = Path(LIBRARY_DIR) / doc_id
    try:
        article_dir = staging / "article"
        try:
            downloaded_size = Path(fetched.temp_path).stat().st_size if fetched.temp_path else len(fetched.content or b"")
            manifest, pages = await asyncio.to_thread(extract_article, fetched, article_dir)
        finally:
            fetched.cleanup()
        (staging / "translations").mkdir(parents=True, exist_ok=True)
        staging.rename(final_dir)
        manifest_path = final_dir / "article" / "article.json"
        from services.languages import detect_document_language
        detection = detect_document_language(pages)
        from services.db import db_save_document
        metadata = {"title": manifest["title"], "source_url": body.url, "canonical_url": manifest["canonical_url"]}
        classification_status = "pending" if body.classification_method == "ai" else "confirmed"
        db_save_document(doc_id, current_user, f"{manifest['title']}.html", str(manifest_path), len(pages), metadata, document_mode=body.document_mode, document_type=body.document_type, classification_status=classification_status, source_language=source_lang, detected_source_language=str(detection["language"]), source_language_confidence=float(detection["confidence"]), preferred_target_language=target_lang, parser_engine="readability", parser_version="1", source_origin="web", content_kind="html_article", source_url=body.url, canonical_url=manifest["canonical_url"], fetched_at=manifest["fetched_at"], content_schema_version=1, content_unit_count=len(pages))
        from services.cache import save_pages_cache
        save_pages_cache(doc_id, str(manifest_path), pages, "readability", "1", strict=True)
        from services.context_retrieval import index_document_chunks
        index_document_chunks(doc_id, pages)
        from routers.upload import sessions
        sessions[doc_id] = {"pdf_path": str(manifest_path), "filename": f"{manifest['title']}.html", "pages": pages, "total_pages": len(pages), "metadata": metadata, "from_library": True, "username": current_user, "document_mode": body.document_mode, "document_type": body.document_type, "classification_status": classification_status, "processing_options": body.model_dump(exclude={"url", "upload_id"}), "source_language": source_lang, "detected_source_language": detection["language"], "source_language_confidence": detection["confidence"], "preferred_target_language": target_lang, "processing_policy": "inherit", "content_revision": 1, "parser_engine": "readability", "parser_version": "1", "content_kind": "html_article", "source_origin": "web"}
        if body.classification_method == "ai":
            from services.document_classification import start_classification_task
            start_classification_task(doc_id, manifest["title"], pages)
        elif body.translation_mode == "auto" and len(pages) < 50 and (source_lang if source_lang != "auto" else detection["language"]) != target_lang:
            from services.translation_job import start_job
            start_job(doc_id, pages, target_lang=target_lang, source_lang=source_lang if source_lang != "auto" else detection["language"], style=body.style, ignore_math=body.ignore_math, ignore_table=body.ignore_table, ignore_refs=body.ignore_refs)
        return UploadResponse(session_id=doc_id, filename=f"{manifest['title']}.html", total_pages=len(pages), file_size_mb=round(downloaded_size / 1048576, 2), metadata=metadata, document_mode=body.document_mode, document_type=body.document_type, classification_status=classification_status, source_language=source_lang, detected_source_language=str(detection["language"]), source_language_confidence=float(detection["confidence"]), preferred_target_language=target_lang, source_origin="web", content_kind="html_article", source_url=body.url, canonical_url=manifest["canonical_url"], fetched_at=manifest["fetched_at"], total_units=len(pages), capabilities=_capabilities("html_article"))
    except WebImportError as exc:
        shutil.rmtree(staging, ignore_errors=True); shutil.rmtree(final_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc)}) from exc
    except Exception as exc:
        from services.db import db_delete_document
        db_delete_document(doc_id)
        shutil.rmtree(staging, ignore_errors=True); shutil.rmtree(final_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail={"code": "article_processing_failed", "message": f"웹 문서 처리 실패: {exc}"}) from exc
