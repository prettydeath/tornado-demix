"""Multi-wallet correlation: intersections and denomination-profile matching.

Given several depositor wallets, this module finds:
  * strong links   - a count-matched candidate shared by 2+ wallets;
  * soft overlaps  - any qualifying recipient shared by 2+ wallets;
  * profile match  - one address that received a wallet's FULL denomination
                     fingerprint (strongest single-wallet exit signal);
  * cross profile  - one address that is a full consolidator for 2+ wallets.

IMPORTANT CAVEAT (surfaced in the report): when wallets deposit at similar
times and use the same voucher size, their search windows overlap, so the
count-matched sets are nearly identical by construction. Raw intersections
(especially soft overlaps) are then an artefact of the shared window rather
than evidence of a link. The discriminating signal is the multi-denomination
profile match plus the synchronicity of deposit timing.
"""

from collections import defaultdict

from .demix import run_demix


def correlate(client, wallets, window_days=30, fee_lo=0.90, fee_hi=0.995, gap_hours=24):
    """Run demix on every wallet and compute cross-wallet correlations.

    Returns a dict with keys: results, strong, soft, addr_detail, fingerprints,
    profile_matches, cross_profile.
    """
    results = {}                                  # wallet -> run_demix output
    cand_members = defaultdict(lambda: defaultdict(set))  # denom -> addr -> wallets
    qual_members = defaultdict(lambda: defaultdict(set))  # denom -> addr -> wallets
    addr_detail = defaultdict(dict)               # (denom, addr) -> wallet -> hits

    for wallet in wallets:
        wallet = wallet.lower()
        data = run_demix(client, wallet, window_days, fee_lo, fee_hi, gap_hours)
        results[wallet] = data
        for denom, res in data["denoms"].items():
            candidates = set()
            for n in res.get("target_counts", []):
                candidates.update(res["candidates_by_count"].get(n, []))
            for addr in candidates:
                cand_members[denom][addr].add(wallet)
            for addr, hits in res["counts"].items():
                qual_members[denom][addr].add(wallet)
                addr_detail[(denom, addr)][wallet] = hits

    strong = _shared(cand_members)
    strong_keys = {(denom, addr) for denom, addr, _ in strong}
    soft = [
        entry for entry in _shared(qual_members)
        if (entry[0], entry[1]) not in strong_keys
    ]

    fingerprints = _fingerprints(results)
    profile_matches, cross_profile = _profile_match(fingerprints, addr_detail)

    return {
        "results": results,
        "strong": strong,
        "soft": soft,
        "addr_detail": addr_detail,
        "fingerprints": fingerprints,
        "profile_matches": profile_matches,
        "cross_profile": cross_profile,
    }


def _shared(membership):
    """Return [(denom, address, sorted_wallets)] for addresses in 2+ wallets."""
    shared = []
    for denom, addr_map in membership.items():
        for addr, wallets in addr_map.items():
            if len(wallets) >= 2:
                shared.append((denom, addr, sorted(wallets)))
    shared.sort(key=lambda entry: (-len(entry[2]), entry[0]))
    return shared


def _fingerprints(results):
    """wallet -> {denom: total notes deposited across all its vouchers}."""
    fingerprints = {}
    for wallet, data in results.items():
        fingerprint = defaultdict(int)
        for voucher in data["vouchers"]:
            fingerprint[voucher["denom"]] += voucher["count"]
        fingerprints[wallet] = dict(fingerprint)
    return fingerprints


def _profile_match(fingerprints, addr_detail):
    """Find addresses that received a wallet's full denomination fingerprint.

    For wallet W with fingerprint {d: N_d}, a consolidation candidate A must
    have received at least N_d withdrawals of every denomination d in W's
    window. Multi-denomination fingerprints are far more discriminating than a
    single count, so those matches are highlighted as strong.
    """
    profile_matches = defaultdict(list)      # wallet -> [(addr, detail, exact)]
    addr_profile_wallets = defaultdict(set)  # addr -> wallets it fully matches

    for wallet, fingerprint in fingerprints.items():
        denoms = list(fingerprint.keys())
        per_denom_sets = []
        for denom in denoms:
            need = fingerprint[denom]
            matching = {
                addr for (d, addr), by_wallet in addr_detail.items()
                if d == denom and by_wallet.get(wallet, 0) >= need
            }
            per_denom_sets.append(matching)

        common = set.intersection(*per_denom_sets) if per_denom_sets else set()
        for addr in common:
            detail, exact = {}, True
            for denom in denoms:
                received = addr_detail[(denom, addr)].get(wallet, 0)
                need = fingerprint[denom]
                detail[denom] = (received, need)
                if received != need:
                    exact = False
            profile_matches[wallet].append((addr, detail, exact))
            if len(denoms) >= 2:
                addr_profile_wallets[addr].add(wallet)
        profile_matches[wallet].sort(key=lambda entry: (not entry[2], entry[0]))

    cross_profile = {
        addr: sorted(wallets)
        for addr, wallets in addr_profile_wallets.items()
        if len(wallets) >= 2
    }
    return profile_matches, cross_profile
