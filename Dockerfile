FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files and directories directly from root
COPY main.py .
COPY app/ ./app/
COPY models/ ./models/

EXPOSE 8000

ENV PYTHONUNBUFFERED=1

COPY . .

# Tell Uvicorn to load main:app directly
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]