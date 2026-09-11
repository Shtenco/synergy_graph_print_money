from __future__ import annotations

from collections.abc import Iterable

from .v7 import Pool

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
WETH_BASE = "0x4200000000000000000000000000000000000006"


def canonical_external_tokens(pools: Iterable[Pool]) -> list[str]:
    """Return canonical Base hard-asset nodes for protocol graph accounting.

    Some V4/Infinity data sources represent native ETH as address(0).  The
    execution system settles ERC-20 inventory and already has WETH in the Base
    graph, so address(0) must map to WETH rather than create a separate node.
    This prevents native-ETH sentinels from inflating C(n,2) own-pool counts.
    """
    nodes: set[str] = set()
    for p in pools:
        for token in (p.token0, p.token1):
            t = (token or "").lower()
            if not t:
                continue
            nodes.add(WETH_BASE if t == ZERO_ADDRESS else t)
    return sorted(nodes)
