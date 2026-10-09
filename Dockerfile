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
COPY api/Polestar_DataPortalAPI.json ./api/Polestar_DataPortalAPI.json

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

# Befehl, der beim Start des Containers ausgeführt wird
CMD ["python", "-u", "/app/Polestar_2_MQTT.py"]

# ***** EOF *****
