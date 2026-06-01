# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.
"""Unit tests for the knowledge-gap pull signal model and emitter."""
from __future__ import annotations

import pytest

import gap_signal as gs


def test_gap_signal_model_defaults():
    sig = gs.GapSignal(
        query="What are payment terms for FOB barley to Japan?",
        topic_needed="payment_terms",
        jurisdiction_needed="Japan",
        gap_description="No FOB barley payment-term reference for Japan corridor.",
    )
    assert sig.metadata == {}
    assert sig.topic_needed == "payment_terms"


class _FakeCursor:
    def __init__(self, store):
        self._store = store

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params):
        self._store["sql"] = sql
        self._store["params"] = params

    def fetchone(self):
        return ("00000000-0000-0000-0000-000000000abc",)


class _FakeConn:
    def __init__(self):
        self.store = {}
        self.committed = False

    def cursor(self):
        return _FakeCursor(self.store)

    def commit(self):
        self.committed = True


def test_emit_gap_signal_inserts_and_returns_id():
    conn = _FakeConn()
    sig = gs.GapSignal(
        query="q", topic_needed="insurance", jurisdiction_needed="UK",
        gap_description="missing insurance terms", metadata={"k": "v"},
    )
    new_id = gs.emit_gap_signal(sig, conn)
    assert new_id == "00000000-0000-0000-0000-000000000abc"
    assert conn.committed is True
    # The query is parameterised (no string interpolation of user input).
    assert "knowledge_gap_signals" in conn.store["sql"]
    assert conn.store["params"]["query"] == "q"
    assert conn.store["params"]["topic_needed"] == "insurance"
    # metadata is JSONB-wrapped for psycopg.
    assert type(conn.store["params"]["metadata"]).__name__ == "Jsonb"
