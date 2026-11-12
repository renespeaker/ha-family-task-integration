"""Family Task Card Integration: a persistent points ledger for the Family Task Card.

The card reports checked-off tasks with `family_tasks.award` (and takes them
back with `revoke`); rewards are paid with `redeem`, parents can give a bonus
or deduction with `adjust`. With `request_reward` a child asks for a reward:
its points are reserved and the parents get a push with "approve" / "deny"
buttons (or decide with the `approve` / `deny` services). With `offer_chore`
a chore of this round goes to someone else, maybe for points, once they say yes
with `answer_offer`. `cover` notes a chore done for someone who was away, and
`even_out` the one they do in return. Every person gets a points sensor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import (
    Event,
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util
from homeassistant.util.ulid import ulid_now

from .const import (
    ACTION_APPROVE,
    ACTION_DENY,
    ATTR_ABSENT,
    ATTR_ACCEPT,
    ATTR_CHORE,
    ATTR_HELPER,
    ATTR_KEY,
    ATTR_OFFER_ID,
    ATTR_PERSON,
    ATTR_POINTS,
    ATTR_REASON,
    ATTR_REQUEST_ID,
    ATTR_REWARD,
    ATTR_TASK,
    ATTR_TO,
    ATTR_UNTIL,
    CONF_NOTIFY,
    DOMAIN,
    EVENT_CHORE_ANSWERED,
    EVENT_CHORE_OFFERED,
    EVENT_NOTIFICATION_ACTION,
    EVENT_POINTS_CHANGED,
    EVENT_REWARD_DECIDED,
    EVENT_REWARD_REQUESTED,
    SERVICE_ADJUST,
    SERVICE_ANSWER_OFFER,
    SERVICE_APPROVE,
    SERVICE_AWARD,
    SERVICE_COVER,
    SERVICE_DENY,
    SERVICE_EVEN_OUT,
    SERVICE_OFFER_CHORE,
    SERVICE_REDEEM,
    SERVICE_REQUEST_REWARD,
    SERVICE_REVOKE,
    SIGNAL_UPDATED,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .ledger import COVER_DAYS, InsufficientPoints, Ledger, Offer, OfferRefused, Request

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PERSON = vol.All(cv.string, vol.Length(min=1))
KEY = vol.All(cv.string, vol.Length(min=1))

AWARD_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_KEY): KEY,
        vol.Required(ATTR_PERSON): PERSON,
        vol.Required(ATTR_POINTS): vol.All(vol.Coerce(int), vol.Range(min=0)),
        vol.Optional(ATTR_TASK, default=""): cv.string,
    }
)
REVOKE_SCHEMA = vol.Schema({vol.Required(ATTR_KEY): KEY})
REWARD_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PERSON): PERSON,
        vol.Required(ATTR_POINTS): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional(ATTR_REWARD, default=""): cv.string,
    }
)
ADJUST_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PERSON): PERSON,
        vol.Required(ATTR_POINTS): vol.All(vol.Coerce(int), vol.NotIn([0])),
        vol.Optional(ATTR_REASON, default=""): cv.string,
    }
)
DECIDE_SCHEMA = vol.Schema({vol.Required(ATTR_REQUEST_ID): KEY})
OFFER_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_KEY): KEY,
        vol.Required(ATTR_PERSON): PERSON,
        vol.Required(ATTR_TO): PERSON,
        vol.Optional(ATTR_POINTS, default=0): vol.All(vol.Coerce(int), vol.Range(min=0)),
        vol.Optional(ATTR_CHORE, default=""): cv.string,
        vol.Optional(ATTR_UNTIL): cv.date,
    }
)
ANSWER_SCHEMA = vol.Schema(
    {vol.Required(ATTR_OFFER_ID): KEY, vol.Required(ATTR_ACCEPT): cv.boolean}
)
COVER_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_KEY): KEY,
        vol.Required(ATTR_PERSON): PERSON,
        vol.Required(ATTR_ABSENT): PERSON,
        vol.Optional(ATTR_CHORE, default=""): cv.string,
    }
)
EVEN_OUT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_KEY): KEY,
        vol.Required(ATTR_PERSON): PERSON,
        vol.Required(ATTR_HELPER): PERSON,
    }
)

# Push texts, by Home Assistant language (English otherwise).
PUSH_TEXT = {
    "de": {
        "title": "🎁 Belohnung angefragt",
        "message": "{person} möchte „{reward}“ für {points} Punkte.",
        "approve": "Freigeben",
        "deny": "Ablehnen",
    },
    "en": {
        "title": "🎁 Reward requested",
        "message": "{person} would like “{reward}” for {points} points.",
        "approve": "Approve",
        "deny": "Deny",
    },
}


@dataclass
class FamilyTasksData:
    """What a loaded entry keeps: the ledger and where it is stored."""

    ledger: Ledger
    store: Store


type FamilyTasksConfigEntry = ConfigEntry[FamilyTasksData]


def _now() -> str:
    return dt_util.utcnow().isoformat()


def _loaded_entry(hass: HomeAssistant) -> FamilyTasksConfigEntry:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_loaded")
    return entries[0]


def _display_name(hass: HomeAssistant, person: str) -> str:
    """Use the person entity's friendly name when the key is a person.*."""
    if person.startswith("person.") and (state := hass.states.get(person)):
        return str(state.attributes.get("friendly_name", person))
    return person


