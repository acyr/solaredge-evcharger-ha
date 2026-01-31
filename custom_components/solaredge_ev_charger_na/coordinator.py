"""Data update coordinator for SolarEdge EV Charger."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import aiohttp
import async_timeout

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .solaredge_web import SolarEdgeWeb
from aiohttp import ClientError, ClientResponseError

from .const import (
    DOMAIN,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


class SolarEdgeEVChargerCoordinator(DataUpdateCoordinator):
    """Class to manage fetching SolarEdge EV Charger data."""

    def __init__(
        self,
        hass: HomeAssistant,
        site_id: str,
        username: str,
        password: str,
        device_id: str | None = None,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize the coordinator."""
        self.site_id = site_id
        self.username = username
        self.password = password
        self.device_id = device_id
        self.timeout = timeout
        self._session = async_get_clientsession(hass)
        self.api = SolarEdgeWeb(
            username=username,
            password=password,
            site_id=site_id,
            session=self._session,
            timeout=timeout
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API."""
        try:
            async with async_timeout.timeout(self.timeout):
                return await self._fetch_data()
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error communicating with API: {err}")
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}")

    async def _fetch_data(self) -> dict[str, Any]:
        """Fetch data from SolarEdge API."""
        devices = {}

        try:
            devices = await self.api.async_get_home_automation_devices()
        except ClientResponseError as err:
            if err.status in (401, 403):
                _LOGGER.error("Invalid authentication")
            else:
                _LOGGER.error("Cannot connect to the service")
            return False
        except (TimeoutError, ClientError):
            _LOGGER.error("Cannot connect to the service")
            return False

        try:
            ev_chargers = []
            for device_type, device_list in devices.get("devicesByType", {}).items():
                    if device_type == "EV_CHARGER":
                        ev_chargers.extend(device_list)

            if not ev_chargers or len(ev_chargers) == 0:
                raise Exception(ERROR_INVALID_SITE)

        except aiohttp.ClientError:
            raise Exception(ERROR_CANNOT_CONNECT)
        except Exception as e:
            if str(e) in [ERROR_AUTH_FAILED, ERROR_INVALID_SITE, ERROR_CANNOT_CONNECT]:
                raise
            _LOGGER.exception("Unexpected error validating credentials")
            raise Exception(ERROR_UNKNOWN)

        return ev_chargers[0]

    async def async_start_charging(self) -> bool:
        """Start charging the EV."""
        return await self._set_charging_state(100)

    async def async_stop_charging(self) -> bool:
        """Stop charging the EV."""
        return await self._set_charging_state(0)

    async def _set_charging_state(self, level: int) -> bool:
        """Set the charging state."""
        try:
            await self.api.async_set_ev_charging_state(
                device_id=self.device_id,
                level=level
                )
        except ClientResponseError as err:
            if err.status in (401, 403):
                _LOGGER.error("Invalid authentication")
            else:
                _LOGGER.error("Cannot connect to the service")
            return False
        except (TimeoutError, ClientError):
            _LOGGER.error("Cannot connect to the service")
            return False

        return True

    async def async_shutdown(self) -> None:
        """Close the session."""
        if self._session:
            await self._session.close()
            self._session = None
