import os
import fitz
import pytest
from services.pdf_parser import (
    _build_opendataloader_pages,
    _opendataloader_page_regions,
    extract_pages,
    extract_pdf_images,
)


def test_build_opendataloader_pages_structure():
    dummy_kids = [
        {
            "type": "heading",
            "page number": 1,
            "content": "Introduction to HJPaper",
            "bounding box": [72.0, 750.0, 300.0, 770.0],
            "heading level": 1,
        },
        {
            "type": "paragraph",
            "page number": 1,
            "content": "This is a body paragraph discussing PDF parsing.",
            "bounding box": [72.0, 700.0, 400.0, 740.0],
        },
        {
            "type": "caption",
            "page number": 1,
            "content": "Figure 1: High level pipeline architecture.",
            "bounding box": [72.0, 500.0, 350.0, 520.0],
        },
        {
            "type": "header",
            "page number": 1,
            "content": "RUNNING HEADER SHOULD BE IGNORED",
            "bounding box": [72.0, 800.0, 300.0, 810.0],
        },
    ]

    pages = _build_opendataloader_pages(dummy_kids, total_pages=1)
    assert len(pages) == 1
    p1 = pages[0]
    assert p1["page_num"] == 1
    assert p1["parser_engine"] == "opendataloader"
    assert "RUNNING HEADER" not in p1["text"]
    assert "Introduction to HJPaper" in p1["text"]
    assert "discussing PDF parsing" in p1["text"]

    body_blocks = [b for b in p1["blocks"] if b["type"] == 0]
    caption_blocks = [b for b in p1["blocks"] if b["type"] == 1]
    assert len(body_blocks) == 2
    assert len(caption_blocks) == 1
    assert "Figure 1" in caption_blocks[0]["text"]


def test_opendataloader_page_regions_extraction(tmp_path):
    pdf_path = tmp_path / "dummy.pdf"
    doc = fitz.open()
    doc.new_page(width=600, height=800)
    doc.save(str(pdf_path))
    doc.close()

    dummy_kids = [
        {
            "type": "picture",
            "id": 10,
            "page number": 1,
            "bounding box": [60.0, 400.0, 360.0, 600.0],
        },
        {
            "type": "caption",
            "id": 11,
            "linked content id": 10,
            "page number": 1,
            "content": "Figure 1: Benchmark results comparison",
            "bounding box": [60.0, 370.0, 360.0, 390.0],
        },
        {
            "type": "table",
            "id": 20,
            "page number": 1,
            "bounding box": [60.0, 100.0, 480.0, 300.0],
            "content": "Table 1: Accuracy metrics across parsers",
        },
    ]

    regions = _opendataloader_page_regions(dummy_kids, str(pdf_path))
    assert len(regions) == 2

    fig_region = next(r for r in regions if r["label"] == "Figure 1")
    assert fig_region["page"] == 1
    assert abs(fig_region["left"] - 10.0) < 0.1
    assert abs(fig_region["width"] - 50.0) < 0.1
    assert "Benchmark results" in fig_region["caption"]

    table_region = next(r for r in regions if r["label"] == "Table 1")
    assert table_region["page"] == 1
    assert abs(table_region["width"] - 70.0) < 0.1


def test_opendataloader_live_pdf_parsing(tmp_path):
    pdf_path = tmp_path / "sample_paper.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 100), "HJPaper: Fast Academic Document Analysis", fontsize=14)
    page.insert_text((72, 140), "Abstract: We present HJPaper utilizing OpenDataLoader PDF for high throughput.", fontsize=10)
    page.insert_text((72, 200), "Figure 1: Architectural diagram.", fontsize=9)
    doc.save(str(pdf_path))
    doc.close()

    pages = extract_pages(str(pdf_path), engine="opendataloader")
    assert len(pages) == 1
    assert pages[0]["parser_engine"] == "opendataloader"
    assert pages[0]["page_num"] == 1
    assert "HJPaper" in pages[0]["text"]
    assert "OpenDataLoader PDF" in pages[0]["text"]
