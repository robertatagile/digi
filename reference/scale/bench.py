"""Measure the shape of the hot paths at volume. Standard library only.

    python3 reference/scale/bench.py [--holdings 1000000] [--classes 2000] [--accounts 250000]

The numbers are for one Python process on one core. Production uses fixed-point integers in a real
store and many partitions; the point here is the complexity of each path, not the absolute speed.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scale.positions import PositionStore, PriceIndex, group_value, value_account, value_cents  # noqa: E402


def timed(label, fn):
    start = time.perf_counter()
    result = fn()
    elapsed = time.perf_counter() - start
    return label, elapsed, result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--holdings", type=int, default=1_000_000)
    parser.add_argument("--classes", type=int, default=2_000)
    parser.add_argument("--accounts", type=int, default=250_000)
    parser.add_argument("--statements", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    rng = random.Random(args.seed)

    classes = [f"C{i:05d}" for i in range(args.classes)]
    accounts = [f"A{i:07d}" for i in range(args.accounts)]
    advisers = [f"ADV{i:04d}" for i in range(max(1, args.accounts // 200))]
    today = date(2026, 9, 14)

    store = PositionStore()
    prices = PriceIndex()
    rows = []

    def build():
        for i in range(args.holdings):
            account = accounts[i % args.accounts]
            # skew: a few large funds hold most accounts, like a real book
            class_id = classes[int(abs(rng.gauss(0, args.classes / 6))) % args.classes]
            units = rng.randint(1_0000, 50_000_0000)  # 1 to 50 000 units, in 1/10 000
            store.open_position(account, class_id, units, advisers[i % len(advisers)])
        for class_id in classes:
            prices.publish(class_id, today - timedelta(days=1), rng.randint(100_00, 5_000_00))
        return len(store.snapshots)

    rows.append(timed(f"build {args.holdings:,} holdings, {args.classes:,} prices", build))
    holdings = len(store.snapshots)

    def deals():
        n = 50_000
        for _ in range(n):
            account = accounts[rng.randrange(args.accounts)]
            class_id = classes[rng.randrange(args.classes)]
            store.post_delta(account, class_id, rng.randint(-1_000_0000, 5_000_0000))
        return n
    rows.append(timed("post 50,000 deals as deltas", deals))

    def publish_all():
        for class_id in classes:
            prices.publish(class_id, today, rng.randint(100_00, 5_000_00))
        return args.classes
    rows.append(timed(f"publish {args.classes:,} new prices (writes nothing else)", publish_all))

    sample = [accounts[rng.randrange(args.accounts)] for _ in range(args.statements)]

    def statements():
        total = 0
        for account in sample:
            total += value_account(store, prices, account).total_cents
        return total
    rows.append(timed(f"value {args.statements:,} account statements", statements))

    def fund_sizes():
        return sum(group_value(store, prices, "in_issue", [c]) for c in classes)
    rows.append(timed(f"fund size for all {args.classes:,} classes from aggregated units", fund_sizes))

    def adviser_books():
        return sum(group_value(store, prices, adv) for adv in advisers[:100])
    rows.append(timed("value 100 adviser books from aggregated units", adviser_books))

    def naive_revalue():
        # what a store-the-value platform does on every price: touch every holding
        total = 0
        for (account, class_id), snap in store.snapshots.items():
            total += value_cents(snap.units_1e4, prices.latest(class_id).cpu_1e2)
        return total
    rows.append(timed(f"baseline: revalue and touch all {holdings:,} holdings", naive_revalue))

    def reconcile():
        return sum(1 for holders, control in store.reconcile().values() if holders != control)
    rows.append(timed(f"register reconciliation, all {args.classes:,} classes, one pass", reconcile))

    rows.append(timed("day close: roll deltas into snapshots", store.roll_snapshots))

    print(f"\nholdings={holdings:,} classes={args.classes:,} accounts={args.accounts:,} statements={args.statements:,}\n")
    print(f"{'step':<64} {'seconds':>9}   note")
    for label, seconds, result in rows:
        note = ""
        if label.startswith("value") and "statements" in label:
            note = f"{seconds / args.statements * 1e6:,.0f} µs per statement"
        elif label.startswith("publish"):
            note = f"{seconds / args.classes * 1e6:,.1f} µs per price"
        elif label.startswith("post"):
            note = f"{seconds / 50_000 * 1e6:,.1f} µs per deal"
        elif label.startswith("register"):
            note = f"{result} breaks"
        elif label.startswith("day close"):
            note = f"{result:,} positions changed"
        elif label.startswith("baseline"):
            note = "the cost calculate-don't-store avoids on every price"
        print(f"{label:<64} {seconds:>9.3f}   {note}")


if __name__ == "__main__":
    main()
