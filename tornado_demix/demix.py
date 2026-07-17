"""Single-wallet Tornado.Cash demixing (amount + timing correlation).

Pipeline:
  1. detect_deposits  - find the wallet's deposits into Tornado ETH pools.
  2. cluster_vouchers - group deposits into "vouchers" (denomination + time).
  3. analyze_denom    - export pool withdrawals in-window and count recipients.
  4. run_demix        - orchestrate the above and attach candidate matches.

This is a probabilistic forensic heuristic over PUBLIC data, not proof.
"""

import sys
from collections import Counter, defaultdict
from datetime import datetime

from .constants import DENOMINATIONS, POOL_BY_ADDR, POOLS, ROUTERS, WEI


def _log(msg):
    print(msg, file=sys.stderr, flush=True)


def detect_deposits(client, wallet):
    """Return the wallet's Tornado deposits as a list of dicts.

    A deposit is an outgoing, successful transaction whose value matches a
    known denomination (within 0.5%) and whose recipient is a Tornado pool or
    router. Each dict has: denom, ts, block, hash, to, via.
    """
    wallet = wallet.lower()
    deposits = []
    for tx in client.outgoing_txs(wallet):
        if tx.get("isError") == "1":
            continue
        to = (tx.get("to") or "").lower()
        value = int(tx.get("value", "0")) / WEI

        denom = None
        for candidate in DENOMINATIONS:
            if value > 0 and abs(value - candidate) <= candidate * 0.005:
                denom = candidate
                break
        if denom is None:
            continue

        is_pool = to in POOL_BY_ADDR
        is_router = to in ROUTERS
        # If sent directly to a pool, the pool must match the denomination.
        if is_pool and POOL_BY_ADDR[to] != denom:
            continue
        if not (is_pool or is_router):
            continue

        deposits.append({
            "denom": denom,
            "ts": int(tx["timeStamp"]),
            "block": int(tx["blockNumber"]),
            "hash": tx["hash"],
            "to": to,
            "via": "pool" if is_pool else "router",
        })
    deposits.sort(key=lambda d: d["ts"])
    return deposits


def cluster_vouchers(deposits, gap_hours=24):
    """Group deposits of the same denomination that are close in time.

    Deposits of one denomination separated by more than ``gap_hours`` start a
    new voucher. Returns a list of voucher dicts sorted by (denom, first_ts).
    """
    by_denom = defaultdict(list)
    for deposit in deposits:
        by_denom[deposit["denom"]].append(deposit)

    vouchers = []
    for denom, items in by_denom.items():
        items.sort(key=lambda d: d["ts"])
        cluster = [items[0]]
        for deposit in items[1:]:
            if deposit["ts"] - cluster[-1]["ts"] <= gap_hours * 3600:
                cluster.append(deposit)
            else:
                vouchers.append(_make_voucher(denom, cluster))
                cluster = [deposit]
        vouchers.append(_make_voucher(denom, cluster))

    vouchers.sort(key=lambda v: (v["denom"], v["first_ts"]))
    return vouchers


def _make_voucher(denom, cluster):
    return {
        "denom": denom,
        "count": len(cluster),
        "first_ts": cluster[0]["ts"],
        "last_ts": cluster[-1]["ts"],
        "first_block": cluster[0]["block"],
        "deposits": cluster,
    }


def analyze_denom(client, denom, vouchers_for_denom, window_days, fee_lo, fee_hi):
    """Export in-window withdrawals for one denomination and count recipients.

    The withdrawal search window spans from the earliest voucher deposit to
    ``window_days`` after the latest voucher deposit of this denomination.
    A withdrawal qualifies if the recipient received ``denom * fee_lo`` ..
    ``denom * fee_hi`` ETH (i.e. the denomination minus the relayer fee).
    """
    pool = POOLS[denom]
    low_value = denom * fee_lo
    high_value = denom * fee_hi

    first_ts = min(v["first_ts"] for v in vouchers_for_denom)
    last_ts = max(v["last_ts"] for v in vouchers_for_denom)
    end_ts = last_ts + window_days * 86400

    start_block = client.block_by_time(first_ts, "before") or 0
    end_block = client.block_by_time(end_ts, "after") or 99999999
    _log(
        f"  [{denom} ETH] pool {pool} | blocks {start_block}..{end_block} "
        f"({datetime.utcfromtimestamp(first_ts):%Y-%m-%d} .. "
        f"{datetime.utcfromtimestamp(end_ts):%Y-%m-%d})"
    )

    internal = client.internal_from(pool, start_block, end_block)
    _log(f"  [{denom} ETH] internal txs from pool in window: {len(internal)}")

    recipients = []  # (address, value_eth, ts, hash)
    for item in internal:
        if (item.get("from") or "").lower() != pool:
            continue
        if item.get("isError") == "1":
            continue
        value = int(item.get("value", "0")) / WEI
        if low_value <= value <= high_value:
            recipients.append((
                (item.get("to") or "").lower(),
                value,
                int(item["timeStamp"]),
                item["hash"],
            ))

    counts = Counter(address for address, *_ in recipients)
    detail = defaultdict(list)
    for address, value, ts, tx_hash in recipients:
        detail[address].append({"value": value, "ts": ts, "hash": tx_hash})

    return {
        "denom": denom,
        "pool": pool,
        "window_blocks": [start_block, end_block],
        "window_ts": [first_ts, end_ts],
        "fee_window_eth": [low_value, high_value],
        "total_qualifying_withdrawals": len(recipients),
        "unique_recipients": len(counts),
        "counts": counts,
        "detail": detail,
    }


def run_demix(client, wallet, window_days=30, fee_lo=0.90, fee_hi=0.995, gap_hours=24):
    """Full single-wallet demix. Returns a structured result dict."""
    wallet = wallet.lower()
    _log(f"[*] Wallet: {wallet}")

    deposits = detect_deposits(client, wallet)
    _log(f"[*] Tornado deposits detected: {len(deposits)}")
    if not deposits:
        return {"wallet": wallet, "deposits": [], "vouchers": [], "denoms": {}}

    vouchers = cluster_vouchers(deposits, gap_hours=gap_hours)
    for voucher in vouchers:
        _log(
            f"    voucher: {voucher['count']} x {voucher['denom']} ETH @ "
            f"{datetime.utcfromtimestamp(voucher['first_ts']):%Y-%m-%d %H:%M} UTC"
        )

    results = {}
    for denom in sorted({v["denom"] for v in vouchers}):
        vouchers_for_denom = [v for v in vouchers if v["denom"] == denom]
        results[denom] = analyze_denom(
            client, denom, vouchers_for_denom, window_days, fee_lo, fee_hi
        )

    # Candidate matching: recipients whose hit-count equals a voucher size for
    # that denomination are likely the depositor's own consolidation address.
    for denom, res in results.items():
        target_counts = sorted({v["count"] for v in vouchers if v["denom"] == denom})
        res["target_counts"] = target_counts
        res["candidates_by_count"] = {
            n: [addr for addr, c in res["counts"].items() if c == n]
            for n in target_counts
        }

    return {
        "wallet": wallet,
        "params": {
            "window_days": window_days,
            "fee_window": [fee_lo, fee_hi],
            "gap_hours": gap_hours,
        },
        "deposits": deposits,
        "vouchers": vouchers,
        "denoms": results,
    }
