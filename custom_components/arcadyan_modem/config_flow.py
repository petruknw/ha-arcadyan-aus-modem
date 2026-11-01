"""Config flow for the Arcadyan 5G modem integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .client import (
    AllowListActive,
    FilterUnavailable,
    InvalidAuth,
    LoginLocked,
    ModemClient,
    ModemConnectionError,
    ModemError,
    SessionBusy,
)
from .const import CONF_DEVICES, CONF_MAC, DEFAULT_HOST, DOMAIN
from .coordinator import ArcadyanModemConfigEntry, get_modem_lock

_LOGGER = logging.getLogger(__name__)

_MAC = re.compile(r"^[0-9A-F]{2}(:[0-9A-F]{2}){5}$")
_ZERO_MAC = "00:00:00:00:00:00"

PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
        vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR,
    }
)
STEP_REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR})
STEP_ADD_DEVICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): str,
        vol.Required(CONF_MAC): str,
    }
)


def normalize_mac(value: str) -> str | None:
    """Return the address as AA:BB:CC:DD:EE:FF, or None if it isn't valid."""
    mac = value.strip().upper().replace("-", ":")
    return mac if _MAC.match(mac) and mac != _ZERO_MAC else None


async def _login_error(hass: HomeAssistant, host: str, password: str) -> str | None:
    """Try one login, and return the error key if it failed."""
    try:
        await ModemClient(host, password, get_modem_lock(hass, host)).async_validate()
    except ModemConnectionError:
        return "cannot_connect"
    except InvalidAuth:
        return "invalid_auth"
    except SessionBusy:
        return "session_busy"
    except LoginLocked:
        return "login_locked"
    except ModemError:
        _LOGGER.exception("Unexpected reply from the modem")
        return "unknown"
    return None


class ArcadyanModemConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the modem."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ArcadyanModemConfigEntry,
    ) -> ArcadyanModemOptionsFlow:
        """Return the flow that manages devices."""
        return ArcadyanModemOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the host and password, and test them once."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._async_abort_entries_match({CONF_HOST: user_input[CONF_HOST]})
            error = await _login_error(
                self.hass, user_input[CONF_HOST], user_input[CONF_PASSWORD]
            )
            if error is None:
                return self.async_create_entry(title="Arcadyan modem", data=user_input)
            errors["base"] = error

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start again after the modem rejects the saved password."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the new password, and test it once."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            error = await _login_error(
                self.hass, entry.data[CONF_HOST], user_input[CONF_PASSWORD]
            )
            if error is None:
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm", data_schema=STEP_REAUTH_SCHEMA, errors=errors
        )


class ArcadyanModemOptionsFlow(OptionsFlowWithReload):
    """Adds and removes devices."""

    @property
    def _devices(self) -> list[dict[str, Any]]:
        return list(self.config_entry.options.get(CONF_DEVICES, []))

    async def _async_unblock(self, mac: str) -> bool:
        """Return True once the address is off the block list, or there isn't one."""
        if self.config_entry.state is not ConfigEntryState.LOADED:
            return False
        try:
            await self.config_entry.runtime_data.client.async_set_blocked([mac], False)
        except (AllowListActive, FilterUnavailable):
            return True
        except ModemError:
            return False
        return True

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose what to do."""
        menu = ["add_device"]
        if self._devices:
            menu.append("remove_device")
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_add_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a device."""
        errors: dict[str, str] = {}
        if user_input is not None:
            devices = self._devices
            mac = normalize_mac(user_input[CONF_MAC])
            if mac is None:
                errors[CONF_MAC] = "invalid_mac"
            elif any(device[CONF_MAC] == mac for device in devices):
                errors[CONF_MAC] = "already_added"
            else:
                device = {CONF_NAME: user_input[CONF_NAME].strip(), CONF_MAC: mac}
                return self.async_create_entry(
                    data={CONF_DEVICES: [*devices, device]}
                )

        return self.async_show_form(
            step_id="add_device",
            data_schema=self.add_suggested_values_to_schema(
                STEP_ADD_DEVICE_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_remove_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove a device and take it off the block list, or it'd stay on with no switch."""
        errors: dict[str, str] = {}
        devices = self._devices
        if user_input is not None:
            mac = user_input[CONF_MAC]
            if await self._async_unblock(mac):
                registry = er.async_get(self.hass)
                entity_id = registry.async_get_entity_id(
                    "switch", DOMAIN, f"{self.config_entry.entry_id}_{mac}"
                )
                if entity_id:
                    registry.async_remove(entity_id)
                return self.async_create_entry(
                    data={
                        CONF_DEVICES: [
                            device for device in devices if device[CONF_MAC] != mac
                        ]
                    }
                )
            errors["base"] = "not_ready"

        schema = vol.Schema(
            {
                vol.Required(CONF_MAC): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(
                                value=device[CONF_MAC], label=device[CONF_NAME]
                            )
                            for device in devices
                        ]
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="remove_device", data_schema=schema, errors=errors
        )
