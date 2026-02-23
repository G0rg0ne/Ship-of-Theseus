FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user for running the app
RUN groupadd --gid 1000 app && useradd --uid 1000 --gid app --shell /bin/bash --create-home app \
    && chown -R app:app /app

# Expose port
EXPOSE 8000

USER app

# Run with uvicorn (production-ready with multiple workers)
# Listen on 0.0.0.0 for access from host when port is mapped
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

