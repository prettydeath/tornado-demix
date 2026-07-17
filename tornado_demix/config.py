"""Configuration loaders.

The Etherscan API key and the list of wallets to analyse are read from CSV
files so that no secret is ever hard-coded or passed on the command line.

api.csv format (header required):

    service,api_key
    etherscan,YOUR_ETHERSCAN_KEY

wallets.csv format (header required, extra columns are ignored):

    address,label
    0x019b5bb2051797e33f726d0e7a8cb9b9c2003ac2,suspect-1
"""

import csv
import os

# Default locations, relative to the repository root / current directory.
DEFAULT_API_CSV = os.path.join("config", "api.csv")
DEFAULT_WALLETS_CSV = os.path.join("config", "wallets.csv")


def load_api_key(csv_path=DEFAULT_API_CSV, service="etherscan"):
    """Return the API key for ``service`` from a CSV file.

    Resolution order:
      1. the ``service`` row of ``csv_path`` (columns: service, api_key);
      2. the ``ETHERSCAN_API_KEY`` environment variable as a fallback.

    Raises SystemExit with a helpful message if no key can be found.
    """
    key = None
    if csv_path and os.path.exists(csv_path):
        with open(csv_path, newline="") as fh:
            for row in csv.DictReader(fh):
                if (row.get("service") or "").strip().lower() == service.lower():
                    key = (row.get("api_key") or "").strip()
                    break
    if not key:
        key = os.environ.get("ETHERSCAN_API_KEY", "").strip()
    if not key:
        raise SystemExit(
            f"No API key found. Add a '{service}' row to {csv_path} "
            f"(columns: service,api_key) or set ETHERSCAN_API_KEY."
        )
    return key


def load_wallets(csv_path=DEFAULT_WALLETS_CSV):
    """Return a list of lowercased wallet addresses from a CSV file.

    The file must have an ``address`` column; a 0x-prefixed 40-hex value is
    required. Blank rows and comment rows (starting with '#') are skipped.
    """
    if not csv_path or not os.path.exists(csv_path):
        raise SystemExit(f"Wallets CSV not found: {csv_path}")
    wallets = []
    with open(csv_path, newline="") as fh:
        for row in csv.DictReader(fh):
            addr = (row.get("address") or "").strip().lower()
            if not addr or addr.startswith("#"):
                continue
            if len(addr) == 42 and addr.startswith("0x"):
                wallets.append(addr)
    if not wallets:
        raise SystemExit(f"No valid addresses in {csv_path}")
    return wallets
