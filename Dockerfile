# Dockerfile

# ---- Stage 1: The Builder ----
FROM python:3.11-slim-bookworm AS builder

# Set a working directory
WORKDIR /app

# Combine all package installation and cleanup into a single RUN layer
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

# Set environment variables in a single layer
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Create a non-root user and group
RUN groupadd --system --gid 1001 appuser && useradd --system --uid 1001 --gid appuser appuser

# Copy necessary files from the builder stage
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /usr/local/bin/kubectl /usr/local/bin/kubectl
COPY --from=builder /usr/bin/tini /usr/bin/tini

# Set the working
# directory and give ownership to the appuser
WORKDIR /app
RUN chown appuser:appuser /app

# Switch to the non-root user
USER appuser

# Copy the rest of the application code
COPY . .

# Set tini as the entrypoint for proper signal handling
ENTRYPOINT ["/usr/bin/tini", "--"]

# Expose the port the app runs on
EXPOSE 8000

# CORRECTED FINAL COMMAND
CMD ["/opt/venv/bin/gunicorn", "-k", "uvicorn.workers.UvicornWorker", "k8s-chat-app:app", "--bind", "0.0.0.0:8000"]