# Wazi — Application Dockerfile
#
# Build:   docker build -t wazi-app .
# Run:     docker run -p 8000:8000 --env-file .env wazi-app

FROM python:3.11-slim

WORKDIR /app

# System dependencies for psycopg2 compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# FastAPI on 8000, Streamlit admin on 8501
EXPOSE 8000 8501

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
