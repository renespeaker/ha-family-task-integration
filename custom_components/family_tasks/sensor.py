"""A points sensor per person: state = spendable points, plus earned/redeemed."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from . import FamilyTasksConfigEntry, _display_name
from .const import DOMAIN, SIGNAL_UPDATED
from .stats import person_stats


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FamilyTasksConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """One sensor for everyone in the ledger; new people get one on first booking."""
    known: set[str] = set()

    @callback
    def _add(person: str) -> None:
        if person in known:
            return
        known.add(person)
        async_add_entities([PointsSensor(hass, entry, person)])

    for person in entry.runtime_data.ledger.persons():
        _add(person)
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_UPDATED, _add))


class PointsSensor(SensorEntity):
    """Spendable points of one person."""

    _attr_has_entity_name = True
    _attr_translation_key = "points"
    _attr_native_unit_of_measurement = "points"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, entry: FamilyTasksConfigEntry, person: str) -> None:
        self._entry = entry
        self._person = person
        self._attr_unique_id = f"{entry.entry_id}_{person}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{person}")},
            name=_display_name(hass, person),
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_UPDATED, self._on_update))
        # A new day can end a streak, Monday starts a new week: recount then.
        self.async_on_remove(
            async_track_time_change(self.hass, self._on_midnight, hour=0, minute=0, second=5)
        )

    @callback
    def _on_midnight(self, _now: Any) -> None:
        self.async_write_ha_state()

    @callback
    def _on_update(self, person: str) -> None:
        if person == self._person:
            self.async_write_ha_state()

    @property
    def native_value(self) -> int:
        """Spendable now: balance minus points reserved by open requests and offers."""
        return self._entry.runtime_data.ledger.available(self._person)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        ledger = self._entry.runtime_data.ledger
        totals = ledger.totals(self._person)
        last = ledger.last(self._person)
        return {
            # The card finds a person's sensor by this key.
            "person": self._person,
            "earned": totals.earned,
            "redeemed": totals.redeemed,
            "transferred": totals.transferred,
            "reserved": ledger.reserved(self._person),
            "pending": [
                {"id": r.id, "reward": r.label, "points": r.points, "at": r.at}
                for r in ledger.pending(self._person)
            ],
            # chores of this round handed over or offered, either way
            "offers": [
                {
                    "id": o.id,
                    "key": o.key,
                    "chore": o.chore,
                    "from": o.sender,
                    "to": o.receiver,
                    "points": o.points,
                    "until": o.until,
                    "accepted": o.accepted,
                }
                for o in ledger.offers_of(self._person)
            ],
            "last_booking": last.label if last else None,
            "last_booking_at": last.at if last else None,
            **self._stats(),
        }

    def _stats(self) -> dict[str, int]:
        """This week / month and streaks, counted in Home Assistant's time zone."""
        days = [
            (dt_util.as_local(at).date(), b)
            for b in self._entry.runtime_data.ledger.bookings
            if b.person == self._person and (at := dt_util.parse_datetime(b.at))
        ]
        st = person_stats(days, self._person, dt_util.now().date())
        return {
            "week_points": st.week_points,
            "month_points": st.month_points,
            "week_tasks": st.week_tasks,
            "month_tasks": st.month_tasks,
            "streak": st.streak,
            "best_streak": st.best_streak,
        }
