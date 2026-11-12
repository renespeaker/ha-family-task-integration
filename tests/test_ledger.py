"""The bookkeeping rules, without Home Assistant."""

import pytest

from custom_components.family_tasks.ledger import InsufficientPoints, Ledger, OfferRefused

T = "2026-10-09T10:00:00+00:00"


def test_award_books_once_per_key():
    led = Ledger()
    assert led.award("todo.lina|a1", "Lina", 10, "Tidy room", T)
    assert not led.award("todo.lina|a1", "Lina", 10, "Tidy room", T)  # second device
    assert led.totals("Lina").earned == 10


def test_revoke_takes_an_award_back():
    led = Ledger()
    led.award("k", "Lina", 10, "Tidy room", T)
    assert led.revoke("k").points == 10
    assert led.totals("Lina").earned == 0
    assert led.revoke("k") is None
    # and it can be earned again afterwards
    assert led.award("k", "Lina", 10, "Tidy room", T)


def test_redeem_spends_and_never_goes_below_zero():
    led = Ledger()
    led.award("k", "Lina", 30, "", T)
    led.redeem("Lina", 20, "Ice cream", T)
    assert (led.totals("Lina").balance, led.totals("Lina").redeemed) == (10, 20)
    with pytest.raises(InsufficientPoints) as err:
        led.redeem("Lina", 11, "Tablet", T)
    assert err.value.balance == 10
    assert led.totals("Lina").balance == 10


def test_adjust_adds_bonus_and_deduction_to_earned():
    led = Ledger()
    led.adjust("Ben", 20, "Helped", T)
    led.adjust("Ben", -5, "Fought", T)
    assert led.totals("Ben").earned == 15
    with pytest.raises(ValueError):
        led.adjust("Ben", 0, "", T)


def test_people_are_kept_apart():
    led = Ledger()
    led.award("a", "Lina", 10, "", T)
    led.award("b", "Ben", 5, "", T)
    assert (led.totals("Lina").balance, led.totals("Ben").balance) == (10, 5)
    assert led.persons() == ["Lina", "Ben"]


def test_survives_a_round_trip_through_storage():
    led = Ledger()
    led.award("a", "Lina", 10, "Bins", T)
    led.redeem("Lina", 4, "Sticker", T)
    again = Ledger.from_dict(led.as_dict())
    assert again == led
    assert not again.award("a", "Lina", 10, "Bins", T)


def test_rejects_nonsense():
    led = Ledger()
    with pytest.raises(ValueError):
        led.award("a", "Lina", -1, "", T)
    with pytest.raises(ValueError):
        led.redeem("Lina", 0, "", T)


def test_a_request_reserves_points_until_decided():
    led = Ledger()
    led.award("a", "Lina", 30, "", T)
    led.request("r1", "Lina", 20, "Ice cream", T)
    assert (led.totals("Lina").balance, led.reserved("Lina"), led.available("Lina")) == (30, 20, 10)
    with pytest.raises(InsufficientPoints):
        led.request("r2", "Lina", 15, "Tablet", T)  # only 10 left to ask for
    with pytest.raises(InsufficientPoints):
        led.redeem("Lina", 15, "Tablet", T)


def test_approve_spends_the_reserved_points():
    led = Ledger()
    led.award("a", "Lina", 30, "", T)
    led.request("r1", "Lina", 20, "Ice cream", T)
    assert led.approve("r1", T).label == "Ice cream"
    assert (led.totals("Lina").redeemed, led.available("Lina"), led.pending("Lina")) == (20, 10, [])
    assert led.approve("r1", T) is None  # the second parent's tap does nothing


def test_deny_frees_the_points_again():
    led = Ledger()
    led.award("a", "Lina", 30, "", T)
    led.request("r1", "Lina", 20, "Ice cream", T)
    assert led.deny("r1").points == 20
    assert (led.totals("Lina").redeemed, led.available("Lina")) == (0, 30)
    assert led.deny("r1") is None


def test_pending_requests_survive_storage():
    led = Ledger()
    led.award("a", "Lina", 30, "", T)
    led.request("r1", "Lina", 20, "Ice cream", T)
    again = Ledger.from_dict(led.as_dict())
    assert again.pending("Lina")[0].id == "r1"
    assert again.available("Lina") == 10
    # a v0.1 store without requests still loads
    assert Ledger.from_dict({"bookings": []}).requests == []


def _lina_has(points: int = 30) -> Ledger:
    led = Ledger()
    led.award("a", "Lina", points, "", T)
    return led


def test_an_offer_reserves_its_points_until_answered():
    led = _lina_has(30)
    led.offer("o1", "todo.chores|c1|2026-10-11", "Bins", "Lina", "Ben", 10, "2026-10-11", T)
    assert (led.reserved("Lina"), led.available("Lina")) == (10, 20)
    with pytest.raises(InsufficientPoints):
        led.offer("o2", "todo.chores|c2|2026-10-11", "Dishes", "Lina", "Ben", 25, "2026-10-11", T)


def test_taking_a_chore_over_moves_the_points_but_not_what_was_earned():
    led = _lina_has(30)
    led.offer("o1", "k", "Bins", "Lina", "Ben", 10, "2026-10-11", T)
    assert led.answer("o1", True, T).accepted
    lina, ben = led.totals("Lina"), led.totals("Ben")
    assert (lina.balance, lina.earned, led.available("Lina")) == (20, 30, 20)
    assert (ben.balance, ben.earned) == (10, 0)
    assert led.answer("o1", True, T) is None  # only once
    assert led.answer("o1", False, T) is None  # and a late "no" changes nothing
    assert led.totals("Ben").balance == 10


def test_turning_it_down_frees_the_points():
    led = _lina_has(30)
    led.offer("o1", "k", "Bins", "Lina", "Ben", 10, "2026-10-11", T)
    assert led.answer("o1", False, T).receiver == "Ben"
    assert (led.available("Lina"), led.offers) == (30, [])
    assert led.totals("Ben").balance == 0


def test_a_free_offer_moves_no_points():
    led = Ledger()
    led.offer("o1", "k", "Bins", "Lina", "Ben", 0, "2026-10-11", T)
    led.answer("o1", True, T)
    assert led.bookings == []
    assert led.offers_of("Ben")[0].accepted


def test_a_new_offer_replaces_the_open_one_and_a_chore_taken_over_stays_taken():
    led = _lina_has(30)
    led.offer("o1", "k", "Bins", "Lina", "Ben", 10, "d", T)
    led.offer("o2", "k", "Bins", "Lina", "Mia", 5, "d", T)
    assert [o.id for o in led.offers] == ["o2"]
    assert led.reserved("Lina") == 5
    led.answer("o2", True, T)
    with pytest.raises(OfferRefused) as err:
        led.offer("o3", "k", "Bins", "Mia", "Ben", 0, "d", T)
    assert err.value.reason == "offer_taken"


def test_no_offer_to_oneself_or_for_minus_points():
    with pytest.raises(OfferRefused) as err:
        Ledger().offer("o1", "k", "Bins", "Lina", "Lina", 0, "d", T)
    assert err.value.reason == "offer_self"
    with pytest.raises(ValueError):
        Ledger().offer("o1", "k", "Bins", "Lina", "Ben", -1, "d", T)


def test_offers_end_with_their_round():
    led = _lina_has(30)
    led.offer("o1", "k1", "Bins", "Lina", "Ben", 10, "2026-10-11", T)
    led.offer("o2", "k2", "Dishes", "Lina", "Ben", 0, "2026-10-18", T)
    assert [o.id for o in led.prune("2026-10-12")] == ["o1"]
    assert [o.id for o in led.offers] == ["o2"]
    assert led.available("Lina") == 30  # the open offer's points are free again
    assert led.prune("2026-10-12") == []


def test_offers_survive_storage_and_bring_their_people():
    led = _lina_has(30)
    led.offer("o1", "k", "Bins", "Lina", "Ben", 10, "2026-10-11", T)
    led.answer("o1", True, T)
    again = Ledger.from_dict(led.as_dict())
    assert again == led
    assert again.persons() == ["Lina", "Ben"]
    # a v0.3 store without offers still loads
    assert Ledger.from_dict({"bookings": [], "requests": []}).offers == []
