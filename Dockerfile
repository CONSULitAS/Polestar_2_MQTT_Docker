# Verwenden eines offiziellen Python Basisimages
FROM python:3.9-slim

# Arbeitsverzeichnis im Container setzen
WORKDIR /app

# Kopieren des Python-Skripts in das Arbeitsverzeichnis des Containers
COPY Polestar_2_MQTT.py .

# Installieren der erforderlichen Python-Pakete
RUN pip install requests

# Befehl, der beim Start des Containers ausgeführt wird
CMD ["python", "./Polestar_2_MQTT.py"]