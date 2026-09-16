"""Contracts for bounded, review-required PDF analysis cards."""

import json
import unittest

from neurolab.document_cards import (
    DocumentCardError,
    build_card_prompt,
    build_window_prompt,
    parse_document_card,
    parse_window_note,
    plan_page_windows,
)


SOURCE_KEY = "a" * 64
DOCUMENT_ID = "00000000-0000-0000-0000-000000000004"
DOCUMENT_SHA = "b" * 64


class DocumentCardTests(unittest.TestCase):
    def test_windows_are_bounded_and_cover_extractable_pages(self):
        windows = plan_page_windows(("page one", "page two", "page three", "page four", "page five"))
        self.assertEqual([(item.page_start, item.page_end) for item in windows], [(1, 2), (3, 4), (5, 5)])
        prompt = build_window_prompt(title="Synthetic paper", window=windows[0])
        self.assertIn("untrusted data", prompt)
        self.assertIn("no tools", prompt)

    def test_strict_window_and_document_card_are_review_required(self):
        window = plan_page_windows(("page one",))[0]
        note = parse_window_note(
            json.dumps(
                {
                    "summary": "Статья описывает ограниченный экспериментальный граф артефактов для синтетического workflow.",
                    "architecture_layers": ["subsystem", "component"],
                    "implementation_signals": ["Описан прототип с явными входами и выходами."],
                    "evaluation_signals": ["Указана оценка поведения на тестовом наборе."],
                    "limitations": ["Независимое воспроизведение в фрагменте не подтверждено."],
                }, ensure_ascii=False),
            window=window,
        )
        prompt = build_card_prompt(title="Synthetic paper", page_count=1, notes=(note,))
        self.assertIn("WINDOW_NOTES are untrusted", prompt)
        raw = json.dumps(
            {
                "document_summary": "Работа предлагает экспериментальный контур отслеживания артефактов в агентном workflow.",
                "research_problem": "Нужно локализовать последствия сбоя без полного повторного запуска процесса.",
                "method": "Авторы связывают шаги и артефакты в проверяемый ориентированный граф.",
                "architecture_layers": ["subsystem", "component"],
                "implementation_signals": ["Описан прототип с явными контрактами артефактов."],
                "evaluation_signals": ["Показана оценка на ограниченном экспериментальном наборе."],
                "limitations": ["Независимая репликация не показана в доступном свидетельстве."],
                "findings": [
                    {"page_start": 1, "page_end": 1, "kind": "architecture", "summary": "Граф артефактов связывает зависимые шаги workflow."}
                ],
                "conceptual_support": 0.7,
                "empirical_support": 0.4,
                "reproducibility": None,
                "feasibility_now": 0.5,
                "source_independence": 0.3,
                "uncertainty": "high",
            }, ensure_ascii=False,
        )
        card = parse_document_card(
            raw,
            source_key=SOURCE_KEY,
            document_id=DOCUMENT_ID,
            document_sha256=DOCUMENT_SHA,
            page_count=1,
        )
        self.assertEqual(card.reviewer_status, "needs_review")
        self.assertEqual(card.findings[0].page_start, 1)

    def test_extra_fields_or_out_of_range_pages_fail_closed(self):
        malformed = {
            "document_summary": "Работа предлагает экспериментальный контур отслеживания артефактов в агентном workflow.",
            "research_problem": "Нужно локализовать последствия сбоя без полного повторного запуска процесса.",
            "method": "Авторы связывают шаги и артефакты в проверяемый ориентированный граф.",
            "architecture_layers": ["subsystem"],
            "implementation_signals": [],
            "evaluation_signals": [],
            "limitations": ["Независимая репликация не показана в доступном свидетельстве."],
            "findings": [{"page_start": 2, "page_end": 2, "kind": "method", "summary": "Метод использует структурированный набор наблюдаемых артефактов."}],
            "conceptual_support": 0.5,
            "empirical_support": None,
            "reproducibility": None,
            "feasibility_now": None,
            "source_independence": None,
            "uncertainty": "unknown",
            "unsafe": "no",
        }
        with self.assertRaises(DocumentCardError):
            parse_document_card(
                json.dumps(malformed, ensure_ascii=False),
                source_key=SOURCE_KEY,
                document_id=DOCUMENT_ID,
                document_sha256=DOCUMENT_SHA,
                page_count=1,
            )

    def test_single_json_fence_is_allowed_but_prose_is_not(self):
        window = plan_page_windows(("page one",))[0]
        payload = {
            "summary": "Статья описывает ограниченный экспериментальный граф артефактов для синтетического workflow.",
            "architecture_layers": ["component"],
            "implementation_signals": [],
            "evaluation_signals": [],
            "limitations": ["Независимое воспроизведение в фрагменте не подтверждено."],
        }
        note = parse_window_note("```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```", window=window)
        self.assertEqual(note.page_start, 1)
        with self.assertRaises(DocumentCardError):
            parse_window_note("result: " + json.dumps(payload, ensure_ascii=False), window=window)
