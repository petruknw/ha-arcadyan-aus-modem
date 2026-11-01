"""Polls the modem's MAC filter."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import (
    FilterState,
    InvalidAuth,
    LoginLocked,
    ModemClient,
    ModemError,
    SessionBusy,
)
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

type ArcadyanModemConfigEntry = ConfigEntry[ArcadyanModemCoordinator]


class ArcadyanModemCoordinator(DataUpdateCoordinator[FilterState]):
    """Keeps the block list up to date."""

    config_entry: ArcadyanModemConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ArcadyanModemConfigEntry,
        client: ModemClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> FilterState:
        try:
            return await self.client.async_read()
        except InvalidAuth as err:
            # Stops polling, so a wrong password can't lock the modem's login.
            raise ConfigEntryAuthFailed(str(err)) from err
        except (SessionBusy, LoginLocked) as err:
            # Someone on the modem's web page shouldn't turn every switch unavailable.
            if self.data is not None:
                _LOGGER.debug("Skipping this update: %s", err)
                return self.data
            raise UpdateFailed(str(err)) from err
        except ModemError as err:
            raise UpdateFailed(str(err)) from err
