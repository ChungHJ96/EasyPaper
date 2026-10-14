"""marker/mineru 엔진의 블록 -> 텍스트/오버레이 변환 로직 단위 테스트.

marker(PyTorch 기반 레이아웃 모델)와 mineru(별도 전용 venv에서만 동작)는
무거운 모델을 실제로 구동해야 해서 일반 테스트 스위트에서 돌리기 부적합하다.
대신 두 엔진이 만들어내는 산출물의 스키마(JSONBlockOutput 트리 / content_list
dict)를 그대로 흉내 낸 가짜 데이터로, 그 산출물을 우리 텍스트/오버레이
포맷으로 변환하는 순수 로직(_marker_page_text, _marker_page_regions,
_mineru_item_text, _mineru_page_regions)만 검증한다.
"""
from services.pdf_parser import (
    _marker_page_text,
    _marker_page_regions,
    _mineru_item_text,
    _mineru_page_regions,
    _build_mineru_pages,
    is_metadata_text,
)


class FakeMarkerBlock:
    """marker JSONRenderer가 만드는 JSONBlockOutput을 흉내 낸 더미 객체.
    실제 pydantic 모델과 달리 속성 접근(block_type/html/bbox/children)만
    필요하므로 이 정도로 충분하다."""

    def __init__(self, block_type, html="", bbox=None, children=None):
        self.block_type = block_type
        self.html = html
        self.bbox = bbox
        self.children = children


def test_marker_page_text_skips_figures_keeps_text():
    page = FakeMarkerBlock(
        "Page",
        bbox=[0, 0, 1000, 1300],
        children=[
            FakeMarkerBlock("Text", html="<p>Introduction paragraph.</p>"),
            FakeMarkerBlock("FigureGroup", bbox=[100, 400, 600, 800], children=[
                FakeMarkerBlock("Figure", bbox=[100, 400, 600, 750]),
                FakeMarkerBlock("Caption", html="<p><strong>Figure 1.</strong> A test figure.</p>"),
            ]),
            FakeMarkerBlock("Text", html="<p>Conclusion paragraph.</p>"),
        ],
    )

    text = _marker_page_text(page)

    assert "Introduction paragraph." in text
    assert "Conclusion paragraph." in text
    # 그림/캡션은 본문 텍스트 스트림에서 빠져야 한다 (pymupdf 경로의 벡터
    # 그림 필터링과 동일한 의도)
    assert "A test figure" not in text


def test_marker_page_regions_detects_labeled_figure_group():
    page = FakeMarkerBlock(
        "Page",
        bbox=[0, 0, 1000, 1300],
        children=[
            FakeMarkerBlock("FigureGroup", bbox=[100, 400, 600, 800], children=[
                FakeMarkerBlock("Figure", bbox=[100, 400, 600, 750]),
                FakeMarkerBlock("Caption", html="<p>Figure 1: A test figure.</p>"),
            ]),
        ],
    )

    regions = _marker_page_regions(page)

    assert len(regions) == 1
    r = regions[0]
    assert r["label"] == "Figure 1"
    assert "A test figure" in r["caption"]
    # bbox [100,400,600,800] / page [0,0,1000,1300] -> left=10%, top≈30.8%
    assert abs(r["left"] - 10.0) < 0.01
    assert abs(r["width"] - 50.0) < 0.01


def test_marker_page_regions_numbers_equation():
    page = FakeMarkerBlock(
        "Page",
        bbox=[0, 0, 1000, 1300],
        children=[
            FakeMarkerBlock("Equation", html="<p>E = mc^2 (3)</p>", bbox=[100, 100, 400, 150]),
        ],
    )

    regions = _marker_page_regions(page)

    assert len(regions) == 1
    assert regions[0]["label"] == "Equation 3"


