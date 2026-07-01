import pytest
from backend.providers import base


def test_pack_unpack_roundtrip():
    tid = base.pack_id("ncm", 123)
    assert tid == "ncm:123"
    assert base.unpack_id(tid) == ("ncm", "123")


def test_unpack_without_prefix_raises():
    with pytest.raises(ValueError):
        base.unpack_id("123")


def test_normalize_track_shape_and_prefixed_id():
    x = {"id": 7, "name": "A", "ar": [{"name": "x"}], "al": {"name": "Al", "picUrl": "c"}, "dt": 1000}
    t = base.normalize_track("ncm", x, "http://u", unlocked=True, source="")
    assert t["id"] == "ncm:7"
    assert t["name"] == "A" and t["artist"] == "x" and t["album"] == "Al"
    assert t["cover"] == "c" and t["duration"] == 1000
    assert t["url"] == "http://u" and t["unlocked"] is True and t["source"] == ""


def test_provider_error_attrs():
    e = base.ProviderError("NETWORK", "netease-enhanced", "boom")
    assert e.code == "NETWORK" and e.provider_id == "netease-enhanced"
    assert "boom" in str(e)
