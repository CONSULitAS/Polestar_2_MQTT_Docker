# Verwenden eines offiziellen Python Basisimages
FROM python:3-slim

RUN groupadd -g 999 python && \
    useradd -r -u 999 -g python python

# Arbeitsverzeichnis im Container setzen
WORKDIR /app

# Aktivieren des Virtualenv
ENV PATH="/app/venv/bin:$PATH"

# Kopieren des Python-Skripts und der Requirements nach WORKDIR
COPY src ./

# Python Virtualenv einrichten
# Basissystem aktualisieren
# pip upgraden
# installieren der erforderlichen Python-Pakete
RUN <<EOF
    python -m venv venv
    apt update -qq -y && apt upgrade -qq -y
    pip -q install --upgrade pip
    pip -q install -r requirements.txt
EOF

USER 999

# Dummy für den Healthcheck, der immer erfolgreich ist (TODO: echten Healthcheck implementieren)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Befehl, der beim Start des Containers ausgeführt wird
CMD ["python", "-u", "/app/Polestar_2_MQTT.py"]

# ***** EOF *****
