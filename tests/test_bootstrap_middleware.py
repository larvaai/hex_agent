"""Bootstrap wires middleware from config['middleware']; inert when the section is absent. Epic E06."""
from core.bootstrap import build_kernel


def test_no_middleware_key_means_none():
    k = build_kernel({"features": {}})
    assert k._middlewares == []


def test_config_wires_policy_and_condense_in_order():
    cfg = {
        "features": {"example_echo": {"enabled": True, "module": "features.example_echo"}},
        "middleware": {
            "policy": {"enabled": True, "deny": ["echo"]},
            "condense": {"enabled": True, "max_chars": 50},
        },
    }
    k = build_kernel(cfg)
    assert len(k._middlewares) == 2
    r = k.execute_tool("echo", {"a": 1})
    assert r["ok"] is False and r["metadata"].get("policy_block")  # policy is outer, blocks first
