from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_runner():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_v7_exact_v2.py"
    spec = spec_from_file_location("run_v7_exact_v2", path)
    mod = module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_balancer_fixed18_fee_to_bps():
    mod = _load_runner()
    assert mod.fixed18_to_bps(0) == 0.0
    assert mod.fixed18_to_bps(10**14) == 1.0      # 0.01% = 1 bp
    assert mod.fixed18_to_bps(10**16) == 100.0   # 1% = 100 bps
