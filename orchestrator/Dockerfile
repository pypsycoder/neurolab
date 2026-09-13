FROM python:3.13-alpine
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# GigaChat is served with a certificate chain rooted in the Russian trusted CA.
# Trust it only inside this workload; TLS verification remains enabled.
RUN apk add --no-cache ca-certificates curl \
    && curl --fail --silent --show-error --location --insecure \
      https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt \
      --output /usr/local/share/ca-certificates/russian-trusted-root-ca.crt \
    && update-ca-certificates \
    && addgroup -S neuro && adduser -S -G neuro neuro
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY worker.py probe_models.py ./
USER neuro
CMD ["python", "worker.py"]
