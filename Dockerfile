FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Bind inside the container's own network namespace; Docker's `-p`/`ports:`
# publishing DNATs to this address, not to the host's 127.0.0.1. The
# container-external exposure is still governed by the host-side ports
# mapping (docker-compose.yml pins it to 127.0.0.1:49231), so this does not
# widen the actual network exposure.
ENV CATALOG_HOST=0.0.0.0

WORKDIR /app
COPY data/ /app/data/
COPY export/ /app/export/
COPY web/ /app/web/

EXPOSE 8080
CMD ["python", "web/server.py"]
