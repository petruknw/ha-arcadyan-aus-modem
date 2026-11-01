"""Client for the Wi-Fi MAC filter in an Arcadyan 5G modem's web UI.

Quirks that shape this client:
- Every page that needs a login answers 403 with the login page as its body,
  so a 403 on / is normal and is where the login token comes from.
- The modem counts bad passwords and locks the login after 5, so nothing here
  retries a login.
- Only one admin session is allowed, so each operation logs in and out, and a
  lock stops two operations overlapping.
- Saving the filter can take a minute to answer, and the Wi-Fi restarts.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Iterable
from dataclasses import dataclass
import hashlib
import logging
import re

import aiohttp
from yarl import URL

_LOGGER = logging.getLogger(__name__)

# The firmware sends this fixed username from its login page.
USERNAME = "optus"
FILTER_PAGE = "wlan_mac_filter.htm"
FILTER_CONFIG = "cgi/cgi_wlan_mac_filter.js"
# subFormWiFiMACFilter in /js/subformvar.js.
FILTER_ACTION = "ui_wireless"
REBOOT_PAGE = "system_r.htm"
# subFormSYSBoot in /js/subformvar.js. The same file defines the factory reset
# action, so never derive this value from the modem at runtime.
REBOOT_ACTION = "reboot"
# The main Wi-Fi on each band. The modem's page offers no filter for guest networks.
BANDS = ("24G1", "5G1")
MAX_MACS = 32

MODE_BLOCK = "deny"
MODE_ALLOW = "allow"
MODE_OFF = "disable"

REQUEST_TIMEOUT = 20
APPLY_TIMEOUT = 120

# Length of "data:image/gif;base64," plus the fixed 1x1 GIF. The rest is the token.
_GIF_PREFIX_LEN = 78
_GIF_SRC = re.compile(r'src="(data:image/gif;base64,[^"]+)"')
_LOGIN_FLAG = re.compile(r"var flag\s*=\s*(\d+)")

_FLAG_BAD_PASSWORD = 1
_FLAG_SESSION_BUSY = 2
_FLAG_LOCKED = 7


class ModemError(Exception):
    """The modem did not do what was asked."""


class ModemConnectionError(ModemError):
    """The modem could not be reached."""


class InvalidAuth(ModemError):
    """The modem rejected the password."""


class SessionBusy(ModemError):
    """Someone else is logged in to the modem."""


class LoginLocked(ModemError):
    """Too many bad passwords, so the login is locked for a short time."""


class AllowListActive(ModemError):
    """The modem uses an allow list, so a block list change would do the opposite."""


@dataclass(frozen=True)
class FilterState:
    """The main Wi-Fi's MAC filter. The field ids change with each session."""

    mode: str
    macs: tuple[str, ...]
    mode_ids: tuple[str, ...]
    list_ids: tuple[str, ...]

    def blocks(self, mac: str) -> bool:
        """Return True if the modem is currently blocking this address."""
        return self.mode == MODE_BLOCK and mac in self.macs


def hash_credential(value: str) -> str:
    """Return sha512(md5hex(value)), the page's do_encode(value, true)."""
    md5_hex = hashlib.md5(value.encode()).hexdigest()
    return hashlib.sha512(md5_hex.encode()).hexdigest()


def parse_token(html: str) -> str:
    """Return the token in the page's first inline GIF, as the page's own code does."""
    sources = _GIF_SRC.findall(html)
    if not sources:
        raise ModemError("No token found in page")
    try:
        token = base64.b64decode(sources[0][_GIF_PREFIX_LEN:]).decode()
    except ValueError as err:
        raise ModemError("Could not decode token") from err
    if not token:
        raise ModemError("Token is empty")
    return token


def _config_field(config: str, name: str) -> tuple[str, str]:
    match = re.search(rf'^addCfg\("{name}","([^"]*)","([^"]*)"', config, re.MULTILINE)
    if match is None:
        raise ModemError(f"No {name} setting in the modem's page")
    return match.group(1), match.group(2)


def parse_filter(config: str) -> FilterState:
    """Read the filter from addCfg("name","id","value") lines."""
    modes = [_config_field(config, f"wl_macmode{band}") for band in BANDS]
    lists = [_config_field(config, f"mac_lst{band}") for band in BANDS]

    values = {value for _, value in modes}
    if MODE_ALLOW in values:
        mode = MODE_ALLOW
    elif values == {MODE_BLOCK}:
        mode = MODE_BLOCK
    else:
        mode = MODE_OFF

    macs: dict[str, None] = {}
    for _, value in lists:
        macs.update(dict.fromkeys(mac.upper() for mac in value.split("|") if mac))
    return FilterState(
        mode,
        tuple(macs),
        tuple(field_id for field_id, _ in modes),
        tuple(field_id for field_id, _ in lists),
    )


def _login_error_code(url: URL, *pages: str) -> int:
    """Return the login page's error flag, or 0 if it gave none."""
    code = url.query.get("err", "0")
    if code.isdigit() and int(code):
        return int(code)
    for page in pages:
        match = _LOGIN_FLAG.search(page)
        if match and int(match.group(1)):
            return int(match.group(1))
    return 0


