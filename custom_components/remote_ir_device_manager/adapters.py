"""IR Blaster adapters for code retrieval."""

from __future__ import annotations

from abc import ABC, abstractmethod
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class BlasterAdapter(ABC):
    """Base class for IR blaster adapters."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize adapter."""
        self._hass = hass

    @abstractmethod
    async def retrieve_learned_code(
        self, entity_id: str, device_name: str, command_name: str
    ) -> str | None:
        """Retrieve a learned code from the blaster's storage.

        Returns the base64-encoded IR code if found, None otherwise.
        """

    @abstractmethod
    def supports_entity(self, entity_id: str) -> bool:
        """Check if this adapter supports the given entity."""


class BroadlinkAdapter(BlasterAdapter):
    """Adapter for Broadlink IR blasters."""

    async def retrieve_learned_code(
        self, entity_id: str, device_name: str, command_name: str
    ) -> str | None:
        """Retrieve learned code from Broadlink storage.

        Broadlink stores codes in .storage/broadlink_remote_MACADDRESS_codes
        """
        # Get the MAC address from the entity
        mac_address = self._get_mac_from_entity(entity_id)
        if not mac_address:
            _LOGGER.debug("Could not determine MAC address for %s", entity_id)
            return None

        # Build storage path
        storage_path = Path(self._hass.config.path(".storage"))
        codes_file = storage_path / f"broadlink_remote_{mac_address}_codes"

        try:
            # Use executor for all blocking file I/O (including exists check)
            data = await self._hass.async_add_executor_job(
                self._read_codes_file, codes_file
            )
            if data is None:
                return None

            # Navigate to the code
            # Structure: {"data": {"device_name": {"command_name": "base64_code"}}}
            devices = data.get("data", {})
            device_codes = devices.get(device_name, {})
            code = device_codes.get(command_name)

            if code:
                _LOGGER.debug(
                    "Retrieved code for %s/%s from Broadlink storage",
                    device_name,
                    command_name,
                )
                return code

        except (json.JSONDecodeError, OSError) as err:
            _LOGGER.debug("Could not read Broadlink codes file: %s", err)

        return None

    def _read_codes_file(self, codes_file: Path) -> dict | None:
        """Read codes file synchronously (runs in executor)."""
        if not codes_file.exists():
            return None
        with open(codes_file, encoding="utf-8") as f:
            return json.load(f)

    def _get_mac_from_entity(self, entity_id: str) -> str | None:
        """Extract MAC address from Broadlink entity."""
        # Get entity registry entry
        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(self._hass)
        entry = registry.async_get(entity_id)

        if entry and entry.unique_id:
            # Broadlink unique_id format includes MAC
            # Try to extract MAC from unique_id
            unique_id = entry.unique_id
            # Format is typically MAC_type or similar
            parts = unique_id.split("_")
            if parts:
                # MAC is usually the first part, formatted as lowercase hex
                potential_mac = parts[0].lower().replace(":", "")
                if len(potential_mac) == 12 and all(
                    c in "0123456789abcdef" for c in potential_mac
                ):
                    return potential_mac

        # Fallback: try to get from device
        if entry and entry.device_id:
            from homeassistant.helpers import device_registry as dr

            device_registry = dr.async_get(self._hass)
            device = device_registry.async_get(entry.device_id)
            if device:
                for identifier in device.identifiers:
                    if identifier[0] == "broadlink":
                        # Second element might be MAC
                        mac = identifier[1].lower().replace(":", "")
                        if len(mac) == 12:
                            return mac

        return None

    def supports_entity(self, entity_id: str) -> bool:
        """Check if entity is a Broadlink remote."""
        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(self._hass)
        entry = registry.async_get(entity_id)

        if entry:
            return entry.platform == "broadlink"

        return False


class GenericAdapter(BlasterAdapter):
    """Generic adapter for unsupported IR blasters.

    This adapter always returns None for code retrieval,
    requiring manual code input from the user.
    """

    async def retrieve_learned_code(
        self, entity_id: str, device_name: str, command_name: str
    ) -> str | None:
        """Return None - manual input required."""
        _LOGGER.debug(
            "Generic adapter: manual code input required for %s/%s on %s",
            device_name,
            command_name,
            entity_id,
        )
        return None

    def supports_entity(self, entity_id: str) -> bool:
        """Generic adapter supports all entities."""
        return True


class AdapterRegistry:
    """Registry of available IR blaster adapters."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize registry."""
        self._hass = hass
        self._adapters: list[BlasterAdapter] = [
            BroadlinkAdapter(hass),
            # Add more adapters here as they're implemented:
            # TuyaAdapter(hass),
            # SwitchbotAdapter(hass),
        ]
        self._generic = GenericAdapter(hass)

    def get_adapter(self, entity_id: str) -> BlasterAdapter:
        """Get the appropriate adapter for an entity."""
        for adapter in self._adapters:
            if adapter.supports_entity(entity_id):
                return adapter
        return self._generic

    async def retrieve_learned_code(
        self, entity_id: str, device_name: str, command_name: str
    ) -> str | None:
        """Retrieve a learned code using the appropriate adapter."""
        adapter = self.get_adapter(entity_id)
        return await adapter.retrieve_learned_code(
            entity_id, device_name, command_name
        )
