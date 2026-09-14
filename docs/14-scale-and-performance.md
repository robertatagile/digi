# 14. Scale and performance

## The claim

> **Calculate, don't store is faster at volume, not slower. But only with the right data layout.**

Incumbent platforms revalue and store every holding when a price arrives. That is one write per holding per price. Here a price is **one write**. Values are multiplications at read time. The cost moves from the write path, where it multiplies by holdings, to the read path, where it multiplies by the lines a person is looking at.

This document sets the targets, names the hot paths with their cost, and lists the rules that keep them fast.

## Design targets

The South African market today, in orders of magnitude, and the targets the platform is built for. Targets carry headroom of roughly five times.

| Dimension | Market today | Design target |
|-----------|--------------|---------------|
| Accounts | About a million at a large tenant. Around ten million industry-wide | 25 million |
| Holdings (account × instrument) | Tens of millions industry-wide | 50 million |
| Instruments (classes, including external per tenant) | Several thousand | 20 000 |
| Instructions per day, sustained | Tens of thousands at a large tenant | 500 000 platform-wide |
| Instructions per day, peak (month-end collections) | Hundreds of thousands at a large tenant | 3 million platform-wide |
| Peak arrival rate before cut-off | Hundreds per second | 2 000 per second |
| Prices per day | Several thousand | 20 000, mostly in a two-hour window |
| Valuation reads | | 5 000 statements per second, p99 under 100 ms |
| Price published to visible in every value | | Under one second |
| Day close per tenant | | Under 30 minutes after the last price |
| Fee run over 10 million holdings | | Under one hour |
| Distribution over a class with a million holders | | Under 10 minutes |
| History online, bitemporal | | 10 years |

## Hot paths and their cost

| Operation | Cost | Why |
|-----------|------|-----|
| Receive an instruction | O(1) | One append. Receive time stamped at the edge, before any queue |
| Match cash | O(1) | One append and one index update |
| Price a class for a dealing day | O(deals in that class and day), parallel by class | One pass over the unpriced index |
| **Publish a price** | **O(1) write** | Nothing is revalued. Caches are keyed by price version and simply miss |
| Value one account | O(lines) | Snapshot plus deltas per line, one price lookup per line, one multiplication |
| Fund size, adviser book, model AUM, tenant AUM | O(classes in the group) | Aggregated **units** per group × price. Never a sum over holdings |
| Expected net flow for a class before the pricing point | O(1) | Unpriced money and units aggregated per class and day as instructions arrive |
| Register reconciliation | O(holdings) once a day, parallel by class | One pass over snapshots and deltas against the aggregate |
| Distribution allocation | O(holders of the class), parallel shards | One pass with deterministic rounding |
| Fee run | O(holdings), parallel shards | Accruals from daily snapshots and the price series |
| As-at query on both time axes | O(deltas since the nearest snapshot) | Daily snapshots. An arbitrary knowledge time replays a few deltas |

The per-deal register check is the journal balancing (I1) and the account-kind check. The full sum is the daily reconciliation. Both hold; only the schedule differs.

## The rules

1. **Store quantities. Aggregate quantities incrementally. Compute values on read.** A deal updates one position and a handful of group aggregates in units. A price updates one index entry.
2. **Push prices, not values.** Screens and APIs subscribe to price versions per class. A client with the positions in view recomputes its lines. Fan-out is per class, never per holding.
3. **Never read-modify-write a balance.** Postings append. Control account balances are sums of daily materialised totals plus today's postings. Hot control accounts never contend.
4. **Partition by tenant, then by account for commands and by class for pricing and bulk runs.** The two keys match the two kinds of load.
5. **Serialisation points are explicit and few.** An account stream, a class pricing run, an exposure tranche. Everything else is append and aggregate.
6. **Snapshots are caches with a sequence number.** A verifier replays a sample continuously. A snapshot that disagrees with replay is a break.
7. **Bulk runs are idempotent per (run, holding) and checkpointed.** Their control totals reconcile per shard, then across shards.
8. **Bursts are queued, never refused. The dealing date never moves.** Cut-off is decided by the receive time stamped at the edge, so a backlog cannot push an instruction to the next day.
9. **Fixed-point integers in storage.** Units in ten-thousandths, prices in hundredths of a cent, money in cents. Exact and compact.

## Data layout

| Store | Key | Notes |
|-------|-----|-------|
| `events` | tenant, stream, sequence | Append-only system of record. Command id for idempotency. Optimistic concurrency per stream |
| `postings` | journal, account, dimension | Derived from events. Columnar friendly. Effective date and posted-at on every row |
| `position_snapshots` | tenant, account, class, as-of date | Units and the sequence they reflect. Written at day close only for positions that changed. Monthly full snapshot |
| `position_deltas` | tenant, account, class, sequence | Today's unit postings. Folded into snapshots at close |
| `group_units` | tenant, group, class | Units in issue, nominee bulk, adviser book, model, product. Updated on every unit posting |
| `unpriced_totals` | tenant, class, dealing date | Money and units awaiting pricing. Feeds the cash forecast |
| `price_index` | tenant, class | Latest official and indicative, with date and version. History in the price series |
| `control_daily` | tenant, account, date | Debit and credit totals per day. Balance as at a date is a prefix sum |
| `instruction_status` | tenant, status, dealing date | The unpriced, unmatched and held queues |
| `closed_days` | tenant | Small. Held in memory |
| Warehouse | columnar copy of events and postings | Analytics, regulatory extracts, heavy as-at reports |

