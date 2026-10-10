# Data Portal on Synology

Build this branch using `Dockerfile` and import the resulting image into Synology
Container Manager. The published `latest` image may still contain the old runtime.
Use `docker-compose_example.yml` as the configuration reference.

Set the Data Portal credentials from `.env.example` and MQTT settings from the
Compose example. Mount a persistent directory at `/local-files` and grant the
container user (UID 999) write access for the topic inventory. Optional OpenAPI
and CSV mapping overrides also belong in this directory.

The current image executes one Data Portal cycle and exits. Disable automatic
restart. Persistent polling, container LWT and separate openWB forwarding remain
pending; this branch is not yet a continuous gateway service.
