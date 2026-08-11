FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY catalog ./catalog
COPY docker ./docker
RUN pip install --no-cache-dir uv && uv sync --locked --no-dev
# The application creates its default data directory during startup.  Own it
# before dropping privileges; the proxy and application remain separate, with
# only the proxy listening on the container interface.
RUN mkdir -p /app/data && chown 65532:65532 /app/data
USER 65532:65532
EXPOSE 8777
CMD ["python", "docker/loopback_proxy.py"]
