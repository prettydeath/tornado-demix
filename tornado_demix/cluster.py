"""Cluster forwarding tracer for split-exit wallets.

When a depositor does NOT consolidate to a single address, its notes are
withdrawn to several addresses. This module takes the per-denomination
count-matched candidates, traces where each forwards funds (one hop), and
looks for a common downstream address ``Z`` fed by two or more denomination
layers. Such a ``Z`` is where the split exits reconverge.

Forward lookups and per-wallet demix layers are cached on disk so a run that
is interrupted (e.g. by a time limit) can simply be re-run and resume.
"""

import json
import os
import time
from collections import defaultdict

from .constants import NON_DOWNSTREAM
from .demix import run_demix

# Tunables.
LAYER_CAP = 35          # skip a denomination layer with more candidates than this
FORWARD_DAYS = 21       # how long after a withdrawal to look for the forward hop
MIN_FORWARD_ETH = 0.05  # ignore dust forwards below this value
PAUSE_BETWEEN = 0.08    # small delay between forward lookups (politeness)


class ForwardCache:
    """JSON-backed cache of first-hop forwards, keyed by address."""

    def __init__(self, path):
        self.path = path
        self.data = {}
        if path and os.path.exists(path):
            try:
                with open(path) as fh:
                    self.data = json.load(fh)
            except Exception:
                self.data = {}

    def get(self, addr):
        return self.data.get(addr)

    def put(self, addr, forwards):
        self.data[addr] = forwards
        try:
            with open(self.path, "w") as fh:
                json.dump(self.data, fh)
        except Exception:
            pass


def _demix_layers(client, wallet, params, cache_dir, layer_cap):
    """Return (fingerprint, layers) for a wallet, using an on-disk cache.

    ``layers`` maps denomination -> {candidate_address: earliest_withdrawal_ts}
    or None when the layer is unusable (no exact-count candidate, or too noisy).
    """
    cache_path = os.path.join(cache_dir, f"layers_{wallet[:10]}.json")
    if os.path.exists(cache_path):
        try:
            cached = json.load(open(cache_path))
            fingerprint = {float(k): v for k, v in cached["fp"].items()}
            layers = {
                float(k): (None if v is None else {a: t for a, t in v.items()})
                for k, v in cached["layers"].items()
            }
            return fingerprint, layers
        except Exception:
            pass

    data = run_demix(client, wallet, **params)
    fingerprint = defaultdict(int)
    for voucher in data["vouchers"]:
        fingerprint[voucher["denom"]] += voucher["count"]
    fingerprint = dict(fingerprint)

    layers = {}
    for denom, res in data["denoms"].items():
        need = fingerprint[denom]
        candidates = [addr for addr, hits in res["counts"].items() if hits == need]
        if not candidates or len(candidates) > layer_cap:
            layers[denom] = None
            continue
        layers[denom] = {
            addr: min(x["ts"] for x in res["detail"][addr]) for addr in candidates
        }

    try:
        json.dump(
            {"fp": {str(k): v for k, v in fingerprint.items()},
             "layers": {str(k): v for k, v in layers.items()}},
            open(cache_path, "w"),
        )
    except Exception:
        pass
    return fingerprint, layers


def _forwards(client, cache, addr, after_ts):
    """First-hop ETH sends from ``addr``, cached, filtered of dust/pools."""
    cached = cache.get(addr)
    if cached is not None:
        return cached
    end_ts = after_ts + FORWARD_DAYS * 86400
    sends = [
        f for f in client.outgoing_in_window(addr, after_ts, end_ts)
        if f["value"] >= MIN_FORWARD_ETH and f["to"] and f["to"] not in NON_DOWNSTREAM
    ]
    cache.put(addr, sends)
    time.sleep(PAUSE_BETWEEN)
    return sends


def trace_wallet(client, wallet, cache_dir, window_days=30, fee_lo=0.90,
                 fee_hi=0.995, gap_hours=24, layer_cap=LAYER_CAP):
    """Trace one wallet's split exits and return reconvergence clusters."""
    wallet = wallet.lower()
    os.makedirs(cache_dir, exist_ok=True)
    cache = ForwardCache(os.path.join(cache_dir, "fwd_cache.json"))

    params = dict(window_days=window_days, fee_lo=fee_lo,
                  fee_hi=fee_hi, gap_hours=gap_hours)
    fingerprint, layers = _demix_layers(client, wallet, params, cache_dir, layer_cap)
    usable = {denom: members for denom, members in layers.items() if members}

    # downstream Z -> {denom -> [(source_candidate, value, ts, hash)]}
    downstream = defaultdict(lambda: defaultdict(list))
    for denom, members in usable.items():
        for candidate, first_ts in members.items():
            for forward in _forwards(client, cache, candidate, first_ts):
                downstream[forward["to"]][denom].append(
                    (candidate, forward["value"], forward["ts"], forward["hash"])
                )

    clusters = []
    for z_addr, by_denom in downstream.items():
        if len(by_denom) >= 2:  # fed by two or more denomination layers
            total = sum(v for lst in by_denom.values() for (_, v, _, _) in lst)
            clusters.append({
                "z": z_addr,
                "denoms_covered": sorted(by_denom.keys()),
                "n_layers": len(by_denom),
                "total_eth": round(total, 4),
                "by_denom": {d: lst for d, lst in by_denom.items()},
            })
    clusters.sort(key=lambda c: (-c["n_layers"], -c["total_eth"]))

    return {
        "wallet": wallet,
        "fingerprint": fingerprint,
        "layers": layers,
        "clusters": clusters,
    }
