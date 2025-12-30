# Dockerfile for AI Voice Gateway
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    git \
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

# Run the gateway service - app.py uses get_app() to select Pipecat or legacy based on USE_PIPECAT env var
CMD ["python", "-m", "uvicorn", "services.gateway.app:get_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
