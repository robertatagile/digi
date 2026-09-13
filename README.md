# Digi — LISP & Unit Trust Management Platform

Design repository for a new South African **LISP and unit trust (CIS) administration platform**.

**The idea in one line:** a small, hard **kernel** of financial building blocks with fixed controls, plus an **AI‑generated Tenant Pack** per manco or LISP. No configuration matrix.

**One kernel for both.** An account holds any number of instruments. A unit trust investor is the case N = 1. A LISP account is N = 30. Who issues the instrument is an attribute, not a system boundary.

## Start here

| Read | Why |
|------|-----|
| [docs/01-vision.md](docs/01-vision.md) | The problem with configuration-heavy platforms, and the thesis. |
| [docs/02-architecture.md](docs/02-architecture.md) | Kernel + packs. How blocks connect. |
| [docs/05-financial-controls.md](docs/05-financial-controls.md) | The control account between every block. |
| [docs/07-backdating-and-corrections.md](docs/07-backdating-and-corrections.md) | Who takes the loss when a price moves. |
| [docs/06-valuation.md](docs/06-valuation.md) | Calculate, don't store. Near real-time values. |
| [docs/09-tenant-packs-ai-generated.md](docs/09-tenant-packs-ai-generated.md) | How a manco's implementation is generated, proven and released. |
| [docs/13-legislation-as-a-controlled-layer.md](docs/13-legislation-as-a-controlled-layer.md) | Legislation (FSR Act, COFI, FAIS, CISCA, FICA …) as a controlled, manco-managed layer bound to controls. |

Full index: [docs/README.md](docs/README.md)

## Reference model

`reference/` holds a small **executable model of the kernel** (Python 3.11+, standard library only).
It exists to make the invariants concrete. It is not production code.

```bash
python3 -m unittest discover -s reference/tests -v
```

## Example pack

`docs/examples/example-manco-pack/` shows what a generated Tenant Pack looks like for a fictional manco.
