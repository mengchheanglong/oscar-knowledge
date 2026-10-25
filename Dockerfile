FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
COPY requirements.lock ./
COPY app ./app
RUN pip install --no-cache-dir -c requirements.lock . && useradd --uid 10001 --create-home knowledge
COPY alembic.ini ./
COPY migrations ./migrations
COPY fixtures ./fixtures
COPY manifests ./manifests
USER 10001
EXPOSE 8010
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010", "--no-access-log", "--limit-concurrency", "32"]
