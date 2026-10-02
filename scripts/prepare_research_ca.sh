#!/usr/bin/env bash
# Build an application-local CA bundle; never weaken TLS or host trust settings.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
OUT="$ROOT/runtime/ca"
mkdir -p "$OUT"
curl --fail --silent --show-error --proto '=https' --tlsv1.2 --max-time 30 \
  https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt \
  --output "$OUT/russian-root.crt"
printf '%s  %s\n' 936a43fea6e8e525bcc0f81acd9c3d21b4fc4b9b68acea7906d698005afc6504 "$OUT/russian-root.crt" | sha256sum -c -
openssl x509 -in "$OUT/russian-root.crt" -noout -subject | grep -q 'Russian Trusted Root CA'
openssl x509 -in "$OUT/russian-root.crt" -noout -checkend 86400
# A generated trust artifact, not a change to /etc/ssl or certifi.
openssl crl2pkcs7 -nocrl -certfile /etc/ssl/certs/ca-certificates.crt -certfile "$OUT/russian-root.crt" |
  openssl pkcs7 -print_certs -out "$OUT/ca-certificates.crt"
openssl x509 -in "$OUT/russian-root.crt" -noout -fingerprint -sha256
echo 'research_ca: generated; host trust unchanged'
