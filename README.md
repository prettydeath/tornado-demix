# tornado-demix

**Tornado.Cash (ETH) demixing toolkit — amount + timing correlation over public on-chain data.**

![python](https://img.shields.io/badge/python-3.9%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)
![data](https://img.shields.io/badge/data-Etherscan%20V2-informational)
![status](https://img.shields.io/badge/status-research-orange)

`tornado-demix` takes an Ethereum wallet, finds its deposits into the Tornado.Cash
ETH pools, and applies a **probabilistic de-anonymization heuristic** to surface the
likely withdrawal (exit) addresses. It works entirely from **public** blockchain data
via the Etherscan API — it does not break any cryptography and produces *leads*, not proof.

> ⚠️ **Disclaimer.** This is a forensic research tool for compliance, investigation,
> and academic use. Its output is **probabilistic and circumstantial**. Never treat a
> candidate address as confirmed without independent corroboration. See
> [Limitations](#limitations).

---

## About

`tornado-demix` turns the **public, observable behaviour** of Tornado.Cash users into
investigative leads. Fixed-denomination mixing loses its privacy guarantee when a
depositor is predictable — withdrawing the same number of notes, in the same
denominations, within a short window. The tool detects those patterns from Etherscan
data and reports likely exit addresses as CSV. It breaks no cryptography and reveals
nothing that is not already on-chain. Full background: [`ABOUT.md`](ABOUT.md).

---

## Table of contents

- [About](#about)
- [How it works](#how-it-works)
- [Install](#install)
- [Configure (API key via CSV)](#configure-api-key-via-csv)
- [Usage](#usage)
  - [Single wallet — `demix`](#single-wallet--demix)
  - [Several wallets — `multi`](#several-wallets--multi)
  - [Split-exit clusters — `cluster`](#split-exit-clusters--cluster)
- [Output](#output)
- [Project layout](#project-layout)
- [Methodology](#methodology)
- [Limitations](#limitations)
- [Legal & ethics](#legal--ethics)
- [License](#license)

---

## How it works

Tornado.Cash mixes funds by accepting fixed-denomination deposits (0.1 / 1 / 10 / 100 ETH)
and later paying them out to fresh addresses. The privacy guarantee weakens when a user
behaves predictably. This tool exploits two public signals:

1. **Denomination + timing.** A depositor who sends *N* notes of a denomination in one
   sitting (a *voucher*) usually withdraws the same *N* notes to one or a few addresses
   within a bounded time window.
2. **Fee fingerprint.** A withdrawal pays out `denomination − relayer fee`, e.g. a 1 ETH
   note arrives as ~0.90–0.995 ETH. Filtering pool payouts to that band isolates real
   withdrawals.

```
Deposit:  N notes of denomination D at time T  (a "voucher")
                     │
                     ▼
Withdrawals (internal txs FROM the pool) in [T, T + window],
where a recipient received ≈ D − relayer fee
                     │
                     ▼
Count unique recipients → those hit exactly N times are
candidate consolidation addresses for the depositor.
```

For multiple wallets, the tool adds **denomination-profile matching** (one address that
received a wallet's *entire* multi-denomination fingerprint) and **cluster tracing**
(following split exits one hop forward to a shared downstream address).

Full write-up: [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

---

## Install

```bash
git clone https://github.com/prettydeath/tornado-demix.git
cd tornado-demix
python -m pip install -r requirements.txt      # or: pip install -e .
```

Requires Python 3.9+ and `requests` (standard-library `csv` handles output — no
heavy dependencies).

---

## Configure (API key via CSV)

The Etherscan API key is read from a **CSV file** — no secrets on the command line.

```bash
cp config/api.csv.example config/api.csv
```

Edit `config/api.csv`:

```csv
service,api_key
etherscan,YOUR_ETHERSCAN_KEY
```

Get a free key at <https://etherscan.io/myapikey>. `config/api.csv` is git-ignored.
As a fallback the tool also reads the `ETHERSCAN_API_KEY` environment variable.

Wallets can likewise be listed in a CSV (`config/wallets.csv`):

```csv
address,label
0x019b5bb2051797e33f726d0e7a8cb9b9c2003ac2,suspect-1
0x450cc23c0bc13d46288deb36913fdaaee49fcd99,suspect-2
```

---

## Usage

All commands: `python -m tornado_demix <command> ...` (or `tornado-demix <command>` if installed).

### Single wallet — `demix`

```bash
python -m tornado_demix demix 0x019b5bb2051797e33f726d0e7a8cb9b9c2003ac2 \
    --out-dir out/demix
```

Detects vouchers and lists recipients hit exactly *N* times per denomination.

### Several wallets — `multi`

```bash
python -m tornado_demix multi --wallets-csv config/wallets.csv --out-dir out/multi
# or inline:
python -m tornado_demix multi 0xAAA... 0xBBB... 0xCCC... --out-dir out/multi
```

Computes strong links, soft overlaps, **profile matches**, and cross-wallet consolidators.

### Split-exit clusters — `cluster`

```bash
python -m tornado_demix cluster --wallets-csv config/wallets.csv \
    --out-dir out/cluster --layer-cap 12
```

Traces per-denomination candidates one hop forward to find a shared downstream address.
Forward lookups and demix layers are cached under `--cache-dir` (default `.cache/`), so an
interrupted run can simply be **re-run to resume**.

### Common options

| Flag | Default | Meaning |
|------|---------|---------|
| `--api-csv` | `config/api.csv` | CSV holding the Etherscan key |
| `--out-dir` | — | directory to write CSV report files |
| `--window-days` | `30` | withdrawal search window after a deposit |
| `--fee-lo` / `--fee-hi` | `0.90` / `0.995` | payout band as a fraction of the denomination |
| `--gap-hours` | `24` | max gap to group deposits into one voucher |
| `--layer-cap` (cluster) | `35` | skip a denomination layer with more candidates than this |

---

## Output

Each command prints a console summary and, with `--out-dir`, writes plain **CSV**
files (openable in any spreadsheet, `grep`, or pandas). Timestamps are ISO-8601 UTC.

**`demix`**

| File | Contents |
|------|----------|
| `vouchers.csv` | detected vouchers: denomination, count, first/last deposit |
| `deposits.csv` | every deposit: denomination, time, block, target, tx hash |
| `candidates.csv` | count-matched candidate exit addresses (the key result) |
| `withdrawals_<D>ETH.csv` | every qualifying recipient per denomination, `is_candidate` flag |

**`multi`**

| File | Contents |
|------|----------|
| `wallets_overview.csv` | per-wallet vouchers & candidate counts |
| `strong_links.csv` | count-matched candidate shared by 2+ wallets |
| `soft_overlaps.csv` | any qualifying recipient shared by 2+ wallets (weak) |
| `profile_matches.csv` | address that received a wallet's full fingerprint (strong) |
| `cross_consolidators.csv` | one address matching 2+ wallets' fingerprints |

**`cluster`**

| File | Contents |
|------|----------|
| `clusters.csv` | reconvergence points `Z` fed by 2+ denomination layers |
| `cluster_detail.csv` | every contributing forward tx (source, value, time, hash) |

Ready-made sample outputs live in [`examples/`](examples/).

---

## Project layout

```
tornado-demix/
├── tornado_demix/          # Python package
│   ├── constants.py        # pool/router addresses, API endpoint
│   ├── config.py           # CSV loaders (API key, wallets)
│   ├── etherscan.py        # Etherscan V2 client (pagination, retries)
│   ├── demix.py            # single-wallet core
│   ├── multi.py            # cross-wallet correlation & profile matching
│   ├── cluster.py          # split-exit forward tracer (resumable cache)
│   ├── report.py           # CSV report writers
│   └── cli.py              # argparse CLI (demix / multi / cluster)
├── config/                 # *.example CSVs (real files are git-ignored)
├── examples/               # ready-made sample CSV outputs + walkthrough
├── docs/METHODOLOGY.md     # detailed method & signal-strength table
├── ABOUT.md                # project background
├── requirements.txt
├── pyproject.toml
└── LICENSE
```

## Limitations

- **Probabilistic, not proof.** Candidates are leads that require corroboration.
- **Window-overlap artefact.** When several wallets deposit at similar times with equal
  voucher sizes, their search windows overlap and raw intersections inflate. The tool
  flags this; rely on multi-denomination profile matches and deposit-time synchronicity.
- **Single-note vouchers** (N = 1) and low counts (N = 2) are weakly discriminating.
- **1-hop cluster tracing** may miss reconvergence that happens two or more hops later.
- **ETH pools only** (0.1 / 1 / 10 / 100 ETH); ERC-20 pools are out of scope.
- **Rate limits.** A free Etherscan key (~5 req/s) is sufficient but slower for busy pools.

---

## Legal & ethics

This project is intended for lawful compliance, investigative, and academic purposes on
**public** blockchain data. You are responsible for using it in accordance with all
applicable laws and terms of service (including Etherscan's). It performs no hacking,
exploits no vulnerability, and reveals nothing that is not already public on-chain.

---

## License

[MIT](LICENSE)
