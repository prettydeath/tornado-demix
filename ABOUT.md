# About

**tornado-demix** is a forensic research toolkit that de-anonymizes Tornado.Cash
(ETH) activity using only **public** on-chain data from the Etherscan API.

## What it does

Given an Ethereum wallet, it finds the wallet's deposits into the Tornado.Cash ETH
pools (0.1 / 1 / 10 / 100 ETH), then applies an **amount + timing correlation**
heuristic to surface the likely withdrawal (exit) addresses. It can also correlate
several wallets against each other and trace split exits to a common downstream
address. Results are written as plain CSV files.

## Why it exists

Tornado.Cash provides privacy through fixed-denomination pooling, but that privacy
degrades when a depositor behaves predictably — withdrawing the same number of notes,
in the same denominations, within a short window. This project turns those public,
observable patterns into investigative leads for compliance, AML, incident-response,
and academic analysis.

## What it is not

- It does **not** break cryptography, exploit any vulnerability, or access private data.
- Its output is **probabilistic and circumstantial** — leads, not proof. Candidates
  must be corroborated with independent evidence before any conclusion is drawn.

## At a glance

| | |
|---|---|
| **Language** | Python 3.9+ |
| **Dependency** | `requests` (CSV output uses the standard library) |
| **Data source** | Etherscan V2 API (key supplied via `config/api.csv`) |
| **Networks** | Ethereum mainnet, Tornado.Cash ETH pools only |
| **Output** | CSV files |
| **Commands** | `demix` (one wallet), `multi` (correlate wallets), `cluster` (trace split exits) |
| **License** | MIT |

## Learn more

- [`README.md`](README.md) — install, configure, usage.
- [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) — full method and signal-strength table.
- [`examples/`](examples/) — ready-made sample outputs with a walkthrough.

## Disclaimer

For lawful compliance, investigative, and academic use only. You are responsible for
using this software in accordance with all applicable laws and the terms of service of
any data provider (including Etherscan).
