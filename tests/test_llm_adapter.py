import llm.adapter as adapter
from discipline import parse_action


class _FakeChoiceMsg:
    def __init__(self, content: str) -> None:
        self.message = type("M", (), {"content": content})()


class _FakeClient:
    def __init__(self, content: str = '{"action":"final","message":"ok"}', boom: bool = False) -> None:
        self.content = content
        self.boom = boom
        self.kwargs: dict | None = None
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.kwargs = kwargs
                if outer.boom:
                    raise RuntimeError("boom")
                return type("R", (), {"choices": [_FakeChoiceMsg(outer.content)]})()

        self.chat = type("C", (), {"completions": _Completions()})()


def test_module_import_is_lazy():
    adapter.reset_client()
    assert adapter._client is None  # no client built just by importing/using helpers


def test_injected_client_json_mode():
    fake = _FakeClient()
    out = adapter.call_llm([{"role": "user", "content": "hi"}], model="m1", client=fake)
    assert out == '{"action":"final","message":"ok"}'
    assert fake.kwargs["response_format"] == {"type": "json_object"}
    assert fake.kwargs["model"] == "m1"
    assert adapter._client is None  # injected client must not populate the cache


def test_json_mode_off():
    fake = _FakeClient()
    adapter.call_llm([{"role": "user", "content": "hi"}], json_mode=False, client=fake)
    assert "response_format" not in fake.kwargs


def test_error_returns_structured_final():
    fake = _FakeClient(boom=True)
    action = parse_action(adapter.call_llm([{"role": "user", "content": "hi"}], client=fake))
    assert action["action"] == "final"
    assert action["finish_reason"] == "error"
