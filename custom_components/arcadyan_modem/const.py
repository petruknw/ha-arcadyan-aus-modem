"""Constants for the Arcadyan 5G modem integration."""

from datetime import timedelta

DOMAIN = "arcadyan_modem"
DEFAULT_HOST = "192.168.1.1"
UPDATE_INTERVAL = timedelta(minutes=5)

CONF_DEVICES = "devices"
CONF_MAC = "mac"
