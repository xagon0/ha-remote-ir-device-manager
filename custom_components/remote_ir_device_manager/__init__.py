"""The Remote IR Device Manager integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import IRDeviceCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Remote IR Device Manager from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = IRDeviceCoordinator(hass, entry)
    await coordinator.async_load()

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
    }

    # Register services
    await _async_register_services(hass, coordinator)

    # Forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

        # Unregister services if no entries remain
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, "learn_command")
            hass.services.async_remove(DOMAIN, "add_command")
            hass.services.async_remove(DOMAIN, "delete_command")
            hass.services.async_remove(DOMAIN, "send_command")

    return unload_ok


def _get_coordinator(hass: HomeAssistant, device_id: str) -> IRDeviceCoordinator | None:
    """Find the coordinator that manages the given device."""
    for entry_data in hass.data[DOMAIN].values():
        coordinator = entry_data.get("coordinator")
        if coordinator and coordinator.get_device(device_id):
            return coordinator
    return None


async def _async_register_services(
    hass: HomeAssistant, coordinator: IRDeviceCoordinator
) -> None:
    """Register integration services."""
    from homeassistant.core import ServiceCall
    import voluptuous as vol
    from homeassistant.helpers import config_validation as cv
    from homeassistant.exceptions import HomeAssistantError

    from .const import (
        CONF_COMMAND_CODE,
        CONF_COMMAND_NAME,
        CONF_COMMAND_TYPE,
        CONF_DEVICE_ID,
        COMMAND_TYPE_IR,
        DEFAULT_LEARN_TIMEOUT,
    )

    async def handle_learn_command(call: ServiceCall) -> None:
        """Handle the learn_command service call."""
        device_id = call.data[CONF_DEVICE_ID]
        coord = _get_coordinator(hass, device_id)
        if not coord:
            raise HomeAssistantError(f"Device '{device_id}' not found")
        command_name = call.data[CONF_COMMAND_NAME]
        command_type = call.data.get(CONF_COMMAND_TYPE, COMMAND_TYPE_IR)
        timeout = call.data.get("timeout", DEFAULT_LEARN_TIMEOUT)
        await coord.async_learn_command(
            device_id, command_name, command_type, timeout
        )

    async def handle_add_command(call: ServiceCall) -> None:
        """Handle the add_command service call."""
        device_id = call.data[CONF_DEVICE_ID]
        coord = _get_coordinator(hass, device_id)
        if not coord:
            raise HomeAssistantError(f"Device '{device_id}' not found")
        command_name = call.data[CONF_COMMAND_NAME]
        code = call.data[CONF_COMMAND_CODE]
        command_type = call.data.get(CONF_COMMAND_TYPE, COMMAND_TYPE_IR)
        icon = call.data.get("icon")
        await coord.async_add_command(
            device_id, command_name, code, command_type, icon
        )

    async def handle_delete_command(call: ServiceCall) -> None:
        """Handle the delete_command service call."""
        device_id = call.data[CONF_DEVICE_ID]
        coord = _get_coordinator(hass, device_id)
        if not coord:
            raise HomeAssistantError(f"Device '{device_id}' not found")
        command_name = call.data[CONF_COMMAND_NAME]
        await coord.async_delete_command(device_id, command_name)

    async def handle_send_command(call: ServiceCall) -> None:
        """Handle the send_command service call."""
        device_id = call.data[CONF_DEVICE_ID]
        coord = _get_coordinator(hass, device_id)
        if not coord:
            raise HomeAssistantError(f"Device '{device_id}' not found")
        command_name = call.data[CONF_COMMAND_NAME]
        num_repeats = call.data.get("num_repeats", 1)
        await coord.async_send_command(device_id, command_name, num_repeats)

    # Only register if not already registered
    if not hass.services.has_service(DOMAIN, "learn_command"):
        hass.services.async_register(
            DOMAIN,
            "learn_command",
            handle_learn_command,
            schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ID): cv.string,
                    vol.Required(CONF_COMMAND_NAME): cv.string,
                    vol.Optional(CONF_COMMAND_TYPE, default=COMMAND_TYPE_IR): vol.In(
                        ["ir", "rf"]
                    ),
                    vol.Optional("timeout", default=DEFAULT_LEARN_TIMEOUT): vol.All(
                        vol.Coerce(int), vol.Range(min=10, max=120)
                    ),
                }
            ),
        )

    if not hass.services.has_service(DOMAIN, "add_command"):
        hass.services.async_register(
            DOMAIN,
            "add_command",
            handle_add_command,
            schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ID): cv.string,
                    vol.Required(CONF_COMMAND_NAME): cv.string,
                    vol.Required(CONF_COMMAND_CODE): cv.string,
                    vol.Optional(CONF_COMMAND_TYPE, default=COMMAND_TYPE_IR): vol.In(
                        ["ir", "rf"]
                    ),
                    vol.Optional("icon"): cv.string,
                }
            ),
        )

    if not hass.services.has_service(DOMAIN, "delete_command"):
        hass.services.async_register(
            DOMAIN,
            "delete_command",
            handle_delete_command,
            schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ID): cv.string,
                    vol.Required(CONF_COMMAND_NAME): cv.string,
                }
            ),
        )

    if not hass.services.has_service(DOMAIN, "send_command"):
        hass.services.async_register(
            DOMAIN,
            "send_command",
            handle_send_command,
            schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ID): cv.string,
                    vol.Required(CONF_COMMAND_NAME): cv.string,
                    vol.Optional("num_repeats", default=1): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=10)
                    ),
                }
            ),
        )
