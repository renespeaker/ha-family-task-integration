# ⭐ Family Task Card Integration

> 🌐 **Deutsch** (diese Seite) · [English](README.md)

![Icon der Family Task Card Integration](custom_components/family_tasks/brand/icon.png)

Ein **dauerhaftes Punktekonto** für die
[Family Task Card](https://github.com/renespeaker/ha-family-task-card) in
[Home Assistant](https://www.home-assistant.io/). Ohne sie berechnet die Karte
Punkte live aus den abgehakten Aufgaben – einfach, aber Punkte verschwinden,
wenn eine Liste geleert wird, und Ämtli, die jede Runde wieder öffnen, können
keine bekommen. Mit dieser Integration wird **jeder Punkt gebucht und bleibt**,
und jede Person bekommt einen Punkte-Sensor.

> **Stand: v0.5.0 – Punktekonto, Belohnungs-Freigabe per Push, Statistik, Ämtli
> abgeben, Ausgleich fürs Einspringen.** Zusammen mit der Family Task Card ab
> v0.14.0 nutzen (`points_backend: true`); Ämtli abgeben braucht die Karte ab
> v0.20.0, den Ausgleich ab v0.21.0. Früher hieß sie *Family Tasks* – nur der Name
> ist neu.

## Was du bekommst

- **Einen Punkte-Sensor pro Person**, z. B. `sensor.lina_punkte` – ausgebbare Punkte
  als Zustand, dazu `earned` (verdient), `redeemed` (eingelöst), `reserved`
  (reserviert), offene Anfragen (`pending`), Ämtli-Angebote (`offers`) und
  Einspringen (`covers`). Funktioniert mit Verlauf, Statistik und Automationen.
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
  | `family_tasks.offer_chore` | ein Ämtli dieser Runde an jemand anderen abgeben, auf Wunsch gegen Punkte (`key`, `person`, `to`, `points`, `chore`, `until`) |
  | `family_tasks.answer_offer` | das Ämtli übernehmen, ablehnen oder das Angebot zurückziehen (`offer_id`, `accept`) |
  | `family_tasks.cover` | vermerken, dass jemand ein Ämtli für eine abwesende Person erledigt hat (`key`, `person`, `absent`, `chore`) |
  | `family_tasks.even_out` | das Ämtli vermerken, das sie im Gegenzug erledigt hat (`key`, `person`, `helper`) |

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

**Wer die Push bekommt:** Einstellungen → Geräte & Dienste → Family Task Card
Integration → **Konfigurieren** → die Benachrichtigungsdienste der Eltern-Handys wählen
(`notify.mobile_app_…`, aus der Home-Assistant-Companion-App). Ohne Ziel lassen
sich Anfragen trotzdem mit `family_tasks.approve` / `deny` entscheiden.

Ereignisse für eigene Automationen: `family_tasks_reward_requested` und
`family_tasks_reward_decided` (mit `approved: true/false`).

## Ämtli abgeben

Ein Ämtli dieser Runde kann an jemand anderen gehen: Lina bietet Ben „Müll
rausbringen" an, auf Wunsch für 10 Punkte (`family_tasks.offer_chore`, oder die
Karte mit eingeschaltetem *Ämtli abgeben*).

- Die Punkte sind **reserviert**, bis Ben antwortet.
- **Ben übernimmt:** Das Ämtli gehört in dieser Runde ihm, und die 10 Punkte
  wandern von Lina zu Ben. Wer das Ämtli erledigt, bekommt wie immer seine
  Punkte.
- **Ben lehnt ab**, oder Lina zieht das Angebot zurück: Die Punkte sind wieder
  frei.
- Ein Angebot endet mit seiner Runde, beantwortet oder nicht.
- Punkte, die für ein Ämtli wandern, sind ein Übertrag: Sie ändern, was jemand
  ausgeben kann (`transferred` am Sensor), nicht, was er verdient hat – Statistik
  und Fairness-Anzeige zählen also weiter nur erledigte Arbeit.

Ereignisse für eigene Automationen, z. B. eine Push an Bens Handy:
`family_tasks_chore_offered` und `family_tasks_chore_answered` (mit
`accepted: true/false`).

## Ausgleich fürs Einspringen

Ist jemand weg, verteilt die Karte seine Ämtli auf die anderen. Das Punktekonto
merkt sich, wer für wen eingesprungen ist, damit das später ausgeglichen werden
kann (Karten-Option *Nachholen*):

- Lina erledigt Bens Ämtli, während er weg ist: `family_tasks.cover` vermerkt,
  dass Ben Lina eins schuldet. Jedes Gerät darf das melden; es zählt einmal.
- Wieder zu Hause, bekommt Ben in einer späteren Runde eines von Linas Ämtli.
  Hat er es erledigt, begleicht `family_tasks.even_out` das älteste Ämtli, das er
  ihr schuldete.
- Haken weg macht den jeweiligen Teil rückgängig (`family_tasks.revoke`): Ein
  Ämtli, das Lina wieder öffnet, ist nicht mehr geschuldet; eines, das Ben wieder
  öffnet, wieder geschuldet.
- Ausgeglichenes wird nach seiner Runde vergessen, nie Ausgeglichenes nach 60
  Tagen.
- Jeder Sensor zeigt, wo seine Person eingesprungen ist oder wer für sie
  (`covers`).

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

### Über den Marketplace oder HACS (empfohlen)

[![Family Task Card Integration im Marketplace oder in HACS öffnen](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=renespeaker&repository=ha-family-task-integration&category=integration)
[![Family Task Card Integration hinzufügen](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=family_tasks)

1. Ab Home Assistant 2026.11: **Einstellungen → Marketplace**, nach
   **„Family Task Card Integration"** suchen und installieren. Ältere
   Versionen: in **HACS** herunterladen und Home Assistant neu starten. Der
   erste Button oben öffnet das Richtige.
2. Die Integration mit dem zweiten Button hinzufügen oder über **Einstellungen →
   Geräte & Dienste → Integration hinzufügen → Family Task Card Integration** →
   Absenden. Es gibt nichts auszufüllen.

> **Noch nicht zu finden?** Dann füge sie als benutzerdefiniertes Repository hinzu
> (*Custom repositories* im Marketplace oder in HACS):
> `https://github.com/renespeaker/ha-family-task-integration`, Typ **Integration**.

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
