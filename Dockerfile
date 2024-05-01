# Verwenden eines offiziellen Python Basisimages
FROM python:3.12.2-slim

RUN groupadd -g 999 python && \
    useradd -r -u 999 -g python python

# Arbeitsverzeichnis im Container setzen
WORKDIR /app

# Aktivieren des Virtualenv
ENV PATH="/app/venv/bin:$PATH"

# Kopieren des Python-Skripts und der Requirements nach WORKDIR
COPY Polestar_2_MQTT.py requirements.txt ./

# Python Virtualenv einrichten
# Basissystem aktualisieren
# pip upgraden
# Installieren der erforderlichen Python-Pakete
RUN <<EOF
    RUN python -m venv venv
    apt update && apt upgrade -y
    pip install --upgrade pip
    pip install -r requirements.txt
EOF

USER 999

# Befehl, der beim Start des Containers ausgeführt wird
CMD ["python", "-u", "/app/Polestar_2_MQTT.py"]

# ***** EOF *****