def test_mineru_item_text_uses_captions_not_raw_body():
    text_item = {"type": "text", "text": "Body paragraph."}
    image_item = {"type": "image", "image_caption": ["Figure 2: an image."], "img_path": "x.png"}
    table_item = {"type": "table", "table_caption": ["Table 1: a table."], "table_body": "<table></table>"}
    equation_item = {"type": "equation", "text": "y = mx + b (5)"}

    assert _mineru_item_text(text_item) == "Body paragraph."
    assert _mineru_item_text(image_item) == "Figure 2: an image."
    assert _mineru_item_text(table_item) == "Table 1: a table."
    assert _mineru_item_text(equation_item) == "y = mx + b (5)"


def test_mineru_page_regions_normalizes_bbox_and_matches_caption():
    content_list = (
        {
            "type": "image",
            "page_idx": 0,
            "bbox": [100, 200, 600, 700],
            "image_caption": ["Figure 3: normalized bbox test."],
        },
        {
            "type": "text",
            "page_idx": 0,
            "text": "irrelevant text block",
        },
    )

    regions_by_page = _mineru_page_regions(content_list)

    assert list(regions_by_page.keys()) == [0]
    regions = regions_by_page[0]
    assert len(regions) == 1
    r = regions[0]
    # bbox 0-1000 정규화 -> 퍼센트는 /10
    assert r["label"] == "Figure 3"


def test_find_cross_page_split_with_comma_boundary():
    """리뷰어 재현 사례: 쉼표가 포함된 다음 페이지 첫 문단이 올바르게 경계에서 분할되는지 검증."""
    from services.pdf_parser import _find_cross_page_split

    current = "We measured the response under several controlled conditions."
    following = "The results, however, indicate a significant change in behavior."

    split_res = _find_cross_page_split(current + " " + following, current, following)
    assert split_res is not None
    part_curr, part_next = split_res
    assert part_curr == current
    assert part_next == following


def test_find_cross_page_split_repeating_words():
    """'the'나 공통 어휘가 앞뒤 문단 모두에 반복 등장할 때 앞쪽 단어로 오분할되지 않는지 검증."""
    from services.pdf_parser import _find_cross_page_split

    current = "The model achieves significant gains across all evaluation benchmarks in the test set."
    following = "The model parameters were optimized using the standard Adam optimizer with decay."

    split_res = _find_cross_page_split(current + " " + following, current, following)
    assert split_res is not None
    part_curr, part_next = split_res
    assert part_curr == current
    assert part_next == following


def test_find_cross_page_split_hyphen_newline():
    """하이픈 줄바꿈(예: experi-\\n mental)이 포함된 경우에도 원문 오프셋 대응을 유지하는지 검증."""
    from services.pdf_parser import _find_cross_page_split

    current = "We measured the response under several experi-\nmental conditions."
    following = "The results, however, indicate a significant change in behavior."

    split_res = _find_cross_page_split(current + " " + following, current, following)
    assert split_res is not None
    part_curr, part_next = split_res
    assert part_curr == current
    assert part_next == following


def test_find_cross_page_split_normal_paragraph_no_split():
    """현재 페이지에만 완전히 속한 일반 문단은 분할하지 않고 None을 반환해야 함."""
    from services.pdf_parser import _find_cross_page_split

    current = "We measured the response under several controlled conditions and verified accuracy."
    following = "A completely different section begins on the next page discussing future work."

    split_res = _find_cross_page_split(current, current, following)
    assert split_res is None


