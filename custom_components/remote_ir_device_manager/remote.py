"""Remote platform for Remote IR Device Manager."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.remote import (
    RemoteEntity,
    RemoteEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .storage import VirtualDevice

if TYPE_CHECKING:
    from .coordinator import IRDeviceCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up remote entities from a config entry."""
    coordinator: IRDeviceCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities: list[VirtualRemoteEntity] = []

    for device in coordinator.devices.values():
        entities.append(
            VirtualRemoteEntity(
                coordinator=coordinator,
                virtual_device=device,
                entry=entry,
            )
        )

    async_add_entities(entities)


class VirtualRemoteEntity(RemoteEntity):
    """Remote entity for a virtual IR device."""

    _attr_has_entity_name = True
    _attr_supported_features = (
        RemoteEntityFeature.LEARN_COMMAND
        | RemoteEntityFeature.DELETE_COMMAND
    )

    def __init__(
        self,
        coordinator: IRDeviceCoordinator,
        virtual_device: VirtualDevice,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the remote."""
        self._coordinator = coordinator
        self._virtual_device = virtual_device
        self._entry = entry
        self._is_on = True

        # Unique ID
        self._attr_unique_id = f"{entry.entry_id}_{virtual_device.id}_remote"
        self._attr_name = None  # Use device name

        # Device info - same as buttons so they're grouped together
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{virtual_device.id}")},
            name=virtual_device.name,
            manufacturer="Remote IR Device Manager",
            model="Virtual Remote",
            sw_version="1.0",
        )

    @property
    def is_on(self) -> bool:
        """Return True if the remote is on."""
        return self._is_on

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Check if the IR blaster entity exists and is available
        state = self._coordinator.hass.states.get(
            self._virtual_device.ir_blaster_entity_id
        )
        return state is not None and state.state != "unavailable"

    @property
    def activity_list(self) -> list[str]:
        """Return list of available activities (command names)."""
        return [cmd.name for cmd in self._virtual_device.commands.values()]

    @property
    def current_activity(self) -> str | None:
        """Return current activity (last sent command)."""
        return self._coordinator.last_sent_command.get(self._virtual_device.id)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "ir_blaster": self._virtual_device.ir_blaster_entity_id,
            "command_count": len(self._virtual_device.commands),
            "commands": list(self._virtual_device.commands.keys()),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the remote."""
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the remote."""
        self._is_on = False
        self.async_write_ha_state()

    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        """Send commands to the device."""
        num_repeats = kwargs.get("num_repeats", 1)
        delay_secs = kwargs.get("delay_secs", 0)

        commands_list = list(command)
        for i, cmd_name in enumerate(commands_list):
            # Look up command case-insensitively
            cmd_key = cmd_name.lower()
            if cmd_key in self._virtual_device.commands:
                await self._coordinator.async_send_command(
                    self._virtual_device.id,
                    cmd_name,
                    num_repeats,
                )
                _LOGGER.debug("Sent command '%s' via remote", cmd_name)

                # Add delay between commands (not after the last one)
                if delay_secs > 0 and i < len(commands_list) - 1:
                    await asyncio.sleep(delay_secs)
            else:
                _LOGGER.warning(
                    "Command '%s' not found on device '%s'",
                    cmd_name,
                    self._virtual_device.name,
                )

    async def async_learn_command(self, **kwargs: Any) -> None:
        """Learn a new command.

        Note: This is triggered via the remote.learn_command service.
        The kwargs include 'command' (list of command names to learn).
        """
        command = kwargs.get("command", [])
        command_type = kwargs.get("command_type", "ir")
        timeout = kwargs.get("timeout", 30)

        if not command:
            _LOGGER.error("No command name provided for learning")
            return

        # Learn each command
        for cmd_name in command:
            try:
                result = await self._coordinator.async_learn_command(
                    self._virtual_device.id,
                    cmd_name,
                    command_type,
                    timeout,
                )
                if result:
                    _LOGGER.info("Successfully learned command '%s'", cmd_name)
                else:
                    _LOGGER.warning(
                        "Could not automatically retrieve code for '%s'. "
                        "Manual input may be required.",
                        cmd_name,
                    )
            except Exception as err:
                _LOGGER.error("Failed to learn command '%s': %s", cmd_name, err)

    async def async_delete_command(self, **kwargs: Any) -> None:
        """Delete a learned command.

        Note: This is triggered via the remote.delete_command service.
        """
        command = kwargs.get("command", [])

        for cmd_name in command:
            try:
                success = await self._coordinator.async_delete_command(
                    self._virtual_device.id,
                    cmd_name,
                )
                if success:
                    _LOGGER.info("Deleted command '%s'", cmd_name)
                else:
                    _LOGGER.warning("Command '%s' not found", cmd_name)
            except Exception as err:
                _LOGGER.error("Failed to delete command '%s': %s", cmd_name, err)
