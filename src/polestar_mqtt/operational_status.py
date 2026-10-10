"""Retained operational status, separate from the telemetry inventory."""

from polestar_mqtt.credential_expiry import CredentialExpiryMonitor, CredentialStatus


def configure_last_will(client, base_topic):
    client.will_set(base_topic.rstrip("/") + "/container/connected",
                    "offline", qos=1, retain=True)


class OperationalStatus:
    """Publish only local status codes and known exception class names."""

    def __init__(self, publisher, config):
        self.publisher = publisher
        self.root = config.mqtt_base_topic.rstrip("/") + "/container"
        self.credential = CredentialExpiryMonitor().check(config.client_secret_expires_at)
        self.count = 0
        self.errors = []
        self.exceptions = []

    def publish(self, suffix, value):
        self.publisher.publish(self.root + "/" + suffix, value, qos=1, retain=True)
        self.count += 1

    def start(self):
        self.publish("connected", "online")
        self.publish("credentials/client_secret_expires_at",
                     self.credential.expires_at.isoformat().replace("+00:00", "Z"))
        self.publish("credentials/client_secret_days_remaining",
                     str(self.credential.days_remaining))
        self.publish("credentials/client_secret_status", self.credential.status.value)

    def result(self, *, battery_timestamp=None, failures=None, fatal_error=None,
               source_time_unknown=False):
        if fatal_error is not None:
            self.errors = ["api_failed"]
            self.exceptions = [type(fatal_error).__name__]
        elif failures:
            self.errors = ["api_partial"]
            self.exceptions = sorted(set(failures.values()))
        if battery_timestamp is not None:
            self.publish("last_update", battery_timestamp)
        if self.credential.status == CredentialStatus.EXPIRED:
            self.errors.append("credential_expired")
        elif self.credential.days_remaining <= 14:
            self.errors.append("credential_expiring")
        if source_time_unknown:
            self.errors.append("source_time_unknown")
        self.publish_errors()

    def publish_errors(self):
        self.publish("last_error", ";".join(self.errors))
        self.publish("last_exception", ";".join(self.exceptions))

    def failure(self, error):
        self.errors.insert(0, "publication_failed")
        self.exceptions.insert(0, type(error).__name__)
        self.publish_errors()

    def stop(self):
        self.publish("connected", "offline")