def test_sanitize_mineru_pages_idempotent(monkeypatch):
    """sanitize_mineru_pages()를 2회 이상 반복 적용해도 결과가 동일하게 유지되는지(멱등성) 검증."""
    import fitz
    import os
    from services.pdf_parser import sanitize_mineru_pages

    p0_text = "We measured the response under several controlled conditions."
    p1_text = "The results, however, indicate a significant change in behavior."

    class FakePage:
        def __init__(self, text):
            self.text = text
        def get_text(self):
            return self.text

    class FakeDoc:
        def __init__(self, pages):
            self.pages = [FakePage(t) for t in pages]
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def __len__(self):
            return len(self.pages)
        def __getitem__(self, i):
            return self.pages[i]

    monkeypatch.setattr(fitz, "open", lambda path: FakeDoc([p0_text, p1_text]))
    monkeypatch.setattr(os.path, "exists", lambda path: True)

    initial_pages = [
        {
            "page_idx": 0,
            "blocks": [
                {"type": 0, "text": f"{p0_text} {p1_text}", "bbox": [0, 0, 1000, 1000]}
            ],
            "text": f"{p0_text} {p1_text}"
        },
        {
            "page_idx": 1,
            "blocks": [],
            "text": ""
        }
    ]

    import copy
    first_pass = sanitize_mineru_pages(copy.deepcopy(initial_pages), "dummy.pdf")
    assert len(first_pass[0]["blocks"]) == 1
    assert first_pass[0]["blocks"][0]["text"] == p0_text
    assert len(first_pass[1]["blocks"]) == 1
    assert first_pass[1]["blocks"][0]["text"] == p1_text

    second_pass = sanitize_mineru_pages(copy.deepcopy(first_pass), "dummy.pdf")
    assert len(second_pass[0]["blocks"]) == 1
    assert second_pass[0]["blocks"][0]["text"] == p0_text
    assert len(second_pass[1]["blocks"]) == 1
    assert second_pass[1]["blocks"][0]["text"] == p1_text


def test_match_label_from_caption_text_with_subpanel_prefix():
    """캡션 시작 부분에 subfigure 기호(예: (b), a), [A])가 섞여 있어도 라벨을 올바르게 추출하는지 검증."""
    from services.pdf_parser import _match_label_from_caption_text

    c1 = "(b) FIGURE 4 | Accumulation curves for species richness (a) and Shannon index (b)"
    lbl1, cap1 = _match_label_from_caption_text(c1)
    assert lbl1 == "Figure 4"
    assert cap1 == c1

    c2 = "a) Figure 2: Comparison of methods"
    lbl2, cap2 = _match_label_from_caption_text(c2)
    assert lbl2 == "Figure 2"

    c3 = "[A] Table 1. Summary of results"
    lbl3, cap3 = _match_label_from_caption_text(c3)
    assert lbl3 == "Table 1"


def test_mineru_page_regions_absorbs_unlabeled_adjacent_subpanels():
    """MinerU 파서 결과에서 캡션이 하단 (b) 패널에만 할당되고 상단 (a) 패널이 미매칭으로 떨어진 경우,
    인접 서브패널을 흡수하여 온전한 하나의 Figure Bounding Box로 통합하는지 검증 (리뷰어 논문 재현)."""
    content_list = (
        # 상단 (a) 서브패널: 캡션 없음 (MinerU가 분리 인식)
        {
            "type": "image",
            "page_idx": 5,
            "bbox": [136, 37, 858, 328],
            "image_caption": [],
        },
        # 하단 (b) 서브패널: 캡션 할당됨 (Figure 3)
        {
            "type": "image",
            "page_idx": 5,
            "bbox": [136, 329, 858, 618],
            "image_caption": ["FIGURE 3 | Prey composition in harbor seal diet in historical samples (gray bars)..."],
        },
    )

    regions_by_page = _mineru_page_regions(content_list)
    assert 5 in regions_by_page
    page_regions = regions_by_page[5]

    # 두 패널이 하나의 Figure 3으로 통합되어 단 1개의 영역만 생성되어야 함
    assert len(page_regions) == 1
    f3 = page_regions[0]
    assert f3["label"] == "Figure 3"
    # 복합 Figure 안전 여백 확장을 통해 좌측 마진 및 상단 (a) 라벨 위치까지 안전하게 확장되어야 함
    assert f3["left"] <= 7.0
    assert f3["top"] <= 2.6
    assert f3["width"] >= 75.0
    assert f3["height"] >= 58.1


