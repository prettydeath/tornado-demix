# Examples

Ready-made CSV outputs produced by the tool against real Ethereum mainnet data
(via Etherscan). Reproduce any of them with your own API key configured in
`config/api.csv`.

All three subjects deposited on **2025-11-23**; the withdrawal search window is
the default 30 days, and the fee band is `0.90 .. 0.995` of the denomination.

---

## 1. `demix_0x019b/` — single wallet

```bash
python -m tornado_demix demix 0x019b5bb2051797e33f726d0e7a8cb9b9c2003ac2 \
    --out-dir examples/demix_0x019b
```

The wallet made **two vouchers**: `9 × 0.1 ETH` and `9 × 1.0 ETH`
(see `vouchers.csv`, `deposits.csv`).

`candidates.csv` — recipients hit **exactly 9 times** inside the window:

| denom | match_count | candidate_address | total_eth_received |
|------:|------------:|-------------------|-------------------:|
| 0.1 | 9 | `0xbe5bf8862d5bc3fa516fffc3e01c6d5548a616d3` | 0.8819 |
| 1.0 | 9 | `0x09bc3d16…`, `0xb394573f…`, `0xefb7fed9…`, `0xb574747f…`, `0x13744619…`, `0x1259d53e…` | ~8.95 each |

The `0.1 ETH` pool yields a **single clean candidate** — a strong lead. The busier
`1.0 ETH` pool yields six count-9 recipients (candidates, not conclusions).
`withdrawals_0_1ETH.csv` / `withdrawals_1_0ETH.csv` list every qualifying recipient
with an `is_candidate` flag.

---

## 2. `multi_example/` — two wallets correlated

```bash
python -m tornado_demix multi \
    0xf666057b3200c2af14534217ded1b8275dca53eb \
    0xb421a98ca7825ad2951eaf6516bea4a9f08ffbfd \
    --out-dir examples/multi_example
```

The standout result is in `profile_matches.csv`: one address received wallet
`0xf666…`'s **entire fingerprint** exactly —

| wallet | fingerprint | consolidator_address | match_type | received_vs_needed |
|--------|-------------|----------------------|-----------|--------------------|
| `0xf666057b…` | 6×0.1 + 4×1.0 | `0xf4c9bcff0a21613596b38ad0ee8cf5198835bb96` | **exact** | 0.1ETH:6/6; 1.0ETH:4/4 |

`strong_links.csv` lists 22 count-matched `1.0 ETH` addresses shared by both wallets.
⚠️ **Read these with care:** both wallets deposited `4 × 1.0 ETH` within minutes of
each other, so their windows overlap and the shared count-4 set is largely a
*window artefact* — not proof of a link. The exact multi-denomination profile match
above is the trustworthy signal. This is exactly the caveat described in
[`../docs/METHODOLOGY.md`](../docs/METHODOLOGY.md).

---

## 3. `cluster_example/` — split-exit tracing

```bash
python -m tornado_demix cluster 0x450cc23c0bc13d46288deb36913fdaaee49fcd99 \
    --out-dir examples/cluster_example --layer-cap 12
```

`0x450c…` deposited `5 × 1.0 ETH + 1 × 10.0 ETH` but has **no single consolidator**.
The tracer follows its per-denomination candidates one hop forward looking for a
shared downstream address. Result (`clusters.csv`): **no 1-hop reconvergence** — the
exits were dispersed across independent addresses (good operational security, or
reconvergence deeper than one hop). A negative result is still an informative finding.

---

## Reading order

1. `vouchers.csv` / `deposits.csv` — what went in.
2. `candidates.csv` (demix) or `profile_matches.csv` (multi) — the leads.
3. `withdrawals_*.csv` / `*_detail.csv` — the full evidence tables for verification
   on <https://etherscan.io>.
