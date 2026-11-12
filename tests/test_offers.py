"""Handing a chore over: offer, take over or turn down, points moving across."""

from datetime import timedelta
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
)

from custom_components.family_tasks.const import (
    DOMAIN,
    EVENT_CHORE_ANSWERED,
    EVENT_CHORE_OFFERED,
    EVENT_POINTS_CHANGED,
)

KEY = "todo.chores|c1|2099-12-31"


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="Family Task Card Integration")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _call(hass: HomeAssistant, service: str, **data: Any) -> dict[str, Any]:
    res = await hass.services.async_call(DOMAIN, service, data, blocking=True, return_response=True)
    await hass.async_block_till_done()
    return res


def _sensor(hass: HomeAssistant, person: str):
    return next(s for s in hass.states.async_all("sensor") if s.attributes.get("person") == person)


async def _lina_offers(hass: HomeAssistant, points: int = 10, until: str = "2099-12-31") -> str:
    await _call(hass, "award", key="a", person="Lina", points=30)
    await _call(hass, "award", key="b", person="Ben", points=5)
    res = await _call(
        hass,
        "offer_chore",
        key=KEY,
        person="Lina",
        to="Ben",
        points=points,
        chore="Take out the bins",
        until=until,
    )
    return res["offer_id"]


async def test_an_offer_reserves_points_and_shows_on_both_sensors(hass: HomeAssistant):
    await _setup(hass)
    events = async_capture_events(hass, EVENT_CHORE_OFFERED)
    oid = await _lina_offers(hass)
    lina, ben = _sensor(hass, "Lina"), _sensor(hass, "Ben")
    assert (lina.state, lina.attributes["reserved"]) == ("20", 10)
    offer = {
        "id": oid,
        "key": KEY,
        "chore": "Take out the bins",
        "from": "Lina",
        "to": "Ben",
        "points": 10,
        "until": "2099-12-31",
        "accepted": False,
    }
    assert lina.attributes["offers"] == [offer]
    assert ben.attributes["offers"] == [offer]
    assert events[0].data == {
        "offer_id": oid,
        "key": KEY,
        "chore": "Take out the bins",
        "from": "Lina",
        "to": "Ben",
        "points": 10,
    }


async def test_taking_it_over_moves_the_points(hass: HomeAssistant):
    await _setup(hass)
    oid = await _lina_offers(hass)
    answered = async_capture_events(hass, EVENT_CHORE_ANSWERED)
    changed = async_capture_events(hass, EVENT_POINTS_CHANGED)
    assert await _call(hass, "answer_offer", offer_id=oid, accept=True) == {"answered": True}
    lina, ben = _sensor(hass, "Lina"), _sensor(hass, "Ben")
    assert (lina.state, lina.attributes["transferred"], lina.attributes["earned"]) == (
        "20",
        -10,
        30,
    )
    assert (ben.state, ben.attributes["transferred"], ben.attributes["earned"]) == ("15", 10, 5)
    assert ben.attributes["offers"][0]["accepted"] is True
    assert answered[0].data["accepted"] is True
    assert [(e.data["person"], e.data["points"]) for e in changed] == [("Lina", -10), ("Ben", 10)]
    # a second tap does nothing
    assert await _call(hass, "answer_offer", offer_id=oid, accept=True) == {"answered": False}
    assert _sensor(hass, "Ben").state == "15"


async def test_turning_it_down_frees_the_points(hass: HomeAssistant):
    await _setup(hass)
    oid = await _lina_offers(hass)
    answered = async_capture_events(hass, EVENT_CHORE_ANSWERED)
    await _call(hass, "answer_offer", offer_id=oid, accept=False)
    lina = _sensor(hass, "Lina")
    assert (lina.state, lina.attributes["reserved"], lina.attributes["offers"]) == ("30", 0, [])
    assert _sensor(hass, "Ben").attributes["offers"] == []
    assert answered[0].data["accepted"] is False


async def test_refuses_what_makes_no_sense(hass: HomeAssistant):
    await _setup(hass)
    oid = await _lina_offers(hass)
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, "offer_chore", key="k2", person="Lina", to="Lina")
    assert err.value.translation_key == "offer_self"
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, "offer_chore", key="k2", person="Lina", to="Ben", points=100)
    assert err.value.translation_key == "insufficient_points"
    await _call(hass, "answer_offer", offer_id=oid, accept=True)
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, "offer_chore", key=KEY, person="Ben", to="Lina")
    assert err.value.translation_key == "offer_taken"


async def test_an_offer_ends_with_its_round(hass: HomeAssistant):
    await _setup(hass)
    yesterday = (dt_util.now().date() - timedelta(days=1)).isoformat()
    oid = await _lina_offers(hass, until=yesterday)
    assert _sensor(hass, "Lina").attributes["reserved"] == 10
    # just after midnight the integration forgets it on its own
    async_fire_time_changed(hass, dt_util.now() + timedelta(days=1))
    await hass.async_block_till_done()
    assert _sensor(hass, "Lina").attributes["offers"] == []
    assert _sensor(hass, "Lina").attributes["reserved"] == 0
    assert await _call(hass, "answer_offer", offer_id=oid, accept=True) == {"answered": False}


async def test_a_round_that_is_over_cannot_be_taken_over(hass: HomeAssistant):
    await _setup(hass)
    yesterday = (dt_util.now().date() - timedelta(days=1)).isoformat()
    oid = await _lina_offers(hass, until=yesterday)
    assert await _call(hass, "answer_offer", offer_id=oid, accept=True) == {"answered": False}
    assert _sensor(hass, "Ben").state == "5"
