import fitz
import pytest
from services.pdf_parser import get_pdf_internal_links

def test_get_pdf_internal_links_empty():
    assert get_pdf_internal_links("") == {}
    assert get_pdf_internal_links("nonexistent.pdf") == {}

def test_get_pdf_internal_links_synthetic(tmp_path):
    pdf_path = str(tmp_path / "test_links.pdf")
    doc = fitz.open()
    doc.new_page(width=500, height=800)
    doc.new_page(width=500, height=800)
    p1 = doc[0]
    p2 = doc[1]

    p1.insert_text((50, 100), "Click Figure 1 for details")
    p1.insert_text((50, 150), "Click here: https://example.com")
    p2.insert_text((50, 200), "Figure 1. A diagram showing results")
    p2.insert_text((50, 230), "Reference 2 should not leak into this preview")

    # Insert URI link
    uri_rect = fitz.Rect(50, 135, 250, 160)
    p1.insert_link({
        "kind": fitz.LINK_URI,
        "from": uri_rect,
        "uri": "https://example.com",
    })

    # Insert GOTO link to Page 2
    goto_rect = fitz.Rect(50, 85, 150, 110)
    p1.insert_link({
        "kind": fitz.LINK_GOTO,
        "from": goto_rect,
        "page": 1,
        "to": fitz.Point(50, 600), # 600 from bottom -> 200 from top
    })

    doc.save(pdf_path)
    doc.close()

    links = get_pdf_internal_links(pdf_path)
    assert 1 in links
    p1_links = links[1]
    assert len(p1_links) == 2

    # Check URI link
    uri_link = next(l for l in p1_links if l["dest_type"] == "uri")
    assert uri_link["uri"] == "https://example.com"
    assert uri_link["from"][0] == pytest.approx(10.0, abs=1.0) # 50/500 * 100 = 10%

    # Check GOTO link
    fig_link = next(l for l in p1_links if l["dest_type"] == "figure")
    assert fig_link["target_page"] == 2
    assert "Figure 1" in fig_link["text"] or "Figure 1" in fig_link["dest_text"]
    assert "Reference 2" not in fig_link["dest_text"]
    assert fig_link["dest_y_pct"] == pytest.approx(25.0, abs=1.0) # (800 - 600)/800 = 200/800 = 25%


def test_get_pdf_internal_links_extracts_one_author_year_entry_from_two_columns(tmp_path):
    pdf_path = str(tmp_path / "author_year_links.pdf")
    doc = fitz.open()
    doc.new_page(width=600, height=800)
    doc.new_page(width=600, height=800)
    source = doc[0]
    refs = doc[1]

    source.insert_text((50, 100), "(Lowry et al., 2014)")
    refs.insert_text((50, 200), "Lowry, M. S., Condit, R., et al. (2014). Correct target.")
    refs.insert_text((50, 225), "Next, A. (2015). Must not leak.")
    refs.insert_text((330, 200), "Copyright (2018). Wrong column.")

    # LINK_GOTO y is expressed from the PDF bottom in this API.
    source.insert_link({
        "kind": fitz.LINK_GOTO,
        "from": fitz.Rect(50, 85, 180, 110),
        "page": 1,
        "to": fitz.Point(50, 600),
    })
    doc.save(pdf_path)
    doc.close()

    links = get_pdf_internal_links(pdf_path)
    reference = next(link for link in links[1] if link["dest_type"] == "reference")
    assert reference["dest_text"].startswith("Lowry, M. S.")
    assert "Next, A." not in reference["dest_text"]
    assert "Copyright" not in reference["dest_text"]


def test_get_pdf_internal_links_fitr_with_diacritics(tmp_path):
    pdf_path = str(tmp_path / "fitr_links.pdf")
    doc = fitz.open()
    doc.new_page(width=600, height=800)
    doc.new_page(width=600, height=800)
    source = doc[0]
    refs = doc[1]

    source.insert_text((50, 100), "(Ha\xa8rko\xa8nen et al., 2006)")
    refs.insert_text((50, 200), "Ha\xa8rko\xa8nen, T., Dietz, R., et al. 2006. Epidemics review.")
    refs.insert_text((50, 240), "Next, B. 2007. Other reference.")

    # Insert base link, then configure /FitR destination in PDF structure
    source.insert_link({
        "kind": fitz.LINK_GOTO,
        "from": fitz.Rect(50, 85, 200, 110),
        "page": 1,
    })
    doc.save(pdf_path)
    doc.close()

    pdf_path_fitr = str(tmp_path / "fitr_links_final.pdf")
    d2 = fitz.open(pdf_path)
    l = d2[0].get_links()[0]
    xref = l["xref"]
    d2.xref_set_key(xref, "A", f"<< /S /GoTo /D [ {d2[1].xref} 0 R /FitR 50 580 300 600 ] >>")
    d2.save(pdf_path_fitr)
    d2.close()

    links = get_pdf_internal_links(pdf_path_fitr)
    assert 1 in links
    ref_link = links[1][0]
    assert ref_link["dest_type"] == "reference"
    assert "Härkönen" in ref_link["text"]
    assert "Härkönen, T." in ref_link["dest_text"]
    assert "Next, B." not in ref_link["dest_text"]
    assert ref_link["dest_y_pct"] == pytest.approx(25.0, abs=1.0)

