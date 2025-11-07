"""Vaillant sensors."""

from __future__ import annotations

import logging
import struct
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import VaillantClient
from .const import API_CLIENT, CONF_DID, DISPATCHERS, DOMAIN, EVT_DEVICE_CONNECTED
from .entity import VaillantEntity

_LOGGER = logging.getLogger(__name__)


SENSOR_DESCRIPTIONS = [
    SensorEntityDescription(
        key="water_pressure",
        name="供暖水压",
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="bar",
    ),
    SensorEntityDescription(
        key="Heating_Curve",
        name="供暖曲线",
    ),
    SensorEntityDescription(
        key="Heating_System_Setting",
        name="暖气系统类型",
    ),
    SensorEntityDescription(
        key="Mode_Setting_CH",
        name="Mode Setting CH",
    ),
    SensorEntityDescription(
        key="Mode_Setting_DHW",
        name="Mode Setting DHW",
    ),
    SensorEntityDescription(
        key="Heating_System_Setting",
        name="Heating System Setting",
    ),
    SensorEntityDescription(
        key="burn_status",
        name="burn_status",  # 燃烧状态
    ),
    SensorEntityDescription(
        key="valveModulation_settingValue",
        name="燃气阀调制设定值",
    ),
    SensorEntityDescription(
        key="valueModulation_currentValue",
        name="燃气阀调制当前值",
    ),
    SensorEntityDescription(
        key="pump_status",
        name="pump_status",  # 泵状态
    ),
    SensorEntityDescription(
        key="fan_status",
        name="风扇状态",
    ),
    SensorEntityDescription(
        key="fan_speed",
        name="风扇转速",
    ),
    SensorEntityDescription(
        key="maintainence_remainTime",
        name="保养时间",
    ),
]

temperatures = [
    ("Flow_temperature", "供暖出水温度"),
    ("return_temperature", "供暖回水温度"),
    ("Tank_temperature", "水罐温度"),
    ("Flow_Temperature_Setpoint", "暖气设置温度"),
    ("indoor_temperature", "室内设定温度"),
    ("DHW_setpoint", "生活热水设置温度"),
    ("Lower_Limitation_of_CH_Setpoint", "暖气最小设置温度"),
    ("Upper_Limitation_of_CH_Setpoint", "暖气最大设置温度"),
    ("Lower_Limitation_of_DHW_Setpoint", "生活热水最小设置温度"),
    ("Upper_Limitation_of_DHW_Setpoint", "生活热水最大设置温度"),
    ("ext_CH_flow_temperature", "ext_CH_flow_temperature"),
    ("ext_CH_return_temperature", "ext_CH_return_temperature"),
    ("ext_DHW_flow_temperature", "ext_DHW_flow_temperature"),
    ("ext_DHW_return_temperature", "ext_DHW_return_temperature"),
]
for key, name in temperatures:
    SENSOR_DESCRIPTIONS.append(
        SensorEntityDescription(
            key=key,
            name=name,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        )
    )
gas_consumption = [
    ("gas_ch_consumption_today", "暖气燃气消耗-今天"),
    ("gas_ch_consumption_yesterday", "暖气燃气消耗-昨天"),
    ("gas_ch_consumption_monthly", "暖气燃气消耗-上个月"),
    ("gas_ch_consumption_yearly", "暖气燃气消耗-去年"),
    ("gas_dhw_consumption_today", "生活热水燃气消耗-今天"),
    ("gas_dhw_consumption_yesterday", "生活热水燃气消耗-昨天"),
    ("gas_dhw_consumption_monthly", "生活热水燃气消耗-上个月"),
    ("gas_dhw_consumption_yearly", "生活热水燃气消耗-去年"),
]
for key, name in gas_consumption:
    SENSOR_DESCRIPTIONS.append(
        SensorEntityDescription(
            key=key,
            name=name,
            device_class=SensorDeviceClass.GAS,
            state_class=SensorStateClass.MEASUREMENT,
            # native_unit_of_measurement=UnitOfTemperature.CUBIC_METERS,
            native_unit_of_measurement="kWh",
        )
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> bool:
    """Set up Vaillant sensors."""
    device_id = entry.data.get(CONF_DID)
    client: VaillantClient = hass.data[DOMAIN][API_CLIENT][entry.entry_id]

    added_entities = []

    @callback
    def async_new_entities(device_attrs: dict[str, Any]):
        _LOGGER.debug("add vaillant sensor entities. device attrs: %s", device_attrs)
        new_entities = []
        for description in SENSOR_DESCRIPTIONS:
            if (
                description.key in device_attrs
                and description.key not in added_entities
            ):
                new_entities.append(VaillantSensorEntity(client, description))
                added_entities.append(description.key)
            elif (
                description.key.startswith("ext_")
                and description.key not in added_entities
            ):
                new_entities.append(VaillantSensorEntity(client, description))
                added_entities.append(description.key)

        if len(new_entities) > 0:
            async_add_entities(new_entities)

    unsub = async_dispatcher_connect(
        hass, EVT_DEVICE_CONNECTED.format(device_id), async_new_entities
    )

    hass.data[DOMAIN][DISPATCHERS][device_id].append(unsub)

    return True


class VaillantSensorEntity(VaillantEntity, SensorEntity):
    """Define a Vaillant sensor entity."""

    def __init__(
        self,
        client: VaillantClient,
        description: SensorEntityDescription,
    ):
        super().__init__(client)
        self.entity_description = description

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"{self.device.id}_{self.entity_description.key}"

    def _hex2float32(self, hex_str):
        # little-endian IEEE 754 float32
        return struct.unpack(">f", int(hex_str, 16).to_bytes(4, byteorder="little"))[0]

    @callback
    def update_from_latest_data(self, data: dict[str, Any]) -> None:
        """Update the entity from the latest data."""

        if self.entity_description.key in data:
            value = data.get(self.entity_description.key)
            if self.entity_description.key.startswith("gas_"):
                value = self._hex2float32(value)
            self._attr_native_value = value
            self._attr_available = value is not None
            # _LOGGER.info("sensor update data %s==%s",self.entity_description.key,value)
            self.async_schedule_update_ha_state(True)
            return

        _LOGGER.debug(
            "update_from_latest_data: %s, %s", self.entity_description.key, data
        )
        if self.entity_description.key.startswith("ext_") and "burn_status" in data:
            self._attr_available = None
            if 2 <= data.get("burn_status", 0) <= 8:
                if self.entity_description.key == "ext_CH_flow_temperature":
                    self._attr_native_value = data.get("Flow_temperature")
                    self._attr_available = data.get("Flow_temperature") is not None
                if self.entity_description.key == "ext_CH_return_temperature":
                    self._attr_native_value = data.get("return_temperature")
                    self._attr_available = data.get("return_temperature") is not None
            if 22 <= data.get("burn_status", 0) <= 28:
                if self.entity_description.key == "ext_DHW_flow_temperature":
                    self._attr_native_value = data.get("Flow_temperature")
                    self._attr_available = data.get("Flow_temperature") is not None
                if self.entity_description.key == "ext_DHW_return_temperature":
                    self._attr_native_value = data.get("return_temperature")
                    self._attr_available = data.get("return_temperature") is not None
            self.async_schedule_update_ha_state(True)
            return
