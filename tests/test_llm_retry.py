"""LLM adapter retry/backoff: transient (timeout/connection/429/5xx) retried, permanent (4xx) not. Epic E03."""
import llm.adapter as adapter
from discipline import parse_action

OK = '{"action":"final","message":"ok"}'


class _StatusError(Exception):
    def __init__(self, status, msg="err"):
        super().__init__(msg)
        self.status_code = status


def _client(seq):
    """seq item = an Exception to raise, or a str content to return."""
    class _C:
        def __init__(self):
            self.calls = 0
            self.seq = list(seq)
            outer = self

            class _Comp:
                def create(self, **kw):
                    outer.calls += 1
                    item = outer.seq.pop(0)
                    if isinstance(item, Exception):
                        raise item
                    return type("R", (), {"choices": [type("Ch", (), {"message": type("M", (), {"content": item})()})()]})()

            self.chat = type("X", (), {"completions": _Comp()})()
    return _C()


def test_defaults_timeout_and_retries(monkeypatch):
    for k in ("LLM_TIMEOUT", "LLM_MAX_RETRIES", "LLM_RETRY_BASE"):
        monkeypatch.delenv(k, raising=False)
    d = adapter._defaults()
    assert d["timeout"] <= 120          # no longer 600
    assert d["max_retries"] >= 1


def test_retries_transient_5xx_then_succeeds(monkeypatch):
    monkeypatch.setenv("LLM_RETRY_BASE", "0")
    monkeypatch.setenv("LLM_MAX_RETRIES", "2")
    c = _client([_StatusError(503), _StatusError(503), OK])
    out = adapter.call_llm([{"role": "user", "content": "hi"}], client=c)
    assert out == OK
    assert c.calls == 3


def test_no_retry_on_permanent_4xx(monkeypatch):
    monkeypatch.setenv("LLM_RETRY_BASE", "0")
    monkeypatch.setenv("LLM_MAX_RETRIES", "2")
    c = _client([_StatusError(400), OK])
    action = parse_action(adapter.call_llm([{"role": "user", "content": "hi"}], client=c))
    assert action["finish_reason"] == "error"
    assert c.calls == 1                  # 4xx = permanent, not retried


def test_transient_exhausts_retries(monkeypatch):
    monkeypatch.setenv("LLM_RETRY_BASE", "0")
    monkeypatch.setenv("LLM_MAX_RETRIES", "2")
    c = _client([_StatusError(503), _StatusError(503), _StatusError(503), OK])
    action = parse_action(adapter.call_llm([{"role": "user", "content": "hi"}], client=c))
    assert action["finish_reason"] == "error"
    assert c.calls == 3                  # max_retries + 1; never reaches OK


def test_retry_on_timeout_named_error(monkeypatch):
    monkeypatch.setenv("LLM_RETRY_BASE", "0")
    monkeypatch.setenv("LLM_MAX_RETRIES", "2")

    class APITimeoutError(Exception):
        pass

    c = _client([APITimeoutError("slow"), OK])
    out = adapter.call_llm([{"role": "user", "content": "hi"}], client=c)
    assert out == OK and c.calls == 2


def test_429_is_transient(monkeypatch):
    monkeypatch.setenv("LLM_RETRY_BASE", "0")
    monkeypatch.setenv("LLM_MAX_RETRIES", "1")
    c = _client([_StatusError(429), OK])
    out = adapter.call_llm([{"role": "user", "content": "hi"}], client=c)
    assert out == OK and c.calls == 2
