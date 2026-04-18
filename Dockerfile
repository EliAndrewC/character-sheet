FROM python:3.12-slim

WORKDIR /app

# System dependencies for the character-import pipeline:
#   antiword - legacy Microsoft .doc extraction (import-design §6)
#   libmagic1 - file-type detection for uploaded documents
RUN apt-get update \
    && apt-get install -y --no-install-recommends antiword libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
