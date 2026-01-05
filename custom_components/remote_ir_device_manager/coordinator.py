"""Coordinator for Remote IR Device Manager."""

from __future__ import annotations

import base64
import logging
import uuid
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .adapters import AdapterRegistry
from .const import DEVICE_TYPE_LIGHT, DEVICE_TYPE_COVER, DEVICE_TYPE_FAN
from .storage import IRCommand, IRDeviceStorage, VirtualDevice, EntityConfig

_LOGGER = logging.getLogger(__name__)


class IRDeviceCoordinator:
    """Coordinator for managing virtual IR devices and commands."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize coordinator."""
        self._hass = hass
        self._entry = entry
        self._storage = IRDeviceStorage(hass, entry.entry_id)
        self._adapter_registry = AdapterRegistry(hass)
        self._last_sent_command: dict[str, str] = {}

    @property
    def hass(self) -> HomeAssistant:
        """Return Home Assistant instance."""
        return self._hass

    @property
    def entry(self) -> ConfigEntry:
        """Return config entry."""
        return self._entry

    @property
    def devices(self) -> dict[str, VirtualDevice]:
        """Return all virtual devices."""
        return self._storage.devices

    @property
    def last_sent_command(self) -> dict[str, str]:
        """Return last sent command per device."""
        return self._last_sent_command

    def get_device(self, device_id: str) -> VirtualDevice | None:
        """Get a virtual device by ID."""
        return self._storage.get_device(device_id)

    def get_device_by_name(self, name: str) -> VirtualDevice | None:
        """Get a virtual device by name."""
        return self._storage.get_device_by_name(name)

    def command_name_exists(self, device_id: str, command_name: str) -> bool:
        """Check if a command name already exists on a device.

        Use this helper to validate command names in config flows.
        """
        device = self._storage.get_device(device_id)
        if device is None:
            return False
        return command_name.lower() in device.commands

    async def async_load(self) -> None:
        """Load data from storage."""
        await self._storage.async_load()

    async def async_add_device(
        self, name: str, ir_blaster_entity_id: str
    ) -> VirtualDevice:
        """Add a new virtual device."""
        # Check for duplicate names
        if self._storage.get_device_by_name(name):
            raise HomeAssistantError(f"Device with name '{name}' already exists")

        device = VirtualDevice(
            id=str(uuid.uuid4()),
            name=name,
            ir_blaster_entity_id=ir_blaster_entity_id,
        )
        await self._storage.async_add_device(device)
        _LOGGER.info("Added virtual device: %s", name)

        # Reload to create the new remote entity
        await self._async_reload_entry()

        return device

    async def async_remove_device(self, device_id: str) -> bool:
        """Remove a virtual device."""
        result = await self._storage.async_remove_device(device_id)
        if result:
            _LOGGER.info("Removed virtual device: %s", device_id)
            # Reload to remove the orphaned entities
            await self._async_reload_entry()
        return result

    async def async_add_command(
        self,
        device_id: str,
        command_name: str,
        code: str,
        command_type: str = "ir",
        icon: str | None = None,
    ) -> IRCommand:
        """Add a command to a device."""
        device = self._storage.get_device(device_id)
        if device is None:
            raise HomeAssistantError(f"Device '{device_id}' not found")

        # Check for duplicate command names
        if command_name.lower() in device.commands:
            raise HomeAssistantError(
                f"Command '{command_name}' already exists on device '{device.name}'"
            )

        # Strip b64: prefix if present
        if code.startswith("b64:"):
            code = code[4:]

        # Validate base64 encoding
        try:
            base64.b64decode(code, validate=True)
        except Exception as err:
            raise HomeAssistantError(f"Invalid base64 code: {err}") from err

        command = IRCommand(
            id=str(uuid.uuid4()),
            name=command_name,
            code=code,
            command_type=command_type,
            icon=icon if icon else None,  # Treat empty string as None
        )

        await self._storage.async_add_command(device_id, command)
        _LOGGER.info("Added command '%s' to device '%s'", command_name, device.name)

        # Trigger entity refresh
        await self._async_reload_entry()

        return command

    async def async_delete_command(
        self, device_id: str, command_name: str
    ) -> bool:
        """Delete a command from a device."""
        result = await self._storage.async_remove_command(device_id, command_name)
        if result:
            _LOGGER.info("Deleted command '%s' from device '%s'", command_name, device_id)
            await self._async_reload_entry()
        return result

    async def async_send_command(
        self, device_id: str, command_name: str, num_repeats: int = 1
    ) -> None:
        """Send a command via the IR blaster."""
        device = self._storage.get_device(device_id)
        if device is None:
            raise HomeAssistantError(f"Device '{device_id}' not found")

        command = device.commands.get(command_name.lower())
        if command is None:
            raise HomeAssistantError(
                f"Command '{command_name}' not found on device '{device.name}'"
            )

        # Send command via remote.send_command
        for _ in range(num_repeats):
            await self._hass.services.async_call(
                "remote",
                "send_command",
                {
                    "entity_id": device.ir_blaster_entity_id,
                    "command": f"b64:{command.code}",
                },
                blocking=True,
            )

        self._last_sent_command[device_id] = command_name
        _LOGGER.debug(
            "Sent command '%s' to '%s' via %s",
            command_name,
            device.name,
            device.ir_blaster_entity_id,
        )

    async def async_learn_command(
        self,
        device_id: str,
        command_name: str,
        command_type: str = "ir",
        timeout: int = 30,
    ) -> IRCommand | None:
        """Learn a new IR command.

        This triggers learning mode on the IR blaster and attempts to
        retrieve the learned code. If automatic retrieval fails,
        returns None (user must input code manually).
        """
        device = self._storage.get_device(device_id)
        if device is None:
            raise HomeAssistantError(f"Device '{device_id}' not found")

        # Check for duplicate command names
        if command_name.lower() in device.commands:
            raise HomeAssistantError(
                f"Command '{command_name}' already exists on device '{device.name}'"
            )

        # Create temporary device/command names for learning
        temp_device = f"_ridm_{device.id[:8]}"
        temp_command = f"_temp_{command_name}"

        _LOGGER.info(
            "Starting IR learning for '%s' on device '%s'",
            command_name,
            device.name,
        )

        try:
            # Call the underlying remote.learn_command
            await self._hass.services.async_call(
                "remote",
                "learn_command",
                {
                    "entity_id": device.ir_blaster_entity_id,
                    "device": temp_device,
                    "command": temp_command,
                    "command_type": command_type,
                    "timeout": timeout,
                },
                blocking=True,
            )
        except Exception as err:
            _LOGGER.error("Learning failed: %s", err)
            raise HomeAssistantError(f"Learning failed: {err}") from err

        # Attempt to retrieve the learned code
        code = await self._adapter_registry.retrieve_learned_code(
            device.ir_blaster_entity_id,
            temp_device,
            temp_command,
        )

        if code:
            # Successfully retrieved code - store it
            command = await self.async_add_command(
                device_id, command_name, code, command_type
            )
            _LOGGER.info("Successfully learned command '%s'", command_name)
            return command

        # Code retrieval failed - user needs to input manually
        _LOGGER.warning(
            "Could not automatically retrieve learned code for '%s'. "
            "Manual input may be required.",
            command_name,
        )
        return None

    async def async_update_command(
        self, device_id: str, command_name: str, **updates: Any
    ) -> bool:
        """Update a command's properties."""
        device = self._storage.get_device(device_id)
        if device is None:
            return False

        command = device.commands.get(command_name.lower())
        if command is None:
            return False

        for key, value in updates.items():
            if hasattr(command, key):
                setattr(command, key, value)

        await self._storage.async_save()
        await self._async_reload_entry()
        return True

    async def async_update_device_type(
        self, device_id: str, device_type: str
    ) -> bool:
        """Update device type and initialize default entity configs."""
        device = self._storage.get_device(device_id)
        if device is None:
            return False

        device.device_type = device_type

        # Initialize default entity config for the new type
        if device_type == DEVICE_TYPE_LIGHT and "light" not in device.entity_configs:
            device.entity_configs["light"] = EntityConfig(
                entity_type="light",
                enabled=True,
                command_mappings={},
                state={"is_on": False, "brightness": 255, "color_temp_index": 2},
                options={"brightness_mode": "none"},
            )
        elif device_type == DEVICE_TYPE_COVER and "cover" not in device.entity_configs:
            device.entity_configs["cover"] = EntityConfig(
                entity_type="cover",
                enabled=True,
                command_mappings={},
                state={"position": 50},
                options={"device_class": "shade"},
            )
        elif device_type == DEVICE_TYPE_FAN and "fan" not in device.entity_configs:
            device.entity_configs["fan"] = EntityConfig(
                entity_type="fan",
                enabled=True,
                command_mappings={},
                state={"is_on": False, "speed": 50},
                options={},
            )

        await self._storage.async_save()
        _LOGGER.info("Updated device '%s' type to '%s'", device.name, device_type)
        await self._async_reload_entry()
        return True

    async def async_update_entity_config(
        self, device_id: str, entity_type: str, config: EntityConfig
    ) -> bool:
        """Update entity configuration."""
        device = self._storage.get_device(device_id)
        if device is None:
            return False

        device.entity_configs[entity_type] = config
        await self._storage.async_save()
        _LOGGER.info(
            "Updated %s config for device '%s'", entity_type, device.name
        )
        await self._async_reload_entry()
        return True

    async def async_save_entity_state(
        self, device_id: str, entity_type: str, state: dict[str, Any]
    ) -> None:
        """Save entity state to storage (for assumed state persistence)."""
        device = self._storage.get_device(device_id)
        if device and entity_type in device.entity_configs:
            device.entity_configs[entity_type].state = state
            await self._storage.async_save()

    async def _async_reload_entry(self) -> None:
        """Reload the config entry to refresh entities."""
        try:
            await self._hass.config_entries.async_reload(self._entry.entry_id)
        except Exception as err:
            _LOGGER.warning("Failed to reload config entry: %s", err)