class ModemClient:
    """Talks to the modem. Holds no session between calls."""

    def __init__(self, host: str, password: str) -> None:
        """Initialize the client."""
        self._base = f"http://{host}"
        self._password = password
        self._lock = asyncio.Lock()

    def _session(self) -> aiohttp.ClientSession:
        # unsafe=True: aiohttp otherwise drops cookies set by an IP address.
        return aiohttp.ClientSession(
            cookie_jar=aiohttp.CookieJar(unsafe=True),
            headers={"Referer": f"{self._base}/"},
        )

    async def _fetch(
        self,
        session: aiohttp.ClientSession,
        method: str,
        path: str,
        data: dict[str, str] | None = None,
        timeout: float = REQUEST_TIMEOUT,
    ) -> tuple[int, str, URL]:
        try:
            async with session.request(
                method,
                f"{self._base}/{path}",
                data=data,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                return resp.status, await resp.text(errors="replace"), resp.url
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ModemConnectionError(f"Could not reach {self._base}") from err

    async def _login(self, session: aiohttp.ClientSession) -> str:
        """Log in and return the filter page, which holds the session token."""
        _, page, _ = await self._fetch(session, "GET", "")
        # The login page's own script sets this cookie before it submits.
        session.cookie_jar.update_cookies({"popup": "1"}, URL(self._base))
        _, result, url = await self._fetch(
            session,
            "POST",
            "cgi-bin/luci/admin/",
            {
                "token": parse_token(page),
                "nextp": "index.htm",
                "luci_password": hash_credential(self._password),
                "luci_username": hash_credential(USERNAME),
            },
        )

        status, filter_page, _ = await self._fetch(session, "GET", FILTER_PAGE)
        if status == 200:
            return filter_page

        code = _login_error_code(url, result, filter_page)
        if code == _FLAG_BAD_PASSWORD:
            raise InvalidAuth("The modem rejected the password")
        if code == _FLAG_SESSION_BUSY:
            raise SessionBusy("Another user is logged in to the modem")
        if code == _FLAG_LOCKED:
            raise LoginLocked("The modem login is locked, try again shortly")
        raise ModemError(f"Login failed (status {status}, flag {code})")

    async def _logout(self, session: aiohttp.ClientSession) -> None:
        """Free the modem's only admin session. Failure here is not fatal."""
        try:
            await self._fetch(session, "GET", "logout.htm")
        except ModemError as err:
            _LOGGER.debug("Logout failed: %s", err)

    async def _read_filter(self, session: aiohttp.ClientSession) -> FilterState:
        status, config, _ = await self._fetch(session, "GET", FILTER_CONFIG)
        if status != 200:
            raise ModemError(f"Could not read the filter (status {status})")
        return parse_filter(config)

    async def _save_filter(
        self,
        session: aiohttp.ClientSession,
        token: str,
        state: FilterState,
        macs: tuple[str, ...],
        mode: str,
    ) -> None:
        form = {
            "token": token,
            "submit_button": FILTER_PAGE,
            "action": FILTER_ACTION,
        }
        # With band steering the two bands must match, so both are always sent.
        form.update(dict.fromkeys(state.list_ids, "|".join(macs)))
        if mode != state.mode:
            form.update(dict.fromkeys(state.mode_ids, mode))

        try:
            status, _, _ = await self._fetch(
                session, "POST", "apply_abstract.cgi", form, APPLY_TIMEOUT
            )
        except ModemConnectionError:
            # The Wi-Fi restarts to apply this, which can drop the connection.
            _LOGGER.debug("Connection dropped while saving the filter")
            return
        if status != 200:
            raise ModemError(f"The modem refused the change (status {status})")

    async def _send_reboot(self, session: aiohttp.ClientSession) -> None:
        status, page, _ = await self._fetch(session, "GET", REBOOT_PAGE)
        if status != 200:
            raise ModemError(f"Could not open the reboot page (status {status})")

        try:
            status, _, _ = await self._fetch(
                session,
                "POST",
                "apply_abstract.cgi",
                {
                    "token": parse_token(page),
                    "submit_button": "index.htm",
                    "action": REBOOT_ACTION,
                },
            )
        except ModemConnectionError:
            # The modem may drop the connection as it goes down.
            _LOGGER.debug("Connection dropped while sending the reboot")
            return
        if status != 200:
            raise ModemError(f"The modem refused the reboot (status {status})")

    async def async_reboot(self) -> None:
        """Log in and ask the modem to reboot, which also ends the session."""
        async with self._lock, self._session() as session:
            await self._login(session)
            try:
                await self._send_reboot(session)
            except ModemError:
                await self._logout(session)
                raise

    async def async_read(self) -> FilterState:
        """Log in, read the filter, and log out."""
        async with self._lock, self._session() as session:
            await self._login(session)
            try:
                return await self._read_filter(session)
            finally:
                await self._logout(session)

    async def async_set_blocked(
        self, macs: Iterable[str], blocked: bool
    ) -> FilterState:
        """Add addresses to the block list or remove them, keeping everything else.

        Only ever uses the block list: an allow list that's wrong would take every
        other device off the Wi-Fi.
        """
        macs = tuple(macs)
        async with self._lock, self._session() as session:
            page = await self._login(session)
            try:
                state = await self._read_filter(session)
                if state.mode == MODE_ALLOW:
                    raise AllowListActive("The modem is using an allow list")

                if blocked:
                    wanted = state.macs + tuple(
                        mac for mac in macs if mac not in state.macs
                    )
                    mode = MODE_BLOCK
                else:
                    wanted = tuple(mac for mac in state.macs if mac not in macs)
                    mode = state.mode
                if len(wanted) > MAX_MACS:
                    raise ModemError(f"The block list is limited to {MAX_MACS} devices")

                if wanted != state.macs or mode != state.mode:
                    await self._save_filter(
                        session, parse_token(page), state, wanted, mode
                    )
                return FilterState(mode, wanted, state.mode_ids, state.list_ids)
            finally:
                await self._logout(session)
