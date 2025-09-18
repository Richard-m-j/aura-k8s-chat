# Dockerfile

# ---- Stage 1: The Builder ----
FROM python:3.11-slim-bookworm AS builder

# Combine all build-time operations into a single RUN command to create one layer.
RUN apt-get update && \
    apt-get install -y --no-install-recommends tini curl unzip gnupg python3-venv && \
    curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && \
    install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl && \
    curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" && \
    unzip awscliv2.zip && \
    ./aws/install && \
    rm -rf kubectl awscliv2.zip aws /var/lib/apt/lists/*

# Create and populate the virtual environment.
COPY requirements.txt .
RUN python3 -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt


# ---- Stage 2: The Final Image ----
FROM python:3.11-slim-bookworm

# Set environment variables for the runtime using the modern KEY=VALUE format.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/opt/venv/bin:$PATH"

# Create a non-root user and group in a single layer with the corrected command.
RUN groupadd --system --gid 1001 appuser && useradd --system --uid 1001 --gid appuser appuser

# Copy all necessary binaries and libraries from the builder stage.
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /usr/local /usr/local
COPY --from=builder /usr/bin/tini /usr/bin/tini

# Create app directory, copy source code, and set ownership.
WORKDIR /app
COPY --chown=appuser:appuser . .

# Switch to the non-root user
USER appuser

# Set tini as the entrypoint to manage processes correctly.
ENTRYPOINT ["/usr/bin/tini", "--"]

# The default command to run, which tini will manage.
CMD ["tail", "-f", "/dev/null"]