"""The harness forces offline settings so no test can reach a real service."""

from app.core.config import get_settings


def test_settings_are_offline():
    s = get_settings()
    assert s.demo_mode is True
    assert s.llm_provider == "fake"
    assert s.vector_store == "memory"
    assert s.uses_fake_redis
    assert s.checkpoint_db_path == ":memory:"
