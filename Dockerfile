# Dockerfile for AI Voice Gateway
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY pyproject.toml ./

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e .

# Copy application code
COPY shared/ ./shared/
COPY services/ ./services/

# Expose port
EXPOSE 8000

# Run the gateway service
CMD ["python", "-m", "uvicorn", "services.gateway.app:app", "--host", "0.0.0.0", "--port", "8000"]