def test_mineru_aside_and_download_metadata_filtering():
    """aside_text 블록 및 출판사 다운로드 메타데이터가 번역 스트림에서 필터링되는지 검증."""
    wiley_metadata = (
        "17487692, 0, Downloaded from https://onlinelibrary.wiley.com/doi/10.1111/mms.70069 "
        "by Goteborgs, Wiley Online Library on [07/09/2025]. See the Terms and Conditions "
        "(https://onlinelibrary.wiley.com/terms-and-conditions) on Wiley Online Library for rules of use; "
        "OA articles are governed by the applicable Creative Commons License"
    )

    # 1) is_metadata_text 검증 (280자를 초과하더라도 True 반환해야 함)
    assert len(wiley_metadata) > 280
    assert is_metadata_text(wiley_metadata, page_idx=4, paper_title="Test Title") is True

    # 2) _build_mineru_pages 검증
    content_list = [
        # 본문 블록
        {
            "type": "text",
            "page_idx": 4,
            "bbox": [100, 100, 500, 200],
            "text": "This is a legitimate paragraph in the paper body.",
        },
        # aside_text (우측 마진에 위치한 메타데이터)
        {
            "type": "aside_text",
            "page_idx": 4,
            "bbox": [968, 14, 984, 982],
            "text": wiley_metadata,
        },
        # text 타입이지만 우측 마진 & 다운로드 메타데이터인 블록
        {
            "type": "text",
            "page_idx": 4,
            "bbox": [960, 20, 980, 900],
            "text": "Downloaded from https://sciencedirect.com by University Library. Terms and Conditions apply.",
        },
    ]

    pages = _build_mineru_pages(content_list, total_pages=5)
    assert len(pages) == 5
    page4 = pages[4]

    assert "This is a legitimate paragraph" in page4["text"]
    assert "Downloaded from" not in page4["text"]
    assert "Wiley Online Library" not in page4["text"]
    assert "Terms and Conditions" not in page4["text"]
    assert len(page4["blocks"]) == 1
    assert page4["blocks"][0]["text"] == "This is a legitimate paragraph in the paper body."


