"""V7.1 exact runner.

Keeps the audited V7.0 accounting/optimizer and replaces only the transport and
pool classification/quote-dispatch layer. This makes comparison with V7.0
straightforward while avoiding silent public-RPC throttling and unsupported
DEX families consuming the candidate budget.
"""

import synergy_graph.v7_exact as engine
from synergy_graph.v7_exact_v2 import classify_pool_v2, exact_step_quote_v2
from synergy_graph.v7_rpc import ReliableRpc

engine.Rpc = ReliableRpc
engine.classify_pool = classify_pool_v2
engine.exact_step_quote = exact_step_quote_v2

if __name__ == "__main__":
    engine.cli()