Storage is not the constraint. Three hundred million postings a year at a few hundred bytes each is under a hundred gigabytes.

## Consistency model

| Scope | Guarantee | How |
|-------|-----------|-----|
| One account stream | Linearizable. Read your own writes | Optimistic concurrency with expected version. Responses carry the sequence |
| One class pricing run | All deals of the class and day priced in one run | The run is the serialisation point. Parallel across classes |
| Exposure limits, ring-fencing thresholds | Exact | Per-fund serialisation with **tranche reservation**: workers reserve headroom in tranches and return what they do not use |
| Group aggregates, statements, dashboards | Eventually consistent within seconds, with a sequence marker | Every response says what sequence and which price versions it reflects |
| Control account balances | Exact as at any posted-at time | Prefix sums over daily totals plus today's postings |

## Peaks, worked

**Month-end collections.** One tenant collects a million debit orders in one file. Each becomes an instruction and an exposure funding, then a deal at the pricing point. Two thousand journals a second on one partition prices the whole book in about eight minutes. Twenty class partitions bring it under a minute. Exposure headroom is reserved in tranches so the fund's limit stays exact without a single lock.

**Pricing window.** Twenty thousand prices arrive between five and seven in the evening. Each is one index write. No holding is touched. A portal showing a client's twelve funds recomputes twelve multiplications on the next read.

**Distribution on a large class.** A million holders. Entitlements are one pass over the class partition in shards of fifty thousand, each shard idempotent and checkpointed, each shard emitting its own control totals. Ten shards in parallel finish inside the ten-minute target with room to spare.

**Quarterly statements.** Ten million accounts. A statement is a read, not a computation over history: positions from the day-close snapshot, prices from the index, rendered and stored with its knowledge time and price versions. Rendering, not valuation, is the cost.

**Price correction on a large class.** Version two of a price. Affected deals are found by the deal index on (class, date, version), not by scanning. Corrections post as ordinary journals, in shards.

## Real-time valuation at volume

- **Official prices** arrive once a day per class. The value of everything moves once a day. The read path does the work.
- **Indicative prices** for portfolio managers arrive intraday from instrument prices. Indicative NAV per fund is O(instruments in the fund). Investor-facing indicative values, where a pack allows them, are again multiplications on read.
- **Subscriptions** carry price version changes per class. A screen with positions in memory updates itself. The platform never pushes a value to a holding.
- **Cash forecast** for the dealing day is a read of `unpriced_totals`. It sharpens as instructions arrive, with no batch.

## Failure modes at scale and their answers

| Failure mode | Answer |
|--------------|--------|
| Hot control account under contention | Append only. Balances are prefix sums |
| One fund's exposure limit serialising a million collections | Tranche reservation |
| Price fan-out storm | None by design. Caches are keyed by version |
| Snapshot lag | Bounded and visible. Every read carries its sequence |
| Duplicate delivery from a bank or FinSwitch | Idempotency by command id and content hash |
| Bulk run fails halfway | Checkpointed and idempotent per holding. Resume, never restart |
| Queue backlog before cut-off | Receive time is stamped at the edge. Dealing date is unaffected |
| Clock skew across nodes | Sequence is the authority. Timestamps come from one time source per partition |
| A flood of backdating after an outage | Batch approval with one reason code, one record per deal |
| A pack guard that is slow | Guards run in a sandbox with a CPU budget and read only projections passed in |

## Technology stance

- **System of record:** a relational store with append-only, partitioned tables per tenant and month, and an outbox for events. Transactions and exactly-once are cheap there.
- **Fan-out:** a log for projections, integrations and subscriptions.
- **Hot indexes in memory:** price index, closed days, KYC and licence flags, unpriced totals. Versioned refresh from the log.
- **Positions:** snapshot and delta tables with covering indexes, warmed into a key-value cache for the read path.
- **Compute:** stateless kernel services. Commands routed by account. Pricing and bulk runs routed by class. Horizontal scale on both.
- **Pack runtime:** pooled sandbox instances per tenant with a CPU budget per guard.
- **Warehouse:** a columnar copy fed by the log for analytics and heavy as-at reports.
- **Region:** South Africa. The repository already deploys to Azure; South Africa North is the natural region.

## Capacity and load-test plan

| Test | Scenario | Assertion |
|------|----------|-----------|
| Month-end | One tenant, one million collections, one pricing point | Priced under one minute on twenty partitions. Exposure limit exact |
| Pricing window | 20 000 prices in two hours | Each visible in valuations under one second. Zero holding writes |
| Statements under load | 5 000 statements per second for 30 minutes during the pricing window | p99 under 100 ms |
| Distribution | A class with one million holders | Allocated under 10 minutes. Declared total equals entitlements plus rounding |
| Fee run | 10 million holdings | Under one hour. Claims equal cancellations equal payments |
| Day close | A tenant with 10 million holdings | Under 30 minutes after the last price |
| Price correction | A class with a million deals on the corrected date | Corrections posted in shards. Register reconciles |
| Replay | Rebuild every projection from events | Equal to the live projections |

Runs nightly at ten percent of target scale in CI. Monthly at full scale. Results published with the release.

## The scale model in the repository

`reference/scale/` holds the production data layout in miniature: snapshots plus deltas, group aggregates in units, a price index, fixed-point integers. `bench.py` measures the shape of each hot path in one Python process on one core. The numbers below come from this repository's container. Production is many partitions in a compiled service; the ratios are what matter.

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

The baseline row is the cost a store-the-value platform pays on every price. Here it is paid once a day at reconciliation, in one pass, in parallel.
