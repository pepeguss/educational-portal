FROM node:22-bookworm-slim AS assets
WORKDIR /build/assets
RUN npm install --global pnpm@10.17.1
COPY assets/package.json assets/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY assets/ ./
COPY templates/ /build/templates/
COPY player/templates/ /build/player/templates/
COPY users/templates/ /build/users/templates/
COPY static/js/ /build/static/js/
RUN pnpm run build

FROM python:3.14.7-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libreoffice-impress fonts-dejavu fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=assets /build/static/vendor/ /opt/portal-vendor/

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

ENTRYPOINT ["python", "docker-entrypoint.py"]
CMD ["gunicorn", "portal.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "180"]
