# Stage 1: Build the virtual environment
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Install uv (faster than pip)
RUN apt-get update && apt-get install -y curl && \
    curl -LsSf https://astral.sh/uv/install.sh | sh && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy project files and install dependencies into a virtual environment
COPY pyproject.toml uv.lock ./
RUN /root/.cargo/bin/uv venv && \
    /root/.cargo/bin/uv sync --system --no-dev

# -----------------------------------------------------------------------------

# Stage 2: Create the final production image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Create a non-root user for security
RUN useradd --create-home --shell /bin/bash appuser
USER appuser

# Copy the virtual environment from the builder stage
COPY --from=builder /app/.venv /.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy the application source code
COPY . .

# Expose the port the app runs on
EXPOSE 8000

# Set the command to run the application
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]