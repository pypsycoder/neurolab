FROM python:3.12-slim

RUN useradd --create-home --uid 10001 researcher
WORKDIR /app

COPY research/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY --chown=researcher:researcher src /app/src
COPY --chown=researcher:researcher scripts/run_it_research.py /app/scripts/run_it_research.py
COPY --chown=researcher:researcher scripts/verify_open_access_pdf.py /app/scripts/verify_open_access_pdf.py
COPY --chown=researcher:researcher scripts/run_arxiv_fulltext_cycle.py /app/scripts/run_arxiv_fulltext_cycle.py
COPY --chown=researcher:researcher scripts/record_reviewed_claim.py /app/scripts/record_reviewed_claim.py
COPY --chown=researcher:researcher scripts/verify_public_repository.py /app/scripts/verify_public_repository.py
COPY --chown=researcher:researcher research/test_pdf_contract.py /app/tests/test_pdf_contract.py

USER researcher
ENV PYTHONPATH=/app/src
ENTRYPOINT ["python", "/app/scripts/run_it_research.py"]
