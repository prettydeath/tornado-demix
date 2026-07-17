"""On-chain constants for Tornado.Cash ETH demixing.

All addresses are stored lowercased so comparisons are case-insensitive.
"""

# Etherscan V2 unified API endpoint (chainid selects the network).
ETHERSCAN_API_URL = "https://api.etherscan.io/v2/api"
CHAIN_ID = 1  # Ethereum mainnet

WEI = 10 ** 18

# Tornado.Cash ETH pools: denomination (in ETH) -> pool contract address.
POOLS = {
    0.1: "0x12d66f87a04a9e220743712ce6d9bb1b5616b8fc",
    1.0: "0x47ce0c6ed5b0ce3d3a51fdb1c52dc66a7c3c2936",
    10.0: "0x910cbd523d972eb0a6f4cae4618ad62622b39dbf",
    100.0: "0xa160cdab225685da1d56aa342ad8841c3b53f291",
}

# Reverse lookup: pool address -> denomination.
POOL_BY_ADDR = {addr: denom for denom, addr in POOLS.items()}

# Deposit entry points. Deposits may go straight to a pool or be routed through
# one of these router/proxy contracts; in both cases the tx value equals the
# denomination.
ROUTERS = {
    "0xd90e2f925da726b50c4ed8d0fb90ad053324f31b",  # Tornado.Cash: Router
    "0x722122df12d4e14e13ac3b6895a86e84145b6967",  # Tornado.Cash: Proxy (legacy)
    "0x905b63fff465b9ffbf41dea908ceb12478ec7601",  # Tornado.Cash: Proxy
}

# Addresses that must never be treated as a downstream consolidation point.
NON_DOWNSTREAM = set(ROUTERS) | set(POOLS.values()) | {
    "0x0000000000000000000000000000000000000000",  # burn / null address
}

# Set of supported denominations.
DENOMINATIONS = set(POOLS.keys())

# Block explorer templates for building verification links.
EXPLORER_TX = "https://etherscan.io/tx/"
EXPLORER_ADDR = "https://etherscan.io/address/"
