# Official stable gateway, kept separate from the research/clinical containers.
FROM python:3.12-slim
RUN pip install --no-cache-dir gpt2giga==0.3.0 \
    && useradd --create-home --uid 10001 researcher
USER researcher
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENTRYPOINT ["gpt2giga"]