def test_publication_and_sidebar_metadata_filtering():
    """논문 사이드바/여백의 출판 메타데이터(저작권, 라이선스, 데이터 가용성, 연구비, 이해상충 등)가 필터링되는지 검증."""
    editor_txt = "Editor: Aldo Corriero, Universita degli Studi di Bari Aldo Moro, ITALY"
    published_txt = "Published: June 30, 2025"
    email_txt = r"\* daire.carroll@bioenv.gu.se"
    reproduction_txt = "and reproduction in any medium, provided the original author and source are credited."
    data_avail_txt = (
        "Data availability statement: All data and code are available on GitHub: "
        "https://github.com/DaireCarroll2023/PV_Trend_Analysis and Zenodo DOI: https://doi.org/10.5281/zenodo.14945453."
    )
    funding_txt = (
        "Funding: Swedish surveys were funded by the Swedish Environmental Protection Agency, and the Swedish "
        "Agency for Marine and Water Management. Danish surveys were funded by the Danish Environmental Protection "
        "Agency. DC thanks the Wild Animal Initiative Fellowship, grant number F-2023-00005, and the Swedish "
        "Environmental Protection Agency through the Environmental Research Fund and the Swedish Research Council "
        "Formas, grant number 2024-00147. KCH was supported by the European Union MARHAB, grant no. 101135307, "
        "and the Swedish Research Council Formas, grant no. 2023-00502. There was no additional external funding "
        "received for this study."
    )
    competing_txt = "Competing interests: The authors have declared that no competing interests exist."
    body_continuation = (
        "in seal abundance. Changes in abundance may be the result of well documented environmental degradation "
        "affecting prey availability and causing regionally lowered birth rates."
    )
    body_intro = (
        "Bioindicator species are monitored in order to track changes in environmental state [1]. European seal "
        "populations have a long history of use as bioindicators due to their responsiveness to environmental factors."
    )

    # 1) is_metadata_text 개별 검증
    assert is_metadata_text(editor_txt) is True
    assert is_metadata_text(published_txt) is True
    assert is_metadata_text(email_txt) is True
    assert is_metadata_text(reproduction_txt) is True
    assert is_metadata_text(data_avail_txt) is True
    assert len(funding_txt) > 400
    assert is_metadata_text(funding_txt) is True
    assert is_metadata_text(competing_txt) is True

    # 본문 및 문장 연결 조각은 절대 메타데이터로 오판정되지 않아야 함
    assert is_metadata_text(body_continuation) is False
    assert is_metadata_text(body_intro) is False

    # 2) _build_mineru_pages 통합 검증
    content_list = [
        {"type": "text", "page_idx": 1, "bbox": [53, 119, 297, 147], "text": reproduction_txt},
        {"type": "text", "page_idx": 1, "bbox": [53, 155, 285, 224], "text": data_avail_txt},
        {"type": "text", "page_idx": 1, "bbox": [53, 231, 302, 440], "text": funding_txt},
        {"type": "text", "page_idx": 1, "bbox": [53, 446, 277, 476], "text": competing_txt},
        {"type": "text", "page_idx": 1, "bbox": [316, 118, 931, 174], "text": body_continuation},
        {"type": "text", "page_idx": 1, "bbox": [318, 224, 431, 241], "text": "Introduction"},
        {"type": "text", "page_idx": 1, "bbox": [316, 247, 941, 369], "text": body_intro},
    ]

    pages = _build_mineru_pages(content_list, total_pages=2)
    p2 = pages[1]

    # 비본문 메타데이터 블록들은 모두 제거되어야 함
    assert "reproduction in any medium" not in p2["text"]
    assert "Data availability" not in p2["text"]
    assert "Funding" not in p2["text"]
    assert "Competing interests" not in p2["text"]

    # 첫 번째 블록은 본문 문장 연결부여야 함
    assert len(p2["blocks"]) == 3
    assert p2["blocks"][0]["text"].startswith("in seal abundance.")
    assert p2["blocks"][1]["text"] == "Introduction"
    assert p2["blocks"][2]["text"].startswith("Bioindicator species are monitored")


def test_download_metadata_publisher_matching_and_body_false_positives():
    """출판사(Wiley, Willy, Elsevier 등) 및 URL이 포함된 다운로드 메타데이터는 감지하고,
    일반 본문의 'downloaded from sensors' 등은 오탐하지 않는지 검증."""
    from services.pdf_parser import _DOWNLOAD_METADATA_RE

    # 1. 실제 출판사 / URL 다운로드 슬러그는 매칭되어야 함
    assert _DOWNLOAD_METADATA_RE.search("Downloaded from Wiley Online Library")
    assert _DOWNLOAD_METADATA_RE.search("Downloaded from Willy for research")
    assert _DOWNLOAD_METADATA_RE.search("Downloaded from Elsevier on 2024-01-01")
    assert _DOWNLOAD_METADATA_RE.search("Downloaded from SpringerLink by University of Michigan")
    assert _DOWNLOAD_METADATA_RE.search("Downloaded from https://sciencedirect.com by University Library.")
    assert _DOWNLOAD_METADATA_RE.search("Downloaded from www.frontiersin.org")
    assert _DOWNLOAD_METADATA_RE.search("Downloaded from Oxford University Press")

    # 2. 일반 본문에서 센서/데이터베이스 다운로드 언급은 매칭되지 않아야 함
    sensor_sentence = (
        "Time Depth Recorders (TDRs) provide a large amount of data that are downloaded from sensors to "
        "computer systems where they are stored."
    )
    assert not _DOWNLOAD_METADATA_RE.search(sensor_sentence)
    assert is_metadata_text(sensor_sentence) is False

    # 3. Godard et al. 서론 본문 전체 블록이 메타데이터로 오판되지 않아야 함
    godard_intro = (
        "In a global warming context, studying and understanding the foraging behavior of predators and their "
        "relationships with their surrounding environment is fundamental for conservation and management programs "
        "(Runge et al., 2014). According to optimal foraging theory, individuals are expected to minimize the time "
        "spent searching for and capturing food while maximizing their energy intake (Stephens and Krebs, 1986). "
        "Aquatic predators, such as birds, reptiles, and mammals that feed underwater but must breathe at the surface, "
        "are expected to optimize their capture success within the constraints of oxygen availability (Kooyman, 2012). "
        "For 20 years, the behavior of these specific animals has been widely studied with the implementation of tags "
        "that allow the sampling of numerous data both on their dive behavior, their physiology, and their biological "
        "and physical surrounding environment. Nowadays, bio-logging devices are the most appropriate tools to provide "
        "critical information on the diving and foraging of free-ranging animals (Evans et al., 2013). Technological "
        "advances have led to size and weight reduction of autonomous devices with gains in battery lifetime and memory "
        "size as well as new variables monitored. This emergence of new data sampled at high frequency (Block et al., "
        "2011) enables the study of diving behaviors at various scales in time and space (Jonsen et al., 2007; Scheffer "
        "et al., 2012; Nowacek et al., 2016). Time Depth Recorders (TDRs) provide a large amount of data that are "
        "downloaded from sensors to"
    )
    assert is_metadata_text(godard_intro) is False


