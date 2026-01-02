"""Storage helper for Remote IR Device Manager."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import STORAGE_KEY, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)


@dataclass
class IRCommand:
    """A learned IR command."""

    id: str
    name: str
    code: str
    command_type: str = "ir"
    learned_at: str = field(default_factory=lambda: dt_util.utcnow().isoformat())
    icon: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IRCommand:
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            code=data["code"],
            command_type=data.get("command_type", "ir"),
            learned_at=data.get("learned_at", dt_util.utcnow().isoformat()),
            icon=data.get("icon"),
        )


@dataclass
class VirtualDevice:
    """A virtual remote device."""

    id: str
    name: str
    ir_blaster_entity_id: str
    commands: dict[str, IRCommand] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: dt_util.utcnow().isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "ir_blaster_entity_id": self.ir_blaster_entity_id,
            "commands": {k: v.to_dict() for k, v in self.commands.items()},
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VirtualDevice:
        """Create from dictionary."""
        commands = {}
        for cmd_key, cmd_data in data.get("commands", {}).items():
            commands[cmd_key] = IRCommand.from_dict(cmd_data)

        return cls(
            id=data["id"],
            name=data["name"],
            ir_blaster_entity_id=data["ir_blaster_entity_id"],
            commands=commands,
            created_at=data.get("created_at", dt_util.utcnow().isoformat()),
        )


class IRDeviceStorage:
    """Handle storage of virtual devices and commands."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize storage."""
        self._hass = hass
        self._entry_id = entry_id
        self._store = Store(
            hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry_id}"
        )
        self._devices: dict[str, VirtualDevice] = {}

    @property
    def devices(self) -> dict[str, VirtualDevice]:
        """Return all virtual devices."""
        return self._devices

    def get_device(self, device_id: str) -> VirtualDevice | None:
        """Get a virtual device by ID."""
        return self._devices.get(device_id)

    def get_device_by_name(self, name: str) -> VirtualDevice | None:
        """Get a virtual device by name."""
        for device in self._devices.values():
            if device.name.lower() == name.lower():
                return device
        return None

    async def async_load(self) -> None:
        """Load data from storage."""
        data = await self._store.async_load()
        if data is None:
            self._devices = {}
            return

        # Handle future storage migrations here
        # stored_version = data.get("version", 1)
        # if stored_version < STORAGE_VERSION:
        #     data = self._migrate_data(data, stored_version)

        self._devices = {}
        for device_id, device_data in data.get("virtual_devices", {}).items():
            try:
                self._devices[device_id] = VirtualDevice.from_dict(device_data)
            except (KeyError, TypeError) as err:
                _LOGGER.warning("Failed to load device %s: %s", device_id, err)

    async def async_save(self) -> None:
        """Save data to storage."""
        data = {
            "virtual_devices": {
                device_id: device.to_dict()
                for device_id, device in self._devices.items()
            }
        }
        await self._store.async_save(data)

    async def async_add_device(self, device: VirtualDevice) -> None:
        """Add a virtual device."""
        self._devices[device.id] = device
        await self.async_save()

    async def async_remove_device(self, device_id: str) -> bool:
        """Remove a virtual device."""
        if device_id in self._devices:
            del self._devices[device_id]
            await self.async_save()
            return True
        return False

    async def async_add_command(
        self, device_id: str, command: IRCommand
    ) -> bool:
        """Add a command to a device."""
        device = self._devices.get(device_id)
        if device is None:
            return False

        device.commands[command.name.lower()] = command
        await self.async_save()
        return True

    async def async_remove_command(
        self, device_id: str, command_name: str
    ) -> bool:
        """Remove a command from a device."""
        device = self._devices.get(device_id)
        if device is None:
            return False

        key = command_name.lower()
        if key in device.commands:
            del device.commands[key]
            await self.async_save()
            return True
        return False
