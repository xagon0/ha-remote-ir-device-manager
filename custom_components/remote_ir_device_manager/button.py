"""Button platform for Remote IR Device Manager."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .storage import IRCommand, VirtualDevice

if TYPE_CHECKING:
    from .coordinator import IRDeviceCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up button entities from a config entry."""
    coordinator: IRDeviceCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities: list[IRCommandButton] = []

    for device in coordinator.devices.values():
        for command in device.commands.values():
            entities.append(
                IRCommandButton(
                    coordinator=coordinator,
                    virtual_device=device,
                    command=command,
                    entry=entry,
                )
            )

    async_add_entities(entities)


class IRCommandButton(ButtonEntity):
    """Button entity for an IR command."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: IRDeviceCoordinator,
        virtual_device: VirtualDevice,
        command: IRCommand,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the button."""
        self._coordinator = coordinator
        self._virtual_device = virtual_device
        self._command = command
        self._entry = entry

        # Unique ID: entry_id + device_id + command_id
        self._attr_unique_id = (
            f"{entry.entry_id}_{virtual_device.id}_{command.id}"
        )
        self._attr_name = command.name
        self._attr_icon = command.icon or "mdi:remote"

        # Device info groups buttons under the virtual device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{virtual_device.id}")},
            name=virtual_device.name,
            manufacturer="Remote IR Device Manager",
            model="Virtual Remote",
            sw_version="1.0",
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Check if the IR blaster entity exists and is available
        state = self._coordinator.hass.states.get(
            self._virtual_device.ir_blaster_entity_id
        )
        return state is not None and state.state != "unavailable"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "command_type": self._command.command_type,
            "ir_blaster": self._virtual_device.ir_blaster_entity_id,
            "virtual_device": self._virtual_device.name,
            "learned_at": self._command.learned_at,
        }

    async def async_press(self) -> None:
        """Handle button press - send IR command."""
        await self._coordinator.async_send_command(
            self._virtual_device.id,
            self._command.name,
        )
        _LOGGER.debug(
            "Sent IR command '%s' for device '%s'",
            self._command.name,
            self._virtual_device.name,
        )
