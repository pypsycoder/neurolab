import json
import unittest

from neurolab.diagram_cards import DiagramCardError, candidate_diagram_pages, parse_diagram_card


class DiagramCardsTests(unittest.TestCase):
    def test_candidate_pages_use_conservative_figure_cues(self):
        self.assertEqual(candidate_diagram_pages(("intro", "Figure 1 workflow", "architecture")), (2, 3))

    def test_sparse_page_in_text_dense_paper_is_a_bounded_layout_candidate(self):
        dense = "x" * 3000
        pages = (dense, dense, "diagram-like page " + "x" * 500, dense)
        self.assertEqual(candidate_diagram_pages(pages), (3,))

    def test_strict_visual_card_requires_known_shape(self):
        raw = json.dumps({"diagram_kind":"workflow","summary":"Схема показывает последовательный workflow с обратной связью.","components":["Сбор данных"],"connections":["Сбор данных передаёт результат в проверку."],"feedback_or_control":["Ошибка возвращает поток к проверке."],"limitations":["Локальные алгоритмы блоков на схеме не раскрыты."]})
        card = parse_diagram_card(raw, source_key="a" * 64, document_id="00000000-0000-0000-0000-000000000004", document_sha256="b" * 64, page_number=1, image_bytes=b"png")
        self.assertEqual(card.reviewer_status, "needs_review")
        with self.assertRaises(DiagramCardError):
            parse_diagram_card(raw[:-1] + ',"unsafe":true}', source_key="a" * 64, document_id="x", document_sha256="b" * 64, page_number=1, image_bytes=b"png")
