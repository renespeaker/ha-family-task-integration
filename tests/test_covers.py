"""Covering for someone who is away, and evening it out later."""

from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.family_tasks.const import DOMAIN


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


def _covers(hass: HomeAssistant, person: str) -> list[dict[str, Any]]:
    st = next(s for s in hass.states.async_all("sensor") if s.attributes.get("person") == person)
    return st.attributes["covers"]


async def test_a_cover_shows_on_both_sensors_until_it_is_evened_out(hass: HomeAssistant):
    await _setup(hass)
    res = await _call(
        hass, "cover", key="todo.chores|c1|2099-01-04", person="Lina", absent="Ben", chore="Bins"
    )
    assert res == {"covered": True}
    assert await _call(
        hass, "cover", key="todo.chores|c1|2099-01-04", person="Lina", absent="Ben"
    ) == {"covered": False}  # the second device
    cover = {
        "key": "todo.chores|c1|2099-01-04",
        "helper": "Lina",
        "absent": "Ben",
        "chore": "Bins",
        "settled_by": None,
    }
    assert _covers(hass, "Lina") == [cover]
    assert _covers(hass, "Ben") == [cover]
    res = await _call(
        hass, "even_out", key="todo.chores|c2|2099-01-11", person="Ben", helper="Lina"
    )
    assert res == {"evened": True}
    assert _covers(hass, "Ben")[0]["settled_by"] == "todo.chores|c2|2099-01-11"


async def test_unchecking_undoes_its_part(hass: HomeAssistant):
    await _setup(hass)
    await _call(hass, "cover", key="todo.chores|c1|2099-01-04", person="Lina", absent="Ben")
    await _call(hass, "award", key="todo.chores|c2|2099-01-11", person="Ben", points=10)
    await _call(hass, "even_out", key="todo.chores|c2|2099-01-11", person="Ben", helper="Lina")
    await _call(hass, "revoke", key="todo.chores|c2|2099-01-11")  # Ben unchecks it again
    assert _covers(hass, "Ben")[0]["settled_by"] is None
    await _call(hass, "revoke", key="todo.chores|c1|2099-01-04")  # and Lina hers
    assert _covers(hass, "Ben") == []


async def test_no_cover_for_oneself(hass: HomeAssistant):
    await _setup(hass)
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, "cover", key="k", person="Lina", absent="Lina")
    assert err.value.translation_key == "offer_self"
