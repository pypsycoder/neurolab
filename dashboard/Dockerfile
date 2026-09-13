FROM python:3.13-alpine
WORKDIR /app
RUN addgroup -S neuro && adduser -S -G neuro neuro
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py ./
COPY static ./static
USER neuro
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
