FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY data/ /app/data/
COPY export/ /app/export/
COPY web/ /app/web/

EXPOSE 8080
CMD ["python", "web/server.py"]
