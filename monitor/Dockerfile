FROM python:3.13-alpine
WORKDIR /app
RUN addgroup -S neuro && adduser -S -G neuro neuro
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY monitor.py ./
USER neuro
CMD ["python", "monitor.py"]
