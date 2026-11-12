# ⭐ Family Tasks

> 🌐 **Deutsch** (diese Seite) · [English](README.md)

![Family-Tasks-Icon](custom_components/family_tasks/brand/icon.png)

Ein **dauerhaftes Punktekonto** für die
[Family Task Card](https://github.com/renespeaker/ha-family-task-card) in
[Home Assistant](https://www.home-assistant.io/). Ohne sie berechnet die Karte
Punkte live aus den abgehakten Aufgaben – einfach, aber Punkte verschwinden,
wenn eine Liste geleert wird, und Ämtli, die jede Runde wieder öffnen, können
keine bekommen. Mit Family Tasks wird **jeder Punkt gebucht und bleibt**, und jede
Person bekommt einen Punkte-Sensor.

> **Stand: v0.3.2 – Punktekonto, Belohnungs-Freigabe per Push, Statistik.**
> Zusammen mit der Family Task Card ab v0.14.0 nutzen (`points_backend: true`).

## Was du bekommst

- **Einen Punkte-Sensor pro Person**, z. B. `sensor.lina_punkte` – ausgebbare Punkte
  als Zustand, dazu `earned` (verdient), `redeemed` (eingelöst), `reserved`
  (reserviert) und offene Anfragen (`pending`). Funktioniert
  mit Verlauf, Statistik und Automationen.
- **Buchungen, die nie doppelt zählen.** Jede Gutschrift hat einen eindeutigen
  Schlüssel (die Karte nimmt Liste + Aufgabe, bei Ämtli zusätzlich die Runde).
  Melden Handy und Wandtablet dieselbe Aufgabe, wird sie einmal gebucht.
- **Dienste** für die Karte und eigene Automationen:

  | Dienst | Was er tut |
  |---|---|
  | `family_tasks.award` | Punkte für eine Aufgabe buchen (`key`, `person`, `points`, `task`) |
  | `family_tasks.revoke` | Gutschrift zurücknehmen, z. B. wenn der Haken entfernt wird (`key`) |
  | `family_tasks.redeem` | Punkte für eine Belohnung ausgeben; lehnt ab, wenn es zu wenige sind (`person`, `points`, `reward`) |
  | `family_tasks.adjust` | Bonus (positiv) oder Abzug (negativ) durch die Eltern (`person`, `points`, `reason`) |
  | `family_tasks.request_reward` | Kind fragt eine Belohnung an: Punkte werden reserviert, Eltern bekommen eine Push (`person`, `points`, `reward`) |
  | `family_tasks.approve` / `deny` | Anfrage entscheiden (`request_id`) – oder den Knopf in der Push antippen |

  Alle liefern den neuen Kontostand zurück (`return_response`).
- **Ein Ereignis** `family_tasks_points_changed` bei jeder Buchung – z. B. um ein
  Licht blinken zu lassen, wenn jemand Punkte bekommt.
- Gespeichert in Home Assistant selbst (`.storage/family_tasks`), keine Cloud,
  nichts einzustellen.

## Belohnungs-Freigabe per Push

Ein Kind fragt eine Belohnung an (`family_tasks.request_reward`, oder die Karte
mit eingeschalteter *Belohnungs-Freigabe*). Die Punkte werden sofort
**reserviert** – niemand kann mehr anfragen, als übrig ist – und die Eltern
bekommen eine **Push-Nachricht mit „Freigeben" / „Ablehnen"** aufs Handy:

- **Freigeben** gibt die reservierten Punkte aus, **Ablehnen** gibt sie wieder frei.
- Nur die erste Entscheidung zählt; danach verschwindet die Push auch von den
  Handys der anderen Eltern.
- Offene Anfragen überstehen Neustarts und stehen im Sensor (`reserved`,
  `pending`).

**Wer die Push bekommt:** Einstellungen → Geräte & Dienste → Family Tasks →
**Konfigurieren** → die Benachrichtigungsdienste der Eltern-Handys wählen
(`notify.mobile_app_…`, aus der Home-Assistant-Companion-App). Ohne Ziel lassen
sich Anfragen trotzdem mit `family_tasks.approve` / `deny` entscheiden.

Ereignisse für eigene Automationen: `family_tasks_reward_requested` und
`family_tasks_reward_decided` (mit `approved: true/false`).

## Statistik

Jeder Punkte-Sensor zählt außerdem, in der Zeitzone von Home Assistant:

| Attribut | Bedeutung |
|---|---|
| `week_points` / `week_tasks` | verdiente Punkte / erledigte Aufgaben diese Woche (ab Montag) |
| `month_points` / `month_tasks` | dasselbe für den laufenden Monat |
| `streak` | Tage am Stück mit mindestens einer Aufgabe, bis heute (oder gestern, bis zur ersten Aufgabe heute) |
| `best_streak` | die bisher längste Serie |

Die Werte schalten kurz nach Mitternacht von selbst weiter. Eine Aufgabe zählt an
dem Tag, an dem sie gebucht wird – die Karte bucht eine Aufgabe, sobald sie sie
abgehakt sieht.

## Installation

### Über HACS (empfohlen)

[![Family Tasks in HACS öffnen](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=renespeaker&repository=ha-family-task-integration&category=integration)
[![Integration Family Tasks hinzufügen](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=family_tasks)

1. In **HACS** nach **„Family Tasks"** suchen und herunterladen (oder den ersten
   Button oben nutzen), dann Home Assistant neu starten.
2. Die Integration mit dem zweiten Button hinzufügen oder über **Einstellungen →
   Geräte & Dienste → Integration hinzufügen → Family Tasks** → Absenden. Es gibt
   nichts auszufüllen.

> **In deinem HACS noch nicht zu finden?** Dann füge sie als benutzerdefiniertes
> Repository hinzu: HACS → ⋮ → **Benutzerdefinierte Repositories** (*Custom
> repositories*) → `https://github.com/renespeaker/ha-family-task-integration`, Typ
> **Integration**.

Personen erscheinen mit ihrer ersten Buchung. Nimm die `person.*`-Entität als
`person` (z. B. `person.lina`), dann heißt das Gerät wie die Person.

### Manuell

`custom_components/family_tasks` nach `config/custom_components/` kopieren, neu
starten und die Integration wie oben hinzufügen.

## Beispiele

```yaml
# Bonus fürs Helfen ohne Aufforderung
action: family_tasks.adjust
data:
  person: person.lina
  points: 20
  reason: Ohne Aufforderung geholfen
```

```yaml
# Kinderzimmer-Licht bei jeder Buchung für Lina grün blinken lassen
triggers:
  - trigger: event
    event_type: family_tasks_points_changed
    event_data:
      person: person.lina
actions:
  - action: light.turn_on
    target: { entity_id: light.kinderzimmer }
    data: { rgb_color: [0, 255, 0], flash: short }
```

## Entwicklung

```bash
uv venv -p 3.13 .venv
uv pip install -p .venv/bin/python -r requirements_test.txt
.venv/bin/python -m pytest -q
uvx ruff@0.16.10 check . && uvx ruff@0.16.10 format --check .
```

## Lizenz

MIT
