FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ARG BUILD_SHA=dev
ARG SEMVER=0.0.0
ENV APP_VERSION=v${SEMVER}+git-${BUILD_SHA}
LABEL org.opencontainers.image.revision=${BUILD_SHA}
LABEL org.opencontainers.image.version=${SEMVER}

WORKDIR /app

# Install system dependencies for OpenCV and PostGIS
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y \
    libpq-dev \
    libgdal-dev \
    libgl1 \
    libglib2.0-0

# Install Python dependencies
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
