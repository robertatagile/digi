"""The production data layout for calculate-don't-store, in miniature.

The kernel reference model scans every posting on every query. That is fine for proving invariants
and useless at volume. This module shows the layout that makes the same principle fast:

- positions are a daily snapshot plus the deltas since, keyed by (account, class)
- aggregate quantities per group (units in issue, adviser book, model) are maintained incrementally
- a price index holds the latest official price per class
- a value is a multiplication at read time; publishing a price writes one index entry and nothing else

Quantities are fixed-point integers: units in 1/10 000 of a unit, prices in 1/100 of a cent (cpu × 100),
money in cents. Exact, compact, and fast.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Optional

UNIT_SCALE = 10_000  # units carry 4 decimals
CPU_SCALE = 100  # cents per unit carry 2 decimals


def value_cents(units_1e4: int, cpu_1e2: int) -> int:
    """units × cents-per-unit ÷ 100, in cents, rounded half up. Integer arithmetic, exact."""
    numerator = units_1e4 * cpu_1e2  # units·cpu scaled by 1e4 · 1e2 = 1e6; cents = units·cpu / 100 → scale 1e4
    return (numerator + 5_000) // 10_000


@dataclass(frozen=True)
class PriceEntry:
    pricing_date: date
    version: int
    cpu_1e2: int


class PriceIndex:
    """Latest official price per class. O(1) publish, O(1) lookup. History lives in the price series."""

    def __init__(self) -> None:
        self._latest: dict[str, PriceEntry] = {}
        self.publications = 0

    def publish(self, class_id: str, pricing_date: date, cpu_1e2: int) -> PriceEntry:
        previous = self._latest.get(class_id)
        version = 1 if previous is None or previous.pricing_date != pricing_date else previous.version + 1
        entry = PriceEntry(pricing_date, version, cpu_1e2)
        self._latest[class_id] = entry
        self.publications += 1
        return entry

    def latest(self, class_id: str) -> Optional[PriceEntry]:
        return self._latest.get(class_id)


@dataclass
class Snapshot:
    units_1e4: int
    through_seq: int


class PositionStore:
    """Snapshot + deltas per (account, class). Group aggregates in units, maintained on every delta."""

    def __init__(self) -> None:
        self.snapshots: dict[tuple[str, str], Snapshot] = {}
        self.deltas: dict[tuple[str, str], list[tuple[int, int]]] = defaultdict(list)  # (seq, units_1e4)
        self.by_account: dict[str, set[str]] = defaultdict(set)
        self.group_units: dict[tuple[str, str], int] = defaultdict(int)  # (group, class) -> units, e.g. ("in_issue", class)
        self.group_classes: dict[str, set[str]] = defaultdict(set)  # group -> classes it holds
        self.account_group: dict[str, str] = {}  # account -> adviser or model group
        self.seq = 0

    def open_position(self, account: str, class_id: str, units_1e4: int, group: str) -> None:
        """Seed a snapshot, as the day close would. Aggregates follow. Seeding the same position twice accumulates."""
        key = (account, class_id)
        if key in self.snapshots:
            self.snapshots[key].units_1e4 += units_1e4
        else:
            self.snapshots[key] = Snapshot(units_1e4, self.seq)
        self.by_account[account].add(class_id)
        self.account_group[account] = group
        self.group_units[("in_issue", class_id)] += units_1e4
        self.group_units[(group, class_id)] += units_1e4
        self.group_classes[group].add(class_id)

    def post_delta(self, account: str, class_id: str, units_1e4: int) -> int:
        """A deal. One append and two aggregate updates. Never a read-modify-write of a stored value."""
        self.seq += 1
        self.deltas[(account, class_id)].append((self.seq, units_1e4))
        self.by_account[account].add(class_id)
        group = self.account_group.get(account, "none")
        self.group_units[("in_issue", class_id)] += units_1e4
        self.group_units[(group, class_id)] += units_1e4
        self.group_classes[group].add(class_id)
        return self.seq

    def units(self, account: str, class_id: str) -> int:
        snap = self.snapshots.get((account, class_id))
        total = snap.units_1e4 if snap else 0
        for _, delta in self.deltas.get((account, class_id), ()):
            total += delta
        return total

    def roll_snapshots(self) -> int:
        """Day close: fold deltas into snapshots. O(changed positions), not O(all positions)."""
        changed = 0
        for key, deltas in self.deltas.items():
            snap = self.snapshots.get(key) or Snapshot(0, 0)
            snap.units_1e4 += sum(d for _, d in deltas)
            snap.through_seq = self.seq
            self.snapshots[key] = snap
            changed += 1
        self.deltas.clear()
        return changed

    def reconcile(self) -> dict[str, tuple[int, int]]:
        """Register reconciliation for every class in one pass: Σ holder positions against the aggregate.

        O(holdings + deltas) once per day, and trivially parallel by class partition.
        """
        holders: dict[str, int] = defaultdict(int)
        for (_, cls), snap in self.snapshots.items():
            holders[cls] += snap.units_1e4
        for (_, cls), deltas in self.deltas.items():
            for _, d in deltas:
                holders[cls] += d
        return {cls: (holders[cls], self.group_units[("in_issue", cls)]) for cls in holders}


@dataclass(frozen=True)
class Line:
    class_id: str
    units_1e4: int
    cpu_1e2: Optional[int]
    price_date: Optional[date]
    value_cents: Optional[int]


@dataclass(frozen=True)
class Statement:
    account: str
    lines: tuple[Line, ...]
    total_cents: int
    oldest_price_date: Optional[date]


def value_account(store: PositionStore, prices: PriceIndex, account: str) -> Statement:
    """O(number of lines). No stored value is read or written."""
    lines = []
    total = 0
    oldest: Optional[date] = None
    for class_id in sorted(store.by_account.get(account, ())):
        units = store.units(account, class_id)
        entry = prices.latest(class_id)
        if entry is None:
            lines.append(Line(class_id, units, None, None, None))
            continue
        cents = value_cents(units, entry.cpu_1e2)
        total += cents
        oldest = entry.pricing_date if oldest is None or entry.pricing_date < oldest else oldest
        lines.append(Line(class_id, units, entry.cpu_1e2, entry.pricing_date, cents))
    return Statement(account, tuple(lines), total, oldest)


def group_value(store: PositionStore, prices: PriceIndex, group: str, class_ids: Optional[Iterable[str]] = None) -> int:
    """Fund size, adviser book, model AUM: O(classes in the group), never O(holdings)."""
    total = 0
    for class_id in (class_ids if class_ids is not None else store.group_classes.get(group, ())):
        entry = prices.latest(class_id)
        if entry is not None:
            total += value_cents(store.group_units[(group, class_id)], entry.cpu_1e2)
    return total
