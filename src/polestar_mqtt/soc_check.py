"""Compatibility entry point for the Data Portal runonce command (including MQTT)."""

from polestar_mqtt.runonce import main


if __name__ == "__main__":
    raise SystemExit(main())
