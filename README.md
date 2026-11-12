# ⭐ Family Task Card Integration

> 🌐 **English** (this page) · [Deutsch](README.de.md)

![Family Task Card Integration icon](custom_components/family_tasks/brand/icon.png)

A **persistent points ledger** for the
[Family Task Card](https://github.com/renespeaker/ha-family-task-card) in
[Home Assistant](https://www.home-assistant.io/). Without it, the card works out
points live from checked-off tasks — simple, but points disappear when a list is
cleared, and chores that reopen every round can't earn any. With this
integration, **every point is booked and kept**, and each person gets a points
sensor.

> **Status: v0.4.0 — points ledger, reward approval by push, statistics, handing
> chores over.** Use it with the Family Task Card v0.14.0 or newer
> (`points_backend: true`); handing chores over needs card v0.20.0. Formerly
> called *Family Tasks* — only the name changed.

## What you get

- **A points sensor per person**, e.g. `sensor.lina_points` — spendable points as
  the state, plus `earned`, `redeemed`, `reserved`, `pending` requests and chore
  `offers`. Works with history graphs, statistics and automations.
- **Bookings that never count twice.** Every award has a unique key (the card uses
  list + task, plus the round for rotating chores). When phone and wall tablet
  both report the same task, it is booked once.
- **Services** for the card and your own automations:

  | Service | What it does |
  |---|---|
  | `family_tasks.award` | book points for a task (`key`, `person`, `points`, `task`) |
  | `family_tasks.revoke` | take an award back, e.g. when a task is unchecked (`key`) |
  | `family_tasks.redeem` | spend points on a reward; refuses if there are too few (`person`, `points`, `reward`) |
  | `family_tasks.adjust` | bonus (positive) or deduction (negative) by a parent (`person`, `points`, `reason`) |
  | `family_tasks.request_reward` | a child asks for a reward: points are reserved, parents get a push (`person`, `points`, `reward`) |
  | `family_tasks.approve` / `deny` | decide a request (`request_id`) — or tap the button in the push |
  | `family_tasks.offer_chore` | hand a chore of this round to someone else, maybe for points (`key`, `person`, `to`, `points`, `chore`, `until`) |
  | `family_tasks.answer_offer` | take the chore over, turn it down or withdraw the offer (`offer_id`, `accept`) |

  All return the new balance (`return_response`).
- **An event** `family_tasks_points_changed` for every booking — e.g. to flash a
  light when someone earns points.
- Stored inside Home Assistant (`.storage/family_tasks`), no cloud, nothing to
  configure.

## Reward approval by push

A child asks for a reward (`family_tasks.request_reward`, or the card with
*reward approval* switched on). The points are **reserved** at once — nobody can
ask for more than is left — and the parents get a **push with "Approve" /
"Deny"** on their phones:

- **Approve** spends the reserved points, **Deny** frees them again.
- Only the first decision counts; the push then disappears from the other
  parents' phones too.
- Open requests are kept across restarts and show up in the sensor
  (`reserved`, `pending`).

**Who gets the push:** Settings → Devices & services → Family Task Card
Integration → **Configure** → pick the notify services of the parents' phones
(`notify.mobile_app_…`, from the Home Assistant Companion app). Without a target,
requests can still be decided with `family_tasks.approve` / `deny`.

Events for your own automations: `family_tasks_reward_requested` and
`family_tasks_reward_decided` (with `approved: true/false`).

## Handing chores over

A chore of this round can go to someone else: Lina offers "Take out the bins"
to Ben, maybe for 10 points (`family_tasks.offer_chore`, or the card with
*handing chores over* switched on).

- The points are **reserved** until Ben answers.
- **Ben takes it over:** the chore is his for this round and the 10 points move
  from Lina to Ben. Who does the chore gets its points as usual.
- **Ben says no**, or Lina withdraws the offer: the points are free again.
- An offer ends with its round, answered or not.
- Points that move for a chore are a transfer: they change what someone can
  spend (`transferred` on the sensor), not what they earned — so the statistics
  and the fair-share bar still count only work done.

Events for your own automations, e.g. a push to Ben's phone:
`family_tasks_chore_offered` and `family_tasks_chore_answered` (with
`accepted: true/false`).

## Statistics

Every points sensor also counts, in Home Assistant's time zone:

| Attribute | Meaning |
|---|---|
| `week_points` / `week_tasks` | points earned / tasks done this week (from Monday) |
| `month_points` / `month_tasks` | the same for this calendar month |
| `streak` | days in a row with at least one task, up to today (or yesterday, until today's first task) |
| `best_streak` | the longest run so far |

The numbers roll over by themselves just after midnight. A task counts on the
day it is booked — the card books a task when it sees it checked off.

## Installation

### Via the Marketplace or HACS (recommended)

[![Open the Family Task Card Integration in the Marketplace or HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=renespeaker&repository=ha-family-task-integration&category=integration)
[![Add the Family Task Card Integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=family_tasks)

1. Home Assistant 2026.11 or newer: **Settings → Marketplace**, search for
   **"Family Task Card Integration"** and install it. Older versions: download
   it in **HACS** and restart Home Assistant. The first button above opens the
   right one.
2. Add the integration with the second button, or via **Settings → Devices &
   services → Add integration → Family Task Card Integration** → Submit. There
   is nothing to fill in.

> **Not listed yet?** Add it as a custom repository (*Custom repositories* in the
> Marketplace or in HACS): `https://github.com/renespeaker/ha-family-task-integration`,
> type **Integration**.

People appear with their first booking. Use the `person.*` entity as `person`
(e.g. `person.lina`) and the device is named after the person.

### Manual

Copy `custom_components/family_tasks` into your `config/custom_components/`,
restart, then add the integration as above.

## Examples

```yaml
# Bonus for helping without being asked
action: family_tasks.adjust
data:
  person: person.lina
  points: 20
  reason: Helped without being asked
```

```yaml
# Flash the kids' room light green on every booking for Lina
triggers:
  - trigger: event
    event_type: family_tasks_points_changed
    event_data:
      person: person.lina
actions:
  - action: light.turn_on
    target: { entity_id: light.kids_room }
    data: { rgb_color: [0, 255, 0], flash: short }
```

## Development

```bash
uv venv -p 3.13 .venv
uv pip install -p .venv/bin/python -r requirements_test.txt
.venv/bin/python -m pytest -q
uvx ruff@0.16.10 check . && uvx ruff@0.16.10 format --check .
```

## License

MIT
