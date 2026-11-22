"""Memory (Phase 8): short-term (Redis) and long-term (customer_memory) facades.

These facades are the only writers of ``customer_memory`` and every note passes ``scrub()`` first.
"""