def test_cross_page_continuation_heading_guard():
    """페이지 끝단의 섹션 제목(INTRODUCTION 등)이 다음 페이지 문장과 결합되지 않고,
    실제 분할된 문장은 올바르게 결합되는지 검증."""
    from services.chunker import get_cross_page_continuation

    # 1. 이전 페이지가 INTRODUCTION 단독으로 끝난 경우 -> 결합하지 않아야 함
    p1_orphan_heading = {
        "page_num": 1,
        "text": "INTRODUCTION",
        "blocks": [{"type": 0, "text": "INTRODUCTION"}],
    }
    p2 = {
        "page_num": 2,
        "text": "computer systems where they are stored. In addition, many of these tags also sample environmental data.",
        "blocks": [{"type": 0, "text": "computer systems where they are stored. In addition, many of these tags also sample environmental data."}],
    }
    assert get_cross_page_continuation(p1_orphan_heading, p2) is None

    # 2. 마크다운 헤더, 번호 매겨진 헤더도 결합하지 않아야 함
    p1_md_heading = {
        "page_num": 1,
        "text": "# Introduction",
        "blocks": [{"type": 0, "text": "# Introduction"}],
    }
    assert get_cross_page_continuation(p1_md_heading, p2) is None

    p1_num_heading = {
        "page_num": 1,
        "text": "1. Introduction",
        "blocks": [{"type": 0, "text": "1. Introduction"}],
    }
    assert get_cross_page_continuation(p1_num_heading, p2) is None

    # 3. 실제 서론 본문 문장이 분할된 경우 -> 정상 결합되어야 함
    p1_legit = {
        "page_num": 1,
        "text": (
            "Time Depth Recorders (TDRs) provide a large amount of data that are downloaded from sensors to"
        ),
        "blocks": [{
            "type": 0,
            "text": "Time Depth Recorders (TDRs) provide a large amount of data that are downloaded from sensors to",
        }],
    }
    cont = get_cross_page_continuation(p1_legit, p2)
    assert cont is not None
    assert cont["tail_fragment"] == "Time Depth Recorders (TDRs) provide a large amount of data that are downloaded from sensors to"
    assert cont["head_fragment"] == "computer systems where they are stored."
    assert cont["stitched_sentence"] == (
        "Time Depth Recorders (TDRs) provide a large amount of data that are downloaded from sensors to "
        "computer systems where they are stored."
    )


