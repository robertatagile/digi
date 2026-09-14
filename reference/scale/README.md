# Scale model

The production data layout for calculate-don't-store, in miniature. Standard library only.

- `positions.py` — snapshots plus deltas per (account, class), group aggregates in units, a price index, fixed-point integers.
- `bench.py` — measures the shape of every hot path at a million holdings in one Python process on one core.

```bash
python3 reference/scale/bench.py --holdings 1000000 --classes 2000 --accounts 250000
```

The kernel reference model in `digi_kernel/` scans every posting on every query. That proves the invariants. This model shows how the same principle stays fast at volume. Doc 14 explains the layout and the rules.

Latest run in this repository's container:

| Step, one Python process, one core | Seconds | Note |
|-----------------------------------|--------:|------|
| Build 1 000 000 holdings and 2 000 prices | 10.0 | Seeding, done once |
| Post 50 000 deals as deltas | 0.63 | 13 µs per deal. One append, two aggregate updates |
| **Publish 2 000 new prices** | **0.003** | **1.5 µs per price. Nothing else is written** |
| Value 10 000 account statements | 0.16 | 16 µs per statement, four lines each |
| Fund size for all 2 000 classes from aggregated units | 0.003 | O(classes), never O(holdings) |
| Value 100 adviser books from aggregated units | 0.05 | O(classes each adviser holds) |
| Baseline: revalue and touch all holdings, as a store-the-value platform does per price | 0.53 | ≈ 3 hours a day of pure write work at 20 000 prices, avoided |
| Register reconciliation, all classes, one pass | 0.27 | 0 breaks. Once a day, parallel by class |
| Day close: roll deltas into snapshots | 0.13 | 49 999 positions changed, not a million |

Reproduce with `python3 reference/scale/bench.py`.
