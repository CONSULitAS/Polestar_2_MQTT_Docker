# Builder der aus poetry eine requirements.txt generiert, die pip einfach verarbeiten kann
FROM python:3-slim AS builder

# Bei Fehlermeldungen in der Bash abbrechen
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Poetry (und pipx für die installation von poetry) installieren 
RUN apt-get update && apt-get install --no-install-recommends --yes pipx
RUN pipx install poetry; \
    pipx inject poetry poetry-plugin-export; \
    pipx ensurepath

ENV PATH=/root/.local/bin:$PATH


# Testen das alles richtig installiert wurde
RUN python3 --version; \
  pip3 --version; \
  pipx --version; \
  poetry --version

WORKDIR /app

COPY pyproject.toml poetry.lock ./

RUN poetry export --without dev --format=requirements.txt > /app/requirements.txt;

######
# Verwenden eines offiziellen Python Basisimages
FROM python:3-slim

RUN groupadd -g 999 python && \
    useradd -r -u 999 -g python python

# Arbeitsverzeichnis im Container setzen
WORKDIR /app

# Aktivieren des Virtualenv
ENV PATH="/app/venv/bin:$PATH"

# Kopieren des Python-Skripts und der Requirements nach WORKDIR
COPY --from=builder /app/requirements.txt ./requirements.txt
COPY polestar2MqttDocker ./

# Python Virtualenv einrichten
# installieren der erforderlichen Python-Pakete
RUN <<EOF
    python -m venv venv
    pip -q install -r requirements.txt
EOF

USER 999

# Befehl, der beim Start des Containers ausgeführt wird
CMD ["python", "-u", "/app/main.py"]

# ***** EOF *****