@callback
def _changed(
    hass: HomeAssistant, data: FamilyTasksData, person: str, kind: str, points: int, label: str
) -> None:
    """Save, refresh the person's sensor and tell automations."""
    data.store.async_delay_save(data.ledger.as_dict, 1)
    async_dispatcher_send(hass, SIGNAL_UPDATED, person)
    hass.bus.async_fire(
        EVENT_POINTS_CHANGED,
        {
            "person": person,
            "kind": kind,
            "points": points,
            "label": label,
            "balance": data.ledger.totals(person).balance,
        },
    )


@callback
def _offers_changed(hass: HomeAssistant, data: FamilyTasksData, persons: set[str]) -> None:
    """Save and refresh the sensors of everyone an offer concerns."""
    data.store.async_delay_save(data.ledger.as_dict, 1)
    for person in persons:
        async_dispatcher_send(hass, SIGNAL_UPDATED, person)


@callback
def _prune(hass: HomeAssistant, data: FamilyTasksData) -> None:
    """Forget offers whose round is over, and covers that no longer matter."""
    today = dt_util.now().date()
    gone = data.ledger.prune(today.isoformat())
    old = data.ledger.prune_covers(
        today.isoformat(), (today - timedelta(days=COVER_DAYS)).isoformat()
    )
    persons = {p for o in gone for p in (o.sender, o.receiver)}
    persons |= {p for c in old for p in (c.helper, c.absent)}
    if persons:
        _offers_changed(hass, data, persons)


def _offer_event(off: Offer) -> dict[str, Any]:
    return {
        "offer_id": off.id,
        "key": off.key,
        "chore": off.chore,
        "from": off.sender,
        "to": off.receiver,
        "points": off.points,
    }


def _insufficient(person: str, err: InsufficientPoints, points: int) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="insufficient_points",
        translation_placeholders={
            "person": person,
            "balance": str(err.balance),
            "points": str(points),
        },
    )


async def _notify_parents(
    hass: HomeAssistant, entry: FamilyTasksConfigEntry, payload: dict[str, Any]
) -> None:
    """Send to every configured phone; one that is gone doesn't stop the others."""
    for target in entry.options.get(CONF_NOTIFY, []):
        if not hass.services.has_service("notify", target):
            _LOGGER.warning(
                "notify.%s not found - pick the parents' phones again in the integration options",
                target,
            )
            continue
        try:
            await hass.services.async_call("notify", target, payload, blocking=False)
        except (HomeAssistantError, vol.Invalid) as err:
            _LOGGER.warning("Could not notify %s: %s", target, err)


async def _push(hass: HomeAssistant, entry: FamilyTasksConfigEntry, req: Request) -> None:
    """Ask the parents: an actionable notification to every configured target."""
    text = PUSH_TEXT.get(hass.config.language.split("-")[0], PUSH_TEXT["en"])
    message = text["message"].format(
        person=_display_name(hass, req.person), reward=req.label or "?", points=req.points
    )
    payload = {
        "title": text["title"],
        "message": message,
        "data": {
            "tag": f"{DOMAIN}_{req.id}",
            "actions": [
                {"action": f"{ACTION_APPROVE}{req.id}", "title": text["approve"]},
                {"action": f"{ACTION_DENY}{req.id}", "title": text["deny"]},
            ],
        },
    }
    await _notify_parents(hass, entry, payload)


async def _clear_push(hass: HomeAssistant, entry: FamilyTasksConfigEntry, request_id: str) -> None:
    """Remove the request's push from every parent's phone once it is decided."""
    await _notify_parents(
        hass,
        entry,
        {"message": "clear_notification", "data": {"tag": f"{DOMAIN}_{request_id}"}},
    )


