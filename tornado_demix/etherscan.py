"""Minimal Etherscan V2 API client with pagination and rate-limit handling."""

import sys
import time

import requests

from .constants import ETHERSCAN_API_URL, CHAIN_ID

# Etherscan returns at most PAGE_SIZE rows per request and at most MAX_PAGES
# pages (10,000 rows) for a single query; larger result sets require narrowing
# the block range. Both limits are handled by ``fetch_all`` below.
PAGE_SIZE = 1000
MAX_PAGES = 10


def _log(msg):
    """Write progress to stderr so it never pollutes stdout / piped output."""
    print(msg, file=sys.stderr, flush=True)


class EtherscanClient:
    """Thin wrapper around the Etherscan V2 unified API.

    A single :class:`requests.Session` is reused for connection pooling. Soft
    errors (rate limits, transient failures) are retried with linear backoff.
    """

    def __init__(self, api_key, chain_id=CHAIN_ID, pause=0.0, retries=5):
        self.api_key = api_key
        self.chain_id = chain_id
        self.pause = pause          # optional fixed delay between calls
        self.retries = retries
        self.session = requests.Session()

    def call(self, params):
        """Perform one API call and return the ``result`` field.

        Returns an empty list for the benign "No transactions found" response.
        Raises SystemExit if the API key is rejected.
        """
        query = dict(params)
        query["chainid"] = self.chain_id
        query["apikey"] = self.api_key

        result = []
        for attempt in range(self.retries):
            if self.pause:
                time.sleep(self.pause)
            try:
                resp = self.session.get(ETHERSCAN_API_URL, params=query, timeout=40)
                payload = resp.json()
            except Exception:  # network / JSON error -> back off and retry
                time.sleep(1.5 * (attempt + 1))
                continue

            status = payload.get("status")
            message = str(payload.get("message", ""))
            result = payload.get("result")

            if status == "1":
                return result
            if isinstance(result, str) and (
                "rate limit" in result.lower() or "max calls" in result.lower()
            ):
                time.sleep(1.2 * (attempt + 1))
                continue
            if "No transactions found" in message or result == []:
                return []
            if isinstance(result, str) and (
                "Invalid API Key" in result or "Missing" in result
            ):
                raise SystemExit(f"Etherscan rejected the API key: {result}")
            # Unknown soft error: retry a couple of times, then give up.
            time.sleep(0.8 * (attempt + 1))
        return result if isinstance(result, list) else []

    # ------------------------------------------------------------------ #
    # Convenience helpers                                                  #
    # ------------------------------------------------------------------ #

    def fetch_all(self, action, address, start_block=0, end_block=99999999):
        """Return every ``account/<action>`` row for ``address`` in a range.

        Handles both Etherscan limits: it pages through up to ``MAX_PAGES``
        pages of ``PAGE_SIZE`` rows, and when a query overflows that cap it
        splits the block range and continues from the last block seen. Results
        are de-duplicated by tx hash.
        """
        address = address.lower()

        def page_range(low, high):
            rows, overflow = [], False
            for page in range(1, MAX_PAGES + 1):
                chunk = self.call({
                    "module": "account",
                    "action": action,
                    "address": address,
                    "startblock": low,
                    "endblock": high,
                    "page": page,
                    "offset": PAGE_SIZE,
                    "sort": "asc",
                })
                if not chunk:
                    break
                rows.extend(chunk)
                if len(chunk) < PAGE_SIZE:
                    break
            else:
                overflow = True  # filled all MAX_PAGES -> there may be more
            return rows, overflow

        collected, low = [], start_block
        while True:
            rows, overflow = page_range(low, end_block)
            if not overflow:
                collected.extend(rows)
                break
            # Overflow: keep rows strictly before the last block, then resume
            # from that block so no transaction in it is skipped.
            max_block = max(int(r["blockNumber"]) for r in rows)
            if max_block <= low:
                collected.extend(rows)  # single block overflowing; take as-is
                break
            collected.extend(r for r in rows if int(r["blockNumber"]) < max_block)
            low = max_block
        return _dedupe_by_hash(collected)

    def block_by_time(self, timestamp, closest="before"):
        """Return the block number closest to a UNIX timestamp, or None."""
        result = self.call({
            "module": "block",
            "action": "getblocknobytime",
            "timestamp": int(timestamp),
            "closest": closest,
        })
        try:
            return int(result)
        except (TypeError, ValueError):
            return None

    def outgoing_txs(self, address):
        """Return every normal transaction sent from ``address``."""
        return self.fetch_all("txlist", address)

    def internal_from(self, contract, start_block, end_block):
        """Return internal txs sent FROM ``contract`` within a block range."""
        contract = contract.lower()
        rows = self.fetch_all("txlistinternal", contract, start_block, end_block)
        return [r for r in rows if (r.get("from") or "").lower() == contract]

    def outgoing_in_window(self, address, start_ts, end_ts, include_internal=True):
        """Return ETH sends FROM ``address`` between two timestamps.

        Used for forward-tracing. Combines normal and (optionally) internal
        transactions. Each item is a dict: to, value (ETH), ts, hash.
        """
        address = address.lower()
        actions = ["txlist"] + (["txlistinternal"] if include_internal else [])
        sends = []
        for action in actions:
            for tx in self.fetch_all(action, address):
                if (tx.get("from") or "").lower() != address:
                    continue
                if tx.get("isError") == "1":
                    continue
                ts = int(tx.get("timeStamp", 0))
                if ts < start_ts or ts > end_ts:
                    continue
                sends.append({
                    "to": (tx.get("to") or "").lower(),
                    "value": int(tx.get("value", "0")) / 10 ** 18,
                    "ts": ts,
                    "hash": tx.get("hash", ""),
                })
        return sends


def _dedupe_by_hash(txs):
    """Return transactions with duplicate hashes removed, order preserved."""
    seen, unique = set(), []
    for tx in txs:
        h = tx.get("hash")
        if h and h not in seen:
            seen.add(h)
            unique.append(tx)
    return unique
