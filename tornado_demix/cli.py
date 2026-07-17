"""Command-line interface for the tornado_demix package.

Subcommands:
  demix    - analyse a single wallet
  multi    - analyse several wallets and correlate them
  cluster  - trace split-exit reconvergence for one or more wallets

The Etherscan API key is loaded from a CSV file (default: config/api.csv);
wallets can be supplied on the command line or via a CSV file.
"""

import argparse
import sys
from datetime import datetime

from . import config
from .cluster import trace_wallet
from .demix import run_demix
from .etherscan import EtherscanClient
from .multi import correlate
from .report import (
    write_cluster_csv,
    write_demix_csv,
    write_multi_csv,
)


def _add_common(parser):
    parser.add_argument("--api-csv", default=config.DEFAULT_API_CSV,
                        help="CSV file holding the Etherscan API key "
                             "(columns: service,api_key)")
    parser.add_argument("--window-days", type=int, default=30,
                        help="withdrawal search window after a deposit (default 30)")
    parser.add_argument("--fee-lo", type=float, default=0.90,
                        help="lower multiplier of denomination (default 0.90 = -10%%)")
    parser.add_argument("--fee-hi", type=float, default=0.995,
                        help="upper multiplier of denomination (default 0.995)")
    parser.add_argument("--gap-hours", type=float, default=24,
                        help="max gap to cluster deposits into one voucher")


def _wallets_from_args(args):
    """Resolve the wallet list from positional args or a CSV file."""
    if getattr(args, "wallets_csv", None):
        return config.load_wallets(args.wallets_csv)
    if getattr(args, "wallets", None):
        return [w.lower() for w in args.wallets]
    raise SystemExit("Provide wallet address(es) or --wallets-csv")


def cmd_demix(args):
    key = config.load_api_key(args.api_csv)
    client = EtherscanClient(key)
    data = run_demix(client, args.wallet, args.window_days,
                     args.fee_lo, args.fee_hi, args.gap_hours)

    print("\n=== DEMIX SUMMARY ===")
    print(f"Wallet: {data['wallet']}")
    for voucher in data["vouchers"]:
        print(f"Voucher: {voucher['count']} x {voucher['denom']} ETH starting "
              f"{datetime.utcfromtimestamp(voucher['first_ts']):%Y-%m-%d %H:%M} UTC")
    for denom, res in data["denoms"].items():
        print(f"\n[{denom} ETH] pool {res['pool']}")
        print(f"  qualifying withdrawals: {res['total_qualifying_withdrawals']} | "
              f"unique recipients: {res['unique_recipients']}")
        for n, addrs in res["candidates_by_count"].items():
            print(f"  recipients hit exactly {n}x -> {len(addrs)} candidate(s)")
            for addr in addrs:
                print(f"     {addr}")

    if args.out_dir:
        files = write_demix_csv(data, args.out_dir)
        print(f"\n[*] CSV report ({len(files)} files) in: {args.out_dir}", file=sys.stderr)


def cmd_multi(args):
    key = config.load_api_key(args.api_csv)
    client = EtherscanClient(key)
    wallets = _wallets_from_args(args)
    corr = correlate(client, wallets, args.window_days,
                     args.fee_lo, args.fee_hi, args.gap_hours)

    print("\n=== CROSS-WALLET CORRELATION ===")
    print(f"Wallets analysed: {len(wallets)}")
    print(f"Strong links (count-matched candidate shared by 2+): {len(corr['strong'])}")
    for denom, addr, ws in corr["strong"]:
        print(f"  [{denom} ETH] {addr} <- {', '.join(ws)}")
    print(f"\nProfile matches (full fingerprint on one address):")
    for wallet, matches in corr["profile_matches"].items():
        fingerprint = corr["fingerprints"][wallet]
        printable = " + ".join(f"{n}x{d}" for d, n in sorted(fingerprint.items()))
        exact = [m for m in matches if m[2]]
        print(f"  {wallet} ({printable}): "
              f"{len(exact)} exact, {len(matches)} total match(es)")
        for addr, _detail, is_exact in exact[:5]:
            print(f"     {'EXACT' if is_exact else '>='} {addr}")
    if corr["cross_profile"]:
        print("\nCross-wallet consolidators:")
        for addr, ws in corr["cross_profile"].items():
            print(f"  {addr} <- {', '.join(ws)}")

    if args.out_dir:
        files = write_multi_csv(corr, args.out_dir)
        print(f"\n[*] CSV report ({len(files)} files) in: {args.out_dir}", file=sys.stderr)


def cmd_cluster(args):
    key = config.load_api_key(args.api_csv)
    client = EtherscanClient(key)
    wallets = _wallets_from_args(args)

    traces = []
    for wallet in wallets:
        trace = trace_wallet(client, wallet, args.cache_dir, args.window_days,
                             args.fee_lo, args.fee_hi, args.gap_hours, args.layer_cap)
        traces.append(trace)

    print("\n=== CLUSTER CONSOLIDATION POINTS ===")
    for trace in traces:
        printable = " + ".join(f"{n}x{d}" for d, n in sorted(trace["fingerprint"].items()))
        print(f"\n{trace['wallet']} ({printable})")
        if not trace["clusters"]:
            print("   no downstream address is fed by 2+ denomination layers")
            continue
        for cluster in trace["clusters"][:8]:
            covered = ", ".join(f"{d}ETH" for d in cluster["denoms_covered"])
            print(f"   Z {cluster['z']} | layers={cluster['n_layers']} [{covered}] "
                  f"| ~{cluster['total_eth']} ETH")

    if args.out_dir:
        files = write_cluster_csv(traces, args.out_dir)
        print(f"\n[*] CSV report ({len(files)} files) in: {args.out_dir}", file=sys.stderr)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="tornado-demix",
        description="Tornado.Cash (ETH) demixing via amount + timing correlation.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_demix = sub.add_parser("demix", help="analyse a single wallet")
    p_demix.add_argument("wallet", help="depositor wallet address (0x...)")
    p_demix.add_argument("--out-dir", default="", help="directory to write CSV report files")
    _add_common(p_demix)
    p_demix.set_defaults(func=cmd_demix)

    p_multi = sub.add_parser("multi", help="analyse & correlate several wallets")
    p_multi.add_argument("wallets", nargs="*", help="wallet addresses")
    p_multi.add_argument("--wallets-csv", default="",
                         help="CSV file with an 'address' column")
    p_multi.add_argument("--out-dir", default="", help="directory to write CSV report files")
    _add_common(p_multi)
    p_multi.set_defaults(func=cmd_multi)

    p_cluster = sub.add_parser("cluster", help="trace split-exit reconvergence")
    p_cluster.add_argument("wallets", nargs="*", help="wallet addresses")
    p_cluster.add_argument("--wallets-csv", default="",
                           help="CSV file with an 'address' column")
    p_cluster.add_argument("--out-dir", default="", help="directory to write CSV report files")
    p_cluster.add_argument("--cache-dir", default=".cache",
                           help="directory for resumable forward/layer caches")
    p_cluster.add_argument("--layer-cap", type=int, default=35,
                           help="skip a denomination layer with more candidates than this")
    _add_common(p_cluster)
    p_cluster.set_defaults(func=cmd_cluster)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
