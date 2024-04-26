# Verwenden eines offiziellen Python Basisimages
FROM python:3.9-slim

# Arbeitsverzeichnis im Container setzen
WORKDIR /app

# Kopieren des Python-Skripts in das Arbeitsverzeichnis des Containers
COPY Polestar_2_MQTT.py .

# Installieren der erforderlichen Python-Pakete
RUN <<EOF
    apt update && apt upgrade -y
    pip install --upgrade pip
    pip install requests #time
EOF

# Befehl, der beim Start des Containers ausgeführt wird
CMD ["python", "-u", "/app/Polestar_2_MQTT.py"]

# ***** EOF *****