"""The Arcadyan 5G modem integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant

from .client import ModemClient
from .coordinator import ArcadyanModemConfigEntry, ArcadyanModemCoordinator

PLATFORMS = [Platform.SWITCH]


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
