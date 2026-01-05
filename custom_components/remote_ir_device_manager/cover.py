"""Cover platform for Remote IR Device Manager."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, DEVICE_TYPE_COVER
from .storage import VirtualDevice, EntityConfig

if TYPE_CHECKING:
    from .coordinator import IRDeviceCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up cover entities from a config entry."""
    coordinator: IRDeviceCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities: list[IRCover] = []

    for device in coordinator.devices.values():
        # Only create cover entity if device type is cover AND cover config exists
        if device.device_type == DEVICE_TYPE_COVER and "cover" in device.entity_configs:
            cover_config = device.entity_configs["cover"]
            if cover_config.enabled:
                entities.append(
                    IRCover(
                        coordinator=coordinator,
                        virtual_device=device,
                        config=cover_config,
                        entry=entry,
                    )
                )

    async_add_entities(entities)


class IRCover(CoverEntity):
    """Cover entity for an IR-controlled cover (projector screen, blinds)."""

    _attr_has_entity_name = True
    _attr_assumed_state = True

    def __init__(
        self,
        coordinator: IRDeviceCoordinator,
        virtual_device: VirtualDevice,
        config: EntityConfig,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the cover."""
        self._coordinator = coordinator
        self._virtual_device = virtual_device
        self._config = config
        self._entry = entry

        # Assumed state
        self._is_closed: bool | None = config.state.get("is_closed")
        self._position: int = config.state.get("position", 50)  # Unknown = middle

        # Unique ID
        self._attr_unique_id = f"{entry.entry_id}_{virtual_device.id}_cover"
        self._attr_name = None  # Use device name

        # Device class - default to shade, can be configured
        device_class = config.options.get("device_class", "shade")
        self._attr_device_class = CoverDeviceClass(device_class)

        # Device info - same identifier as other entities for grouping
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{virtual_device.id}")},
            name=virtual_device.name,
            manufacturer="Remote IR Device Manager",
            model="Virtual IR Cover",
            sw_version="1.0",
        )

        # Configure supported features based on command mappings
        self._setup_features()

    def _setup_features(self) -> None:
        """Configure supported features based on available commands."""
        mappings = self._config.command_mappings
        features = CoverEntityFeature(0)

        if mappings.get("open"):
            features |= CoverEntityFeature.OPEN
        if mappings.get("close"):
            features |= CoverEntityFeature.CLOSE
        if mappings.get("stop"):
            features |= CoverEntityFeature.STOP

        self._attr_supported_features = features

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        state = self._coordinator.hass.states.get(
            self._virtual_device.ir_blaster_entity_id
        )
        if state is None:
            return True
        return state.state != "unavailable"

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed."""
        return self._is_closed

    @property
    def current_cover_position(self) -> int | None:
        """Return current position (0=closed, 100=open)."""
        return self._position

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        mappings = self._config.command_mappings
        cmd = mappings.get("open")
        if cmd:
            await self._send_command(cmd)

        self._is_closed = False
        self._position = 100
        await self._save_state()
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        mappings = self._config.command_mappings
        cmd = mappings.get("close")
        if cmd:
            await self._send_command(cmd)

        self._is_closed = True
        self._position = 0
        await self._save_state()
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        mappings = self._config.command_mappings
        cmd = mappings.get("stop")
        if cmd:
            await self._send_command(cmd)

        # Position stays at assumed current position
        # Set to middle if was fully open/closed
        if self._position in (0, 100):
            self._position = 50
            self._is_closed = None  # Unknown
        await self._save_state()
        self.async_write_ha_state()

    async def _send_command(self, command_name: str) -> None:
        """Send an IR command."""
        await self._coordinator.async_send_command(
            self._virtual_device.id,
            command_name,
        )

    async def _save_state(self) -> None:
        """Persist assumed state to storage."""
        self._config.state["is_closed"] = self._is_closed
        self._config.state["position"] = self._position
        await self._coordinator.async_save_entity_state(
            self._virtual_device.id, "cover", self._config.state
        )
