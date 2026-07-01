import pytest
from backend.providers.registry import Registry
from backend.providers.base import ProviderError


class FakeProvider:
    def __init__(self, prefix): self.prefix = prefix
    def is_up(self, timeout=2): return True
    def search(self, k, l): return []
    def search_split(self, k, l, t): return [], []
    def resolve_pending(self, p, max_n): yield from ()


def test_register_and_get():
    r = Registry()
    p = FakeProvider("ncm")
    r.register(p)
    assert r.get("ncm") is p
    assert r.list() == ["ncm"]


def test_resolve_by_id_prefix():
    r = Registry()
    p = FakeProvider("ncm")
    r.register(p)
    assert r.resolve("ncm:123") is p


def test_get_unknown_prefix_raises_not_found():
    r = Registry()
    with pytest.raises(ProviderError) as ei:
        r.get("qq")
    assert ei.value.code == "NOT_FOUND"


def test_duplicate_prefix_raises():
    r = Registry()
    r.register(FakeProvider("ncm"))
    with pytest.raises(ValueError):
        r.register(FakeProvider("ncm"))