async def _decide(
    hass: HomeAssistant, entry: FamilyTasksConfigEntry, request_id: str, approve: bool
) -> Request | None:
    """Approve or deny a request; None if it was already decided (or unknown)."""
    data = entry.runtime_data
    req = data.ledger.approve(request_id, _now()) if approve else data.ledger.deny(request_id)
    if req is None:
        return None
    if approve:
        _changed(hass, data, req.person, "redeem", -req.points, req.label)
    else:
        data.store.async_delay_save(data.ledger.as_dict, 1)
        async_dispatcher_send(hass, SIGNAL_UPDATED, req.person)
    hass.bus.async_fire(
        EVENT_REWARD_DECIDED,
        {
            "request_id": req.id,
            "person": req.person,
            "reward": req.label,
            "points": req.points,
            "approved": approve,
        },
    )
    await _clear_push(hass, entry, req.id)
    return req


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the services (they look up the loaded entry when called)."""

    async def award(call: ServiceCall) -> ServiceResponse:
        data = _loaded_entry(hass).runtime_data
        person, points, task = call.data[ATTR_PERSON], call.data[ATTR_POINTS], call.data[ATTR_TASK]
        booked = data.ledger.award(call.data[ATTR_KEY], person, points, task, _now())
        if booked:
            _changed(hass, data, person, "award", points, task)
        return {"awarded": booked, "balance": data.ledger.totals(person).balance}

    async def revoke(call: ServiceCall) -> ServiceResponse:
        data = _loaded_entry(hass).runtime_data
        gone = data.ledger.revoke(call.data[ATTR_KEY])
        if gone:
            _changed(hass, data, gone.person, "revoke", -gone.points, gone.label)
        # a chore done for someone, or in return, no longer counts either
        undone = data.ledger.undo_cover(call.data[ATTR_KEY])
        if undone:
            _offers_changed(hass, data, {p for c in undone for p in (c.helper, c.absent)})
        return {"revoked": gone is not None}

    async def redeem(call: ServiceCall) -> ServiceResponse:
        data = _loaded_entry(hass).runtime_data
        person, points, reward = (
            call.data[ATTR_PERSON],
            call.data[ATTR_POINTS],
            call.data[ATTR_REWARD],
        )
        try:
            data.ledger.redeem(person, points, reward, _now())
        except InsufficientPoints as err:
            raise _insufficient(person, err, points) from err
        _changed(hass, data, person, "redeem", -points, reward)
        return {"balance": data.ledger.totals(person).balance}

    async def adjust(call: ServiceCall) -> ServiceResponse:
        data = _loaded_entry(hass).runtime_data
        person, points, reason = (
            call.data[ATTR_PERSON],
            call.data[ATTR_POINTS],
            call.data[ATTR_REASON],
        )
        data.ledger.adjust(person, points, reason, _now())
        _changed(hass, data, person, "adjust", points, reason)
        return {"balance": data.ledger.totals(person).balance}

    async def request_reward(call: ServiceCall) -> ServiceResponse:
        entry = _loaded_entry(hass)
        data = entry.runtime_data
        person, points, reward = (
            call.data[ATTR_PERSON],
            call.data[ATTR_POINTS],
            call.data[ATTR_REWARD],
        )
        try:
            req = data.ledger.request(ulid_now(), person, points, reward, _now())
        except InsufficientPoints as err:
            raise _insufficient(person, err, points) from err
        data.store.async_delay_save(data.ledger.as_dict, 1)
        async_dispatcher_send(hass, SIGNAL_UPDATED, person)
        hass.bus.async_fire(
            EVENT_REWARD_REQUESTED,
            {"request_id": req.id, "person": person, "reward": reward, "points": points},
        )
        await _push(hass, entry, req)
        return {"request_id": req.id, "available": data.ledger.available(person)}

    async def approve(call: ServiceCall) -> ServiceResponse:
        req = await _decide(hass, _loaded_entry(hass), call.data[ATTR_REQUEST_ID], True)
        return {"decided": req is not None}

    async def deny(call: ServiceCall) -> ServiceResponse:
        req = await _decide(hass, _loaded_entry(hass), call.data[ATTR_REQUEST_ID], False)
        return {"decided": req is not None}

    async def offer_chore(call: ServiceCall) -> ServiceResponse:
        data = _loaded_entry(hass).runtime_data
        _prune(hass, data)
        sender, receiver, points = (
            call.data[ATTR_PERSON],
            call.data[ATTR_TO],
            call.data[ATTR_POINTS],
        )
        until = call.data.get(ATTR_UNTIL) or dt_util.now().date()
        try:
            off = data.ledger.offer(
                ulid_now(),
                call.data[ATTR_KEY],
                call.data[ATTR_CHORE],
                sender,
                receiver,
                points,
                until.isoformat(),
                _now(),
            )
        except InsufficientPoints as err:
            raise _insufficient(sender, err, points) from err
        except OfferRefused as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key=err.reason
            ) from err
        _offers_changed(hass, data, {sender, receiver})
        hass.bus.async_fire(EVENT_CHORE_OFFERED, _offer_event(off))
        return {"offer_id": off.id, "available": data.ledger.available(sender)}

    async def answer_offer(call: ServiceCall) -> ServiceResponse:
        data = _loaded_entry(hass).runtime_data
        _prune(hass, data)  # a round that is over can't be taken over any more
        accept = call.data[ATTR_ACCEPT]
        off = data.ledger.answer(call.data[ATTR_OFFER_ID], accept, _now())
        if off is None:
            return {"answered": False}
        if accept and off.points:
            label = f"🔁 {off.chore}".strip()
            _changed(hass, data, off.sender, "transfer", -off.points, label)
            _changed(hass, data, off.receiver, "transfer", off.points, label)
        else:
            _offers_changed(hass, data, {off.sender, off.receiver})
        hass.bus.async_fire(EVENT_CHORE_ANSWERED, {**_offer_event(off), "accepted": accept})
        return {"answered": True}

    async def cover(call: ServiceCall) -> ServiceResponse:
        data = _loaded_entry(hass).runtime_data
        helper, absent = call.data[ATTR_PERSON], call.data[ATTR_ABSENT]
        if helper == absent:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="offer_self")
        noted = data.ledger.cover(
            call.data[ATTR_KEY], helper, absent, call.data[ATTR_CHORE], _now()
        )
        if noted:
            _offers_changed(hass, data, {helper, absent})
        return {"covered": noted is not None}

    async def even_out(call: ServiceCall) -> ServiceResponse:
        data = _loaded_entry(hass).runtime_data
        person, helper = call.data[ATTR_PERSON], call.data[ATTR_HELPER]
        done = data.ledger.even_out(call.data[ATTR_KEY], person, helper)
        if done:
            _offers_changed(hass, data, {person, helper})
        return {"evened": done is not None}

    for name, handler, schema in (
        (SERVICE_AWARD, award, AWARD_SCHEMA),
        (SERVICE_REVOKE, revoke, REVOKE_SCHEMA),
        (SERVICE_REDEEM, redeem, REWARD_SCHEMA),
        (SERVICE_ADJUST, adjust, ADJUST_SCHEMA),
        (SERVICE_REQUEST_REWARD, request_reward, REWARD_SCHEMA),
        (SERVICE_APPROVE, approve, DECIDE_SCHEMA),
        (SERVICE_DENY, deny, DECIDE_SCHEMA),
        (SERVICE_OFFER_CHORE, offer_chore, OFFER_SCHEMA),
        (SERVICE_ANSWER_OFFER, answer_offer, ANSWER_SCHEMA),
        (SERVICE_COVER, cover, COVER_SCHEMA),
        (SERVICE_EVEN_OUT, even_out, EVEN_OUT_SCHEMA),
    ):
        hass.services.async_register(
            DOMAIN, name, handler, schema=schema, supports_response=SupportsResponse.OPTIONAL
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: FamilyTasksConfigEntry) -> bool:
    """Load the ledger, the sensors and listen for "approve" / "deny" taps."""
    store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    entry.runtime_data = FamilyTasksData(Ledger.from_dict(await store.async_load()), store)

    async def _on_action(event: Event) -> None:
        action = str(event.data.get("action", ""))
        for prefix, yes in ((ACTION_APPROVE, True), (ACTION_DENY, False)):
            if action.startswith(prefix):
                await _decide(hass, entry, action.removeprefix(prefix), yes)

    entry.async_on_unload(hass.bus.async_listen(EVENT_NOTIFICATION_ACTION, _on_action))

    @callback
    def _new_day(_now: Any) -> None:
        _prune(hass, entry.runtime_data)

    # Offers end with their round: drop them just after midnight (and now).
    _prune(hass, entry.runtime_data)
    entry.async_on_unload(async_track_time_change(hass, _new_day, hour=0, minute=0, second=1))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FamilyTasksConfigEntry) -> bool:
    """Write pending bookings before unloading."""
    data = entry.runtime_data
    await data.store.async_save(data.ledger.as_dict())
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
