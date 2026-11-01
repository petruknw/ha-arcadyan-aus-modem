"""Polls the modem's MAC filter."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import (
    NO_FILTER,
    FilterState,
    FilterUnavailable,
    InvalidAuth,
    LoginLocked,
    ModemClient,
    ModemError,
    SessionBusy,
)
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

# Long enough for someone to finish on the modem's web page.
MAX_SKIPPED_UPDATES = 3

type ArcadyanModemConfigEntry = ConfigEntry[ArcadyanModemCoordinator]


def get_modem_lock(hass: HomeAssistant, host: str) -> asyncio.Lock:
    """Return the lock for a modem, which outlives reloads because the modem does."""
    return hass.data.setdefault(DOMAIN, {}).setdefault(host, asyncio.Lock())


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
        self._skipped_updates = 0

    async def _async_update_data(self) -> FilterState:
        try:
            state = await self.client.async_read()
        except InvalidAuth as err:
            # Stops polling, so a wrong password can't lock the modem's login.
            raise ConfigEntryAuthFailed(str(err)) from err
        except (SessionBusy, LoginLocked) as err:
            # Someone on the modem's web page shouldn't turn every switch unavailable.
            if self.data is not None and self._skipped_updates < MAX_SKIPPED_UPDATES:
                self._skipped_updates += 1
                _LOGGER.debug("Skipping this update: %s", err)
                return self.data
            raise UpdateFailed(str(err)) from err
        except FilterUnavailable as err:
            # The reboot action doesn't need the filter, so setup still succeeds.
            _LOGGER.debug("No MAC filter: %s", err)
            state = NO_FILTER
        except ModemError as err:
            raise UpdateFailed(str(err)) from err
        self._skipped_updates = 0
        return state
