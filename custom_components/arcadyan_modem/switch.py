"""A switch for each device: on blocks it from the main Wi-Fi."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import ModemError
from .const import CONF_DEVICES, CONF_MAC, DOMAIN
from .coordinator import ArcadyanModemConfigEntry, ArcadyanModemCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ArcadyanModemConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a switch for each device."""
    async_add_entities(
        BlockDeviceSwitch(entry.runtime_data, entry.entry_id, device)
        for device in entry.options.get(CONF_DEVICES, [])
    )


class BlockDeviceSwitch(CoordinatorEntity[ArcadyanModemCoordinator], SwitchEntity):
    """Blocks one device."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:wifi-lock"

    def __init__(
        self,
        coordinator: ArcadyanModemCoordinator,
        entry_id: str,
        device: dict[str, Any],
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._mac: str = device[CONF_MAC]
        self._attr_name = f"Block {device[CONF_NAME]}"
        self._attr_unique_id = f"{entry_id}_{self._mac}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Arcadyan modem",
            manufacturer="Arcadyan",
        )

    @property
    def is_on(self) -> bool:
        """Return True while the modem is blocking the device."""
        return self.coordinator.data.blocks(self._mac)

    async def _async_set(self, blocked: bool) -> None:
        try:
            state = await self.coordinator.client.async_set_blocked(
                [self._mac], blocked
            )
        except ModemError as err:
            raise HomeAssistantError(str(err)) from err
        self.coordinator.async_set_updated_data(state)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Block the device. The modem's Wi-Fi restarts to apply this."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Unblock the device. The modem's Wi-Fi restarts to apply this."""
        await self._async_set(False)