def test_reassemble_page_from_blocks():
    """사용자 override에 따른 블록 재조립(본문, 캡션, 제외) 기능 검증."""
    from services.pdf_parser import reassemble_page_from_blocks

    page = {
        "page_num": 1,
        "text": "Initial text",
        "blocks": [
            {"bbox": [100, 100, 900, 200], "text": "Body sentence 1.", "type": 0},
            {"bbox": [100, 500, 900, 600], "text": "Figure 1. A diagram.", "type": 1},
        ],
        "ignored_blocks": [
            {"bbox": [50, 20, 200, 40], "text": "Downloaded from Wiley Online", "type": 2},
        ],
    }

    # 사용자가 'Downloaded from Wiley Online'을 본문(type 0)으로 복구하고, 'Figure 1'을 제외(type 2)로 변경
    new_blocks = [
        {"bbox": [50, 20, 200, 40], "text": "Downloaded from Wiley Online", "type": 0},
        {"bbox": [100, 100, 900, 200], "text": "Body sentence 1.", "type": 0},
        {"bbox": [100, 500, 900, 600], "text": "Figure 1. A diagram.", "type": 2},
    ]

    updated = reassemble_page_from_blocks(page, new_blocks)
    assert updated["user_edited"] is True
    assert len(updated["blocks"]) == 2
    assert updated["blocks"][0]["text"] == "Downloaded from Wiley Online"
    assert updated["blocks"][1]["text"] == "Body sentence 1."
    assert len(updated["ignored_blocks"]) == 1
    assert updated["ignored_blocks"][0]["text"] == "Figure 1. A diagram."
    assert "Downloaded from Wiley Online\n\nBody sentence 1." in updated["text"]
    assert "Figure 1" not in updated["text"]


def test_clear_page_translation_isolates_pages(tmp_path, monkeypatch):
    """특정 페이지만 번역 캐시와 DB가 삭제되고 다른 페이지는 유지되는지 검증."""
    from config import CACHE_DIR
    from services.cache import save_translation_cache, get_cached_translation, clear_page_translation_cache
    from services.db import db_save_translation, db_get_translation, db_clear_page_translation

    doc_id = "test-doc-page-isolation"
    # 캐시 파일 생성
    save_translation_cache(doc_id, 1, "Page 1 Korean", suffix="ko_academic")
    save_translation_cache(doc_id, 2, "Page 2 Korean", suffix="ko_academic")
    save_translation_cache(doc_id, 10, "Page 10 Korean", suffix="ko_academic")

    # DB 저장
    db_save_translation(doc_id, 1, "Page 1 Korean", suffix="ko_academic")
    db_save_translation(doc_id, 2, "Page 2 Korean", suffix="ko_academic")
    db_save_translation(doc_id, 10, "Page 10 Korean", suffix="ko_academic")

    # 1페이지만 삭제
    clear_page_translation_cache(doc_id, 1)
    db_clear_page_translation(doc_id, 1)

    # 1페이지는 삭제되어야 함
    assert get_cached_translation(doc_id, 1, suffix="ko_academic") is None
    assert db_get_translation(doc_id, 1, suffix="ko_academic") is None

    # 2페이지와 10페이지는 유지되어야 함 (10이 1로 시작하지만 접두사 오탐 방지)
    assert get_cached_translation(doc_id, 2, suffix="ko_academic") == "Page 2 Korean"
    assert db_get_translation(doc_id, 2, suffix="ko_academic") == "Page 2 Korean"
    assert get_cached_translation(doc_id, 10, suffix="ko_academic") == "Page 10 Korean"
    assert db_get_translation(doc_id, 10, suffix="ko_academic") == "Page 10 Korean"

    # 정리
    clear_page_translation_cache(doc_id, 2)
    clear_page_translation_cache(doc_id, 10)
    db_clear_page_translation(doc_id, 2)
    db_clear_page_translation(doc_id, 10)


