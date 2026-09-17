API Documentation
M2M and Telemetry APIs for the EU Data Act Developer Portal Sandbox.
All requests require a Bearer token in the Authorization header.
Base URL
https://pc-api.polestar.com/eu-north-1/data-portal/m2m
Account ID / x-client-id
a2c75124-4e38-451b-a73c-5a6d7f49c109
Raw OpenAPI spec
/de/api-credentials/docs/openapi
API Rate limits
Maximum of 10,000 API calls per client, per day.

## Anwendungseinrichtung
Erstellen Sie eine Anwendung, um auf die API zuzugreifen
Bereitgestellte Zugangsdaten können sein:
* API-Schlüssel
* OAuth-Client-Zugangsdaten
## Erforderliche Header
Jede Anfrage muss enthalten:
* accept: application/json
* authorization: Bearer <access_token>
* x-api-key: <api_key>
## Genehmigung
OAuth2 wird erwartet
* Access Token muss in Anfrage-Headern enthalten sein