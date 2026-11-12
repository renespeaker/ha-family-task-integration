"""The points ledger: every booking per person, persisted by the integration.

Kept free of Home Assistant imports so the bookkeeping rules can be tested on
their own.

An award carries a unique key chosen by the caller (the card uses list + task,
plus the round for rotating chores). Awarding the same key twice does nothing,
so several devices reporting the same checked-off task book it only once.

A reward request reserves its points until a parent approves (it becomes a
redemption) or denies it (the points are free again). Reserved points can't be
requested or redeemed a second time.

A chore can be handed to someone else for one round, maybe for points: the
offer reserves them until the other person takes the chore (the points move
over as a transfer) or turns it down. A transfer changes what someone can
spend, not what they earned: it is no work done. Offers end with their round.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any, Literal

Kind = Literal["award", "redeem", "adjust", "transfer"]


class OfferRefused(Exception):
    """An offer that can't be made; `reason` names the translated message."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InsufficientPoints(Exception):
    """A redemption costs more than the person has."""

    def __init__(self, person: str, balance: int, points: int) -> None:
        super().__init__(f"{person} has {balance} points, needs {points}")
        self.person = person
        self.balance = balance
        self.points = points


@dataclass(frozen=True)
class Booking:
    """One line in the ledger."""

    kind: Kind
    person: str
    points: int  # as booked: award/adjust/transfer add it (signed), redeem subtracts it
    label: str
    at: str  # ISO timestamp
    key: str | None = None  # awards only


@dataclass(frozen=True)
class Request:
    """A reward asked for, waiting for a parent."""

    id: str
    person: str
    points: int
    label: str
    at: str


@dataclass(frozen=True)
class Offer:
    """A chore handed to someone else for one round, maybe for points."""

    id: str
    key: str  # the chore in this round, as the card books it
    chore: str
    sender: str
    receiver: str
    points: int
    until: str  # last day it matters (YYYY-MM-DD): the end of the round
    at: str
    accepted: bool = False


@dataclass(frozen=True)
class Totals:
    """What a person has: earned (awards + adjustments), redeemed, transfers and the rest."""

    earned: int
    redeemed: int
    transferred: int = 0  # points handed over for chores: received minus paid

    @property
    def balance(self) -> int:
        return self.earned - self.redeemed + self.transferred


@dataclass
class Ledger:
    """All bookings, oldest first."""

    bookings: list[Booking] = field(default_factory=list)
    requests: list[Request] = field(default_factory=list)
    offers: list[Offer] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Ledger:
        if not data:
            return cls()
        return cls(
            [Booking(**b) for b in data.get("bookings", [])],
            [Request(**r) for r in data.get("requests", [])],
            [Offer(**o) for o in data.get("offers", [])],
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "bookings": [asdict(b) for b in self.bookings],
            "requests": [asdict(r) for r in self.requests],
            "offers": [asdict(o) for o in self.offers],
        }

    def _award_index(self, key: str) -> int | None:
        for i, b in enumerate(self.bookings):
            if b.kind == "award" and b.key == key:
                return i
        return None

    def award(self, key: str, person: str, points: int, label: str, at: str) -> bool:
        """Book points for a task. False when this key was already booked."""
        if points < 0:
            raise ValueError("award points must not be negative")
        if self._award_index(key) is not None:
            return False
        self.bookings.append(Booking("award", person, points, label, at, key))
        return True

    def revoke(self, key: str) -> Booking | None:
        """Take an award back (task unchecked). Returns what was removed."""
        i = self._award_index(key)
        return self.bookings.pop(i) if i is not None else None

    def redeem(self, person: str, points: int, label: str, at: str) -> None:
        """Spend points on a reward; refuses to go below zero."""
        if points <= 0:
            raise ValueError("redeem points must be positive")
        available = self.available(person)
        if points > available:
            raise InsufficientPoints(person, available, points)
        self.bookings.append(Booking("redeem", person, points, label, at))

    def request(self, request_id: str, person: str, points: int, label: str, at: str) -> Request:
        """Ask for a reward: reserve its points until a parent decides."""
        if points <= 0:
            raise ValueError("request points must be positive")
        available = self.available(person)
        if points > available:
            raise InsufficientPoints(person, available, points)
        req = Request(request_id, person, points, label, at)
        self.requests.append(req)
        return req

    def _take_request(self, request_id: str) -> Request | None:
        for i, r in enumerate(self.requests):
            if r.id == request_id:
                return self.requests.pop(i)
        return None

    def approve(self, request_id: str, at: str) -> Request | None:
        """A parent said yes: the reserved points are spent."""
        req = self._take_request(request_id)
        if req:
            self.bookings.append(Booking("redeem", req.person, req.points, req.label, at))
        return req

    def deny(self, request_id: str) -> Request | None:
        """A parent said no: the reserved points are free again."""
        return self._take_request(request_id)

    def pending(self, person: str) -> list[Request]:
        return [r for r in self.requests if r.person == person]

    def reserved(self, person: str) -> int:
        """Points held back for open reward requests and open chore offers."""
        offered = sum(o.points for o in self.offers if o.sender == person and not o.accepted)
        return sum(r.points for r in self.pending(person)) + offered

    def available(self, person: str) -> int:
        """What can still be spent: balance minus reserved points."""
        return self.totals(person).balance - self.reserved(person)

    def offer(
        self,
        offer_id: str,
        key: str,
        chore: str,
        sender: str,
        receiver: str,
        points: int,
        until: str,
        at: str,
    ) -> Offer:
        """Hand a chore of this round to someone else; its points wait for the answer.

        A new offer for the same chore replaces an open one. A chore already
        taken over this round can't be offered again.
        """
        if points < 0:
            raise ValueError("offer points must not be negative")
        if sender == receiver:
            raise OfferRefused("offer_self")
        if any(o.key == key and o.accepted for o in self.offers):
            raise OfferRefused("offer_taken")
        self.offers = [o for o in self.offers if not (o.key == key and not o.accepted)]
        available = self.available(sender)
        if points > available:
            raise InsufficientPoints(sender, available, points)
        off = Offer(offer_id, key, chore, sender, receiver, points, until, at)
        self.offers.append(off)
        return off

    def answer(self, offer_id: str, accept: bool, at: str) -> Offer | None:
        """Take the chore over (its points move across) or turn it down / withdraw it.

        None when the offer is gone or already taken.
        """
        for i, o in enumerate(self.offers):
            if o.id != offer_id or o.accepted:
                continue
            if not accept:
                return self.offers.pop(i)
            taken = replace(o, accepted=True)
            self.offers[i] = taken
            if o.points:
                label = f"🔁 {o.chore}".strip()
                self.bookings.append(Booking("transfer", o.sender, -o.points, label, at))
                self.bookings.append(Booking("transfer", o.receiver, o.points, label, at))
            return taken
        return None

    def offers_of(self, person: str) -> list[Offer]:
        """Offers this person made or got, oldest first."""
        return [o for o in self.offers if person in (o.sender, o.receiver)]

    def prune(self, today: str) -> list[Offer]:
        """Forget offers whose round is over (open ones free their points). Returns them."""
        gone = [o for o in self.offers if o.until < today]
        if gone:
            self.offers = [o for o in self.offers if o.until >= today]
        return gone

    def adjust(self, person: str, points: int, label: str, at: str) -> None:
        """Bonus (positive) or deduction (negative) by a parent."""
        if points == 0:
            raise ValueError("adjust points must not be zero")
        self.bookings.append(Booking("adjust", person, points, label, at))

    def totals(self, person: str) -> Totals:
        mine = [b for b in self.bookings if b.person == person]
        earned = sum(b.points for b in mine if b.kind in ("award", "adjust"))
        redeemed = sum(b.points for b in mine if b.kind == "redeem")
        transferred = sum(b.points for b in mine if b.kind == "transfer")
        return Totals(earned, redeemed, transferred)

    def last(self, person: str) -> Booking | None:
        for b in reversed(self.bookings):
            if b.person == person:
                return b
        return None

    def persons(self) -> list[str]:
        """Everyone with at least one booking, in first-seen order."""
        seen: dict[str, None] = {}
        for b in self.bookings:
            seen.setdefault(b.person, None)
        for r in self.requests:
            seen.setdefault(r.person, None)
        for o in self.offers:
            seen.setdefault(o.sender, None)
            seen.setdefault(o.receiver, None)
        return list(seen)
