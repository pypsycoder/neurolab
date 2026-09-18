FROM python:3.12-slim

RUN useradd --create-home --uid 10001 researcher
WORKDIR /app

COPY research/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY --chown=researcher:researcher src /app/src
COPY --chown=researcher:researcher scripts/run_it_research.py /app/scripts/run_it_research.py
COPY --chown=researcher:researcher scripts/import_arxiv_record.py /app/scripts/import_arxiv_record.py
COPY --chown=researcher:researcher scripts/verify_open_access_pdf.py /app/scripts/verify_open_access_pdf.py
COPY --chown=researcher:researcher scripts/run_arxiv_fulltext_cycle.py /app/scripts/run_arxiv_fulltext_cycle.py
COPY --chown=researcher:researcher scripts/record_reviewed_claim.py /app/scripts/record_reviewed_claim.py
COPY --chown=researcher:researcher scripts/import_openalex_doi_record.py /app/scripts/import_openalex_doi_record.py
COPY --chown=researcher:researcher scripts/run_f1000_html_evidence.py /app/scripts/run_f1000_html_evidence.py
COPY --chown=researcher:researcher scripts/run_f1000_fulltext_cycle.py /app/scripts/run_f1000_fulltext_cycle.py
COPY --chown=researcher:researcher scripts/run_gigachat_document_card.py /app/scripts/run_gigachat_document_card.py
COPY --chown=researcher:researcher scripts/run_gigachat_diagram_cards.py /app/scripts/run_gigachat_diagram_cards.py
COPY --chown=researcher:researcher scripts/review_document_card.py /app/scripts/review_document_card.py
COPY --chown=researcher:researcher scripts/review_diagram_card.py /app/scripts/review_diagram_card.py
COPY --chown=researcher:researcher scripts/render_reviewed_card_packet.py /app/scripts/render_reviewed_card_packet.py
COPY --chown=researcher:researcher scripts/verify_public_repository.py /app/scripts/verify_public_repository.py
COPY --chown=researcher:researcher scripts/verify_evaluator_evolution_smoke.py /app/scripts/verify_evaluator_evolution_smoke.py
COPY --chown=researcher:researcher scripts/run_article_scoring_shadow.py /app/scripts/run_article_scoring_shadow.py
COPY --chown=researcher:researcher scripts/run_response_quality_shadow.py /app/scripts/run_response_quality_shadow.py
COPY --chown=researcher:researcher scripts/run_gigachat_response_quality_replay.py /app/scripts/run_gigachat_response_quality_replay.py
COPY --chown=researcher:researcher research/test_pdf_contract.py /app/tests/test_pdf_contract.py

USER researcher
ENV PYTHONPATH=/app/src
ENTRYPOINT ["python", "/app/scripts/run_it_research.py"]
