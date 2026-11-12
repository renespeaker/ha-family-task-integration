"""Reward approval by push: request, notify, approve/deny by service or button."""

from typing import Any

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_mock_service,
)

from custom_components.family_tasks.const import (
    CONF_NOTIFY,
    DOMAIN,
    EVENT_REWARD_DECIDED,
    EVENT_REWARD_REQUESTED,
)


async def _setup(hass: HomeAssistant, notify: list[str] | None = None) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, title="Family Task Card Integration", options={CONF_NOTIFY: notify or []}
    )
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


async def _lina_asks(hass: HomeAssistant) -> str:
    await _call(hass, "award", key="a", person="Lina", points=30)
    res = await _call(hass, "request_reward", person="Lina", points=20, reward="Ice cream")
    return res["request_id"]


async def test_request_reserves_points_and_pushes_the_parents(hass: HomeAssistant):
    hass.config.language = "de"
    mom = async_mock_service(hass, "notify", "mobile_app_mom")
    dad = async_mock_service(hass, "notify", "mobile_app_dad")
    await _setup(hass, ["mobile_app_mom", "mobile_app_dad"])
    events = async_capture_events(hass, EVENT_REWARD_REQUESTED)
    rid = await _lina_asks(hass)

    st = _sensor(hass, "Lina")
    assert (st.state, st.attributes["reserved"]) == ("10", 20)
    assert st.attributes["pending"][0] | {"at": None} == {
        "id": rid,
        "reward": "Ice cream",
        "points": 20,
        "at": None,
    }
    assert events[0].data == {
        "request_id": rid,
        "person": "Lina",
        "reward": "Ice cream",
        "points": 20,
    }
    assert len(mom) == len(dad) == 1
    push = mom[0].data
    assert push["title"] == "🎁 Belohnung angefragt"
    assert push["message"] == "Lina möchte „Ice cream“ für 20 Punkte."
    assert push["data"]["tag"] == f"family_tasks_{rid}"
    assert [a["action"] for a in push["data"]["actions"]] == [
        f"FAMILY_TASKS_APPROVE_{rid}",
        f"FAMILY_TASKS_DENY_{rid}",
    ]


async def test_the_approve_button_on_the_phone_spends_the_points(hass: HomeAssistant):
    mom = async_mock_service(hass, "notify", "mobile_app_mom")
    await _setup(hass, ["mobile_app_mom"])
    decided = async_capture_events(hass, EVENT_REWARD_DECIDED)
    rid = await _lina_asks(hass)

    hass.bus.async_fire("mobile_app_notification_action", {"action": f"FAMILY_TASKS_APPROVE_{rid}"})
    await hass.async_block_till_done()

    st = _sensor(hass, "Lina")
    assert (st.state, st.attributes["redeemed"], st.attributes["pending"]) == ("10", 20, [])
    assert decided[0].data["approved"] is True
    # the push disappears from the other phones
    assert mom[-1].data == {"message": "clear_notification", "data": {"tag": f"family_tasks_{rid}"}}


async def test_deny_frees_the_points(hass: HomeAssistant):
    await _setup(hass)
    decided = async_capture_events(hass, EVENT_REWARD_DECIDED)
    rid = await _lina_asks(hass)
    assert await _call(hass, "deny", request_id=rid) == {"decided": True}
    st = _sensor(hass, "Lina")
    assert (st.state, st.attributes["redeemed"], st.attributes["reserved"]) == ("30", 0, 0)
    assert decided[0].data["approved"] is False


async def test_only_the_first_decision_counts(hass: HomeAssistant):
    await _setup(hass)
    rid = await _lina_asks(hass)
    assert await _call(hass, "approve", request_id=rid) == {"decided": True}
    assert await _call(hass, "deny", request_id=rid) == {"decided": False}  # second parent
    hass.bus.async_fire("mobile_app_notification_action", {"action": f"FAMILY_TASKS_APPROVE_{rid}"})
    await hass.async_block_till_done()
    assert _sensor(hass, "Lina").attributes["redeemed"] == 20


async def test_other_notification_buttons_are_ignored(hass: HomeAssistant):
    await _setup(hass)
    rid = await _lina_asks(hass)
    hass.bus.async_fire("mobile_app_notification_action", {"action": "OPEN_GARAGE"})
    await hass.async_block_till_done()
    assert _sensor(hass, "Lina").attributes["pending"][0]["id"] == rid


async def test_cannot_ask_for_more_than_is_left(hass: HomeAssistant):
    await _setup(hass)
    await _lina_asks(hass)
    with pytest.raises(ServiceValidationError):
        await _call(hass, "request_reward", person="Lina", points=15, reward="Tablet")


async def test_requests_survive_a_restart(hass: HomeAssistant):
    entry = await _setup(hass)
    rid = await _lina_asks(hass)
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert _sensor(hass, "Lina").attributes["pending"][0]["id"] == rid
    assert await _call(hass, "approve", request_id=rid) == {"decided": True}


async def test_options_pick_the_push_targets(hass: HomeAssistant):
    async_mock_service(hass, "notify", "mobile_app_mom")
    async_mock_service(hass, "notify", "mobile_app_dad")
    entry = await _setup(hass)
    res = await hass.config_entries.options.async_init(entry.entry_id)
    assert res["type"] is FlowResultType.FORM
    res = await hass.config_entries.options.async_configure(
        res["flow_id"], {CONF_NOTIFY: ["mobile_app_mom"]}
    )
    assert res["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_NOTIFY: ["mobile_app_mom"]}


async def test_the_deny_button_on_the_phone_frees_the_points(hass: HomeAssistant):
    await _setup(hass)
    rid = await _lina_asks(hass)
    hass.bus.async_fire("mobile_app_notification_action", {"action": f"FAMILY_TASKS_DENY_{rid}"})
    await hass.async_block_till_done()
    st = _sensor(hass, "Lina")
    assert (st.state, st.attributes["redeemed"], st.attributes["pending"]) == ("30", 0, [])


async def test_a_phone_that_is_gone_does_not_stop_requests(hass: HomeAssistant):
    """Dad's old phone was removed: Mom still gets the push, deciding still works."""
    mom = async_mock_service(hass, "notify", "mobile_app_mom")
    # a notify service that only takes a plain message
    async_mock_service(hass, "notify", "sms", schema=vol.Schema({vol.Required("message"): str}))
    await _setup(hass, ["mobile_app_dads_old_phone", "sms", "mobile_app_mom"])
    rid = await _lina_asks(hass)
    assert len(mom) == 1
    assert await _call(hass, "approve", request_id=rid) == {"decided": True}
    assert mom[-1].data["message"] == "clear_notification"
    assert _sensor(hass, "Lina").attributes["redeemed"] == 20
