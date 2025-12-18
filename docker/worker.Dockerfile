FROM python:3.11-slim

WORKDIR /app

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

COPY pyproject.toml README.md SECURITY.md /app/
COPY src /app/src

RUN python -m pip install --upgrade pip && \
    python -m pip install -e ".[postgres]"

# Install optional forensic utilities (best-effort; modules are feature-gated)
# Note: Debian/Ubuntu provide `exiftool` via `libimage-exiftool-perl`.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      binutils \
      file \
      libmagic1 \
      libimage-exiftool-perl \
      tshark \
      foremost \
    ; \
    # Optional tools that may not exist in all repos (do not fail the image build):
    apt-get install -y --no-install-recommends bulk-extractor || true; \
    apt-get install -y --no-install-recommends yara || true; \
    rm -rf /var/lib/apt/lists/*

CMD ["python", "-m", "eviforge.worker"]
