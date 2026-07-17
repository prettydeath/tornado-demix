# Methodology

This document explains the demixing heuristics implemented in `tornado-demix` and how to
read their output honestly.

## 1. Deposits and vouchers

A **deposit** is an outgoing transaction from the subject wallet whose value equals a
Tornado.Cash denomination (0.1, 1, 10, 100 ETH, within 0.5%) and whose recipient is a
Tornado pool contract or one of the known router/proxy contracts.

Consecutive deposits of the same denomination that occur within `--gap-hours` are grouped
into a **voucher**. A voucher of size *N* means the depositor put *N* notes of that
denomination in during one session — e.g. `9 × 1 ETH`.

## 2. Withdrawal side (payouts)

Tornado withdrawals appear as **internal transactions sent from the pool contract**. Each
withdrawal pays the recipient `denomination − relayer fee`. We keep payouts whose value
falls in the band `[denomination × fee_lo, denomination × fee_hi]` (default `0.90 .. 0.995`).

We search the window `[first deposit, last deposit + window_days]` (default 30 days).
Block ranges are resolved from timestamps; Etherscan caps a response at 10,000 rows, so
ranges that hit the cap are split recursively to avoid missing data.

## 3. Candidate matching (single wallet)

Within the window we count how many qualifying payouts each recipient received. A
recipient hit **exactly N times** (where *N* is a voucher size) is a **candidate
consolidation address**: the depositor probably withdrew all *N* notes to it.

- A **unique** N-count recipient is a strong single-wallet lead.
- Busier pools yield several N-count recipients; these are candidates, not conclusions.

## 4. Cross-wallet correlation (multi)

Given several wallets we compute:

| Result | Definition | Strength |
|--------|-----------|----------|
| **Profile match (exact, multi-denom)** | one address received a wallet's *entire* fingerprint, e.g. `6×0.1 + 4×1.0` | 🔴 strong |
| **Cross consolidator** | one address is a full-fingerprint match for 2+ wallets | 🔴 strong |
| **Synchronous deposits** | wallets deposited within minutes of each other | 🟠 behavioural link |
| **Strong link (single denom)** | a count-matched candidate shared by 2+ wallets | 🟡 lead |
| **Soft overlap** | any qualifying recipient shared by 2+ wallets | ⚪ often artefact |

### The window-overlap caveat

If two wallets have the **same voucher size** and **overlapping windows** (because they
deposited at nearly the same time), their count-matched candidate sets are computed from
the *same* pool payouts and are therefore **almost identical by construction**. In that
situation, intersections do **not** distinguish "linked" from "unlinked" — they are an
artefact of the shared window.

What remains discriminating:

- **Multi-denomination profile matches**, because a single address receiving a specific
  combination like `8×0.1 + 4×1.0 + 1×10` is unlikely by chance.
- **Deposit-time synchronicity**, which is a behavioural signal independent of the exit
  analysis.

The tool surfaces this caveat directly in the multi-wallet report.

## 5. Cluster tracing (split exits)

When a wallet does not consolidate to a single address, its notes are spread across many
recipients. For each denomination we take the count-matched candidates, follow their
funds **one hop forward** (within `FORWARD_DAYS`, ignoring dust and pool/router
addresses), and look for a **shared downstream address `Z` fed by two or more
denomination layers**. Such a `Z` is where the split exits reconverge.

Noisy layers (candidate count above `--layer-cap`, or single-note layers) are skipped,
because tracing hundreds of false candidates dilutes the signal. Absence of a 1-hop
reconvergence is itself informative: it suggests dispersed exits (good operational
security) or reconvergence deeper than one hop.

## 6. Reading the output responsibly

- Treat every candidate as a **lead**, corroborated by other evidence (KYC records,
  off-chain data, subsequent hops, exchange attribution).
- Prefer exact multi-denomination profile matches over single-count candidates.
- Do not present soft overlaps from synchronous-deposit wallets as evidence of a link.
