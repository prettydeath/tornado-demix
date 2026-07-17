"""CSV report writers for the demix / multi / cluster commands.

Every command writes a small set of plain-CSV files into an output directory,
so results are easy to open in any spreadsheet, grep, or load with pandas.
Timestamps are rendered as ISO-8601 UTC strings.
"""

import csv
import os
from datetime import datetime, timezone


def _ts(ts):
    """UNIX seconds -> 'YYYY-MM-DD HH:MM:SSZ' (UTC)."""
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


def _write(path, header, rows):
    """Write a single CSV file and return its path."""
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)
    return path


def _ensure_dir(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


# ---------------------------------------------------------------------------
# Single-wallet CSVs
# ---------------------------------------------------------------------------
def write_demix_csv(data, out_dir):
    """Write single-wallet demix results as CSV files. Returns the file list."""
    _ensure_dir(out_dir)
    files = []

    # vouchers.csv
    files.append(_write(
        os.path.join(out_dir, "vouchers.csv"),
        ["denomination_eth", "num_deposits", "first_deposit_utc", "last_deposit_utc"],
        [[v["denom"], v["count"], _ts(v["first_ts"]), _ts(v["last_ts"])]
         for v in data["vouchers"]],
    ))

    # deposits.csv
    files.append(_write(
        os.path.join(out_dir, "deposits.csv"),
        ["idx", "denomination_eth", "timestamp_utc", "block", "to_address", "via", "tx_hash"],
        [[i, d["denom"], _ts(d["ts"]), d["block"], d["to"], d["via"], d["hash"]]
         for i, d in enumerate(data["deposits"], 1)],
    ))

    # candidates.csv (count-matched recipients across all denominations)
    cand_rows = []
    for denom, res in data["denoms"].items():
        for n in res.get("target_counts", []):
            for addr in res["candidates_by_count"].get(n, []):
                records = res["detail"][addr]
                total = round(sum(x["value"] for x in records), 6)
                cand_rows.append([denom, n, addr, total,
                                  _ts(min(x["ts"] for x in records)),
                                  _ts(max(x["ts"] for x in records))])
    files.append(_write(
        os.path.join(out_dir, "candidates.csv"),
        ["denomination_eth", "match_count", "candidate_address",
         "total_eth_received", "first_seen_utc", "last_seen_utc"],
        cand_rows,
    ))

    # withdrawals_<denom>ETH.csv: every qualifying recipient for the denomination
    for denom, res in data["denoms"].items():
        targets = set(res.get("target_counts", []))
        rows = []
        for addr, hits in res["counts"].items():
            records = res["detail"][addr]
            total = round(sum(x["value"] for x in records), 6)
            timestamps = sorted(x["ts"] for x in records)
            hashes = ";".join(x["hash"] for x in records[:4])
            rows.append([addr, hits, "yes" if hits in targets else "",
                         total, _ts(timestamps[0]), _ts(timestamps[-1]), hashes])
        rows.sort(key=lambda r: (r[2] != "yes", -r[1]))
        fname = f"withdrawals_{str(denom).replace('.', '_')}ETH.csv"
        files.append(_write(
            os.path.join(out_dir, fname),
            ["recipient_address", "hit_count", "is_candidate",
             "total_eth_received", "first_seen_utc", "last_seen_utc", "sample_tx_hashes"],
            rows,
        ))

    return files


# ---------------------------------------------------------------------------
# Multi-wallet CSVs
# ---------------------------------------------------------------------------
def write_multi_csv(corr, out_dir):
    """Write multi-wallet correlation results as CSV files."""
    _ensure_dir(out_dir)
    results = corr["results"]
    addr_detail = corr["addr_detail"]
    files = []

    # wallets_overview.csv
    overview = []
    for wallet, data in results.items():
        if not data["vouchers"]:
            overview.append([wallet, "", "", "", "", "", ""])
            continue
        for v in data["vouchers"]:
            res = data["denoms"][v["denom"]]
            n_cand = sum(len(res["candidates_by_count"].get(n, []))
                         for n in res.get("target_counts", []))
            overview.append([wallet, v["denom"], v["count"], _ts(v["first_ts"]),
                             res["total_qualifying_withdrawals"],
                             res["unique_recipients"], n_cand])
    files.append(_write(
        os.path.join(out_dir, "wallets_overview.csv"),
        ["wallet", "denomination_eth", "num_deposits", "first_deposit_utc",
         "qualifying_withdrawals", "unique_recipients", "num_candidates"],
        overview,
    ))

    # strong_links.csv and soft_overlaps.csv
    for name, entries in (("strong_links", corr["strong"]), ("soft_overlaps", corr["soft"])):
        rows = []
        for denom, addr, wallets in entries:
            detail = ";".join(f"{w}({addr_detail[(denom, addr)][w]}x)" for w in wallets)
            rows.append([denom, addr, len(wallets), detail])
        files.append(_write(
            os.path.join(out_dir, f"{name}.csv"),
            ["denomination_eth", "address", "num_wallets", "wallets_and_hitcounts"],
            rows,
        ))

    # profile_matches.csv
    prof_rows = []
    for wallet, fingerprint in corr["fingerprints"].items():
        printable = " + ".join(f"{n}x{d}" for d, n in sorted(fingerprint.items()))
        multi = "yes" if len(fingerprint) >= 2 else "no"
        for addr, detail, exact in corr["profile_matches"].get(wallet, []):
            recv = ";".join(f"{d}ETH:{r}/{n}" for d, (r, n) in sorted(detail.items()))
            prof_rows.append([wallet, printable, addr,
                              "exact" if exact else "gte", recv, multi])
    files.append(_write(
        os.path.join(out_dir, "profile_matches.csv"),
        ["wallet", "fingerprint", "consolidator_address",
         "match_type", "received_vs_needed", "multi_denomination"],
        prof_rows,
    ))

    # cross_consolidators.csv
    files.append(_write(
        os.path.join(out_dir, "cross_consolidators.csv"),
        ["consolidator_address", "num_wallets", "wallets"],
        [[addr, len(ws), ";".join(ws)] for addr, ws in corr["cross_profile"].items()],
    ))

    return files


# ---------------------------------------------------------------------------
# Cluster CSVs
# ---------------------------------------------------------------------------
def write_cluster_csv(traces, out_dir):
    """Write cluster-trace results as CSV files."""
    _ensure_dir(out_dir)
    files = []

    cluster_rows, detail_rows = [], []
    for trace in traces:
        printable = " + ".join(f"{n}x{d}" for d, n in sorted(trace["fingerprint"].items()))
        if not trace["clusters"]:
            cluster_rows.append([trace["wallet"], printable, "", 0, "", "", ""])
            continue
        for cluster in trace["clusters"]:
            sources = []
            for denom, lst in cluster["by_denom"].items():
                for src, _v, _t, _h in lst[:2]:
                    sources.append(f"{denom}ETH:{src}")
            cluster_rows.append([
                trace["wallet"], printable, cluster["z"], cluster["n_layers"],
                ",".join(str(d) for d in cluster["denoms_covered"]),
                cluster["total_eth"], ";".join(sources[:6]),
            ])
            for denom, lst in cluster["by_denom"].items():
                for src, value, ts, tx_hash in lst:
                    detail_rows.append([trace["wallet"], cluster["z"], denom, src,
                                        round(value, 6), _ts(ts), tx_hash])

    files.append(_write(
        os.path.join(out_dir, "clusters.csv"),
        ["wallet", "fingerprint", "cluster_point_z", "num_denom_layers",
         "denoms_covered", "eth_funneled", "sample_source_candidates"],
        cluster_rows,
    ))
    files.append(_write(
        os.path.join(out_dir, "cluster_detail.csv"),
        ["wallet", "cluster_point_z", "denomination_eth", "source_candidate",
         "forward_eth", "forward_time_utc", "tx_hash"],
        detail_rows,
    ))
    return files
