# Imagem de produção — Encanto em Casa (backend Flask + frontend estático)
#
# O Flask serve o front-end (pasta frontend/) junto com a API, exatamente
# como em desenvolvimento (ver backend/app.py) — não precisa de um segundo
# servidor/container para o front-end.
FROM python:3.11-slim

WORKDIR /app

# Dependências do sistema exigidas pelo psycopg2-binary e pela geração de PDF (reportlab)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY frontend/ frontend/

WORKDIR /app/backend

ENV PYTHONUNBUFFERED=1 \
    FLASK_DEBUG=0

EXPOSE 8080

# 2 workers é suficiente para o piloto (plano Nano do Supabase aceita até 60
# conexões diretas — ver schema_postgres.sql / SETUP_INTEGRACOES.md).
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "60", "app:app"]
