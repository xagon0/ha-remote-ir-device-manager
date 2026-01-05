"""Base entity classes for Remote IR Device Manager."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry

from .storage import VirtualDevice

if TYPE_CHECKING:
    from .coordinator import IRDeviceCoordinator


class IRDeviceEntityMixin:
    """Mixin providing common functionality for IR device entities.

    Classes using this mixin must define:
        _coordinator: IRDeviceCoordinator
        _virtual_device: VirtualDevice
        _entry: ConfigEntry
    """

    _coordinator: "IRDeviceCoordinator"
    _virtual_device: VirtualDevice
    _entry: ConfigEntry

    @property
    def available(self) -> bool:
        """Return if entity is available based on IR blaster state.

        During startup, state may not exist yet - assume available.
        """
        state = self._coordinator.hass.states.get(
            self._virtual_device.ir_blaster_entity_id
        )
        if state is None:
            return True
        return state.state != "unavailable"

    async def _send_ir_command(self, command_name: str) -> None:
        """Send an IR command via the coordinator."""
        await self._coordinator.async_send_command(
            self._virtual_device.id,
            command_name,
        )
