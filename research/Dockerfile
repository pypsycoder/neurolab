FROM python:3.12-slim

RUN useradd --create-home --uid 10001 researcher
WORKDIR /app

COPY research/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY --chown=researcher:researcher src /app/src
COPY --chown=researcher:researcher scripts/run_it_research.py /app/scripts/run_it_research.py

USER researcher
ENV PYTHONPATH=/app/src
ENTRYPOINT ["python", "/app/scripts/run_it_research.py"]
