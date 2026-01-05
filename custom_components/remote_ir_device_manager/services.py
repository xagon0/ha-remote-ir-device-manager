"""Service handlers for Remote IR Device Manager."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    CONF_COMMAND_CODE,
    CONF_COMMAND_NAME,
    CONF_COMMAND_TYPE,
    CONF_DEVICE_ID,
    COMMAND_TYPE_IR,
    DEFAULT_LEARN_TIMEOUT,
)

if TYPE_CHECKING:
    from .coordinator import IRDeviceCoordinator

_LOGGER = logging.getLogger(__name__)

# Service names
SERVICE_LEARN_COMMAND = "learn_command"
SERVICE_ADD_COMMAND = "add_command"
SERVICE_DELETE_COMMAND = "delete_command"
SERVICE_SEND_COMMAND = "send_command"

# Service schemas
SCHEMA_LEARN_COMMAND = vol.Schema(
    {
        vol.Required(CONF_DEVICE_ID): cv.string,
        vol.Required(CONF_COMMAND_NAME): cv.string,
        vol.Optional(CONF_COMMAND_TYPE, default=COMMAND_TYPE_IR): vol.In(["ir", "rf"]),
        vol.Optional("timeout", default=DEFAULT_LEARN_TIMEOUT): vol.All(
            vol.Coerce(int), vol.Range(min=10, max=120)
        ),
    }
)

SCHEMA_ADD_COMMAND = vol.Schema(
    {
        vol.Required(CONF_DEVICE_ID): cv.string,
        vol.Required(CONF_COMMAND_NAME): cv.string,
        vol.Required(CONF_COMMAND_CODE): cv.string,
        vol.Optional(CONF_COMMAND_TYPE, default=COMMAND_TYPE_IR): vol.In(["ir", "rf"]),
        vol.Optional("icon"): cv.string,
    }
)

SCHEMA_DELETE_COMMAND = vol.Schema(
    {
        vol.Required(CONF_DEVICE_ID): cv.string,
        vol.Required(CONF_COMMAND_NAME): cv.string,
    }
)

SCHEMA_SEND_COMMAND = vol.Schema(
    {
        vol.Required(CONF_DEVICE_ID): cv.string,
        vol.Required(CONF_COMMAND_NAME): cv.string,
        vol.Optional("num_repeats", default=1): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=10)
        ),
    }
)


def _get_coordinator(hass: HomeAssistant, device_id: str) -> "IRDeviceCoordinator":
    """Find coordinator for device or raise error."""
    for entry_data in hass.data.get(DOMAIN, {}).values():
        coordinator = entry_data.get("coordinator")
        if coordinator and coordinator.get_device(device_id):
            return coordinator
    raise HomeAssistantError(f"Device '{device_id}' not found")


async def _handle_learn_command(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle learn_command service."""
    device_id = call.data[CONF_DEVICE_ID]
    coord = _get_coordinator(hass, device_id)
    await coord.async_learn_command(
        device_id,
        call.data[CONF_COMMAND_NAME],
        call.data.get(CONF_COMMAND_TYPE, COMMAND_TYPE_IR),
        call.data.get("timeout", DEFAULT_LEARN_TIMEOUT),
    )


async def _handle_add_command(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle add_command service."""
    device_id = call.data[CONF_DEVICE_ID]
    coord = _get_coordinator(hass, device_id)
    await coord.async_add_command(
        device_id,
        call.data[CONF_COMMAND_NAME],
        call.data[CONF_COMMAND_CODE],
        call.data.get(CONF_COMMAND_TYPE, COMMAND_TYPE_IR),
        call.data.get("icon"),
    )


async def _handle_delete_command(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle delete_command service."""
    device_id = call.data[CONF_DEVICE_ID]
    coord = _get_coordinator(hass, device_id)
    await coord.async_delete_command(device_id, call.data[CONF_COMMAND_NAME])


async def _handle_send_command(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle send_command service."""
    device_id = call.data[CONF_DEVICE_ID]
    coord = _get_coordinator(hass, device_id)
    await coord.async_send_command(
        device_id,
        call.data[CONF_COMMAND_NAME],
        call.data.get("num_repeats", 1),
    )


# Service definitions: (name, schema, handler)
_SERVICES = [
    (SERVICE_LEARN_COMMAND, SCHEMA_LEARN_COMMAND, _handle_learn_command),
    (SERVICE_ADD_COMMAND, SCHEMA_ADD_COMMAND, _handle_add_command),
    (SERVICE_DELETE_COMMAND, SCHEMA_DELETE_COMMAND, _handle_delete_command),
    (SERVICE_SEND_COMMAND, SCHEMA_SEND_COMMAND, _handle_send_command),
]


async def async_register_services(hass: HomeAssistant) -> None:
    """Register all integration services."""
    for name, schema, handler in _SERVICES:
        if hass.services.has_service(DOMAIN, name):
            continue

        async def create_handler(h):
            async def wrapped(call: ServiceCall) -> None:
                await h(hass, call)
            return wrapped

        hass.services.async_register(
            DOMAIN,
            name,
            await create_handler(handler),
            schema=schema,
        )


def async_unregister_services(hass: HomeAssistant) -> None:
    """Unregister all integration services."""
    for name, _, _ in _SERVICES:
        hass.services.async_remove(DOMAIN, name)
