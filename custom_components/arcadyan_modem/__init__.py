"""The Arcadyan 5G modem integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .client import ModemClient, ModemError
from .const import DOMAIN
from .coordinator import ArcadyanModemConfigEntry, ArcadyanModemCoordinator

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [Platform.SWITCH]
SERVICE_REBOOT = "reboot"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Add the reboot action."""

    async def async_reboot(call: ServiceCall) -> None:
        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if not entries:
            raise ServiceValidationError("The modem isn't set up")
        for entry in entries:
            try:
                await entry.runtime_data.client.async_reboot()
            except ModemError as err:
                raise HomeAssistantError(str(err)) from err

    hass.services.async_register(DOMAIN, SERVICE_REBOOT, async_reboot)
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: ArcadyanModemConfigEntry
) -> bool:
    """Set up the modem."""
    client = ModemClient(entry.data[CONF_HOST], entry.data[CONF_PASSWORD])
    coordinator = ArcadyanModemCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ArcadyanModemConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
