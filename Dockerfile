# Dockerfile
# ---- Stage 1: The Builder ----
FROM python:3.11-slim-bookworm AS builder
# Set a working directory
WORKDIR /app
RUN apt-get update && \
    apt-get install -y --no-install-recommends tini curl gnupg python3-venv && \
    curl -Lo /usr/local/bin/kubectl "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && \
    chmod +x /usr/local/bin/kubectl && \
    # Clean up apt cache to reduce image size
    rm -rf /var/lib/apt/lists/*
# Copy only the requirements file first to leverage the build cache
COPY requirements.txt .
# Create and populate the virtual environment in a single RUN layer
RUN python3 -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# ---- Stage 2: The Final Image ----
FROM python:3.11-slim-bookworm
# Set environment variables, create user, copy files, and set permissions in combined layers
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"
# Create non-root user, copy files from builder, set working directory and permissions
RUN groupadd --system --gid 1001 appuser && \
    useradd --system --uid 1001 --gid appuser appuser && \
    mkdir -p /app && \
    chown appuser:appuser /app
# Copy all necessary files from builder stage in a single layer
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /usr/local/bin/kubectl /usr/local/bin/kubectl
COPY --from=builder /usr/bin/tini /usr/bin/tini
# Set working directory and switch to non-root user
WORKDIR /app
USER appuser
# Copy application code
COPY . .
# Set tini as the entrypoint and expose port
ENTRYPOINT ["/usr/bin/tini", "--"]
EXPOSE 8000
# Command to run the application
CMD ["uvicorn", "k8s-chat-app:app", "--host", "0.0.0.0", "--port", "8000"]