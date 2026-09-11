"""V7.1 exact runner with pinned-state Balancer flash-fee discovery.

Keeps the V7.0 accounting/optimizer and replaces transport/classification while
removing the optimistic assumption that Balancer flash fee is permanently 0.
If --flash-fee-bps is omitted, the runner reads Vault.getProtocolFeesCollector()
and ProtocolFeesCollector.getFlashLoanFeePercentage() at the same block used for
quotes. Failure to resolve the fee aborts the run.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import synergy_graph.v7_exact as engine
from synergy_graph.v7 import BALANCER_V2_VAULT, decode_address, decode_uint
from synergy_graph.v7_exact import calldata
from synergy_graph.v7_exact_v2 import classify_pool_v2, exact_step_quote_v2
from synergy_graph.v7_rpc import ReliableRpc

engine.Rpc = ReliableRpc
engine.classify_pool = classify_pool_v2
engine.exact_step_quote = exact_step_quote_v2


def fixed18_to_bps(raw: int) -> float:
    return raw * 10_000.0 / 1e18


def _arg_value(flag: str) -> str | None:
    try:
        i = sys.argv.index(flag)
    except ValueError:
        return None
    return sys.argv[i + 1] if i + 1 < len(sys.argv) else None


def resolve_balancer_flash_fee_bps(rpc_url: str, block_number: int) -> tuple[float, str]:
    rpc = ReliableRpc(rpc_url)
    block = hex(block_number)
    collector_raw = rpc.eth_call(
        BALANCER_V2_VAULT,
        calldata("getProtocolFeesCollector()", [], []),
        block,
    )
    collector = decode_address(collector_raw)
    if not collector:
        raise RuntimeError("Balancer ProtocolFeesCollector address unavailable at pinned block")
    fee_raw = rpc.eth_call(
        collector,
        calldata("getFlashLoanFeePercentage()", [], []),
        block,
    )
    if not fee_raw or fee_raw == "0x":
        raise RuntimeError("Balancer flash-loan fee unavailable at pinned block")
    return fixed18_to_bps(decode_uint(fee_raw)), collector.lower()


def main() -> None:
    auto_fee = "--flash-fee-bps" not in sys.argv
    collector = None
    if auto_fee:
        rpc_url = _arg_value("--rpc-url") or os.getenv("BASE_RPC_URL", "https://base-rpc.publicnode.com")
        block_text = _arg_value("--block")
        probe = ReliableRpc(rpc_url)
        block_number = int(block_text) if block_text is not None else probe.latest_block()
        fee_bps, collector = resolve_balancer_flash_fee_bps(rpc_url, block_number)
        sys.argv.extend(["--flash-fee-bps", repr(fee_bps)])

    engine.cli()

    # Preserve provenance in the evidence artifact. The legacy field name is
    # retained for backward compatibility but is no longer an assumption when
    # V7.1 resolves the value on-chain.
    out = Path(_arg_value("--out") or "artifacts") / "v7_exact_report.json"
    if out.exists():
        report = json.loads(out.read_text(encoding="utf-8"))
        report["flash_fee_bps_source"] = "pinned_onchain_protocol_fees_collector" if auto_fee else "explicit_override"
        if collector:
            report["balancer_protocol_fees_collector"] = collector
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
