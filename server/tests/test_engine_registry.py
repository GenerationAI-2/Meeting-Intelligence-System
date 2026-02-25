"""Tests for EngineRegistry — thread-safe lazy engine cache.

Covers:
- Lazy engine creation (starts at 0)
- Cache hit (same engine returned for same db)
- Multiple databases (separate engines)
- dispose_all clears all engines
- Thread safety (concurrent get_engine calls)
"""
import sys
import os
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import patch, MagicMock
from src.database import EngineRegistry


def _make_registry():
    """Create an EngineRegistry with mocked engine creation."""
    return EngineRegistry(sql_server="test-server.database.windows.net")


class TestLazyCreation:

    @patch.object(EngineRegistry, '_create_engine', return_value=MagicMock())
    def test_starts_empty(self, mock_create):
        reg = _make_registry()
        assert reg.engine_count == 0
        mock_create.assert_not_called()

    @patch.object(EngineRegistry, '_create_engine', return_value=MagicMock())
    def test_first_get_creates_engine(self, mock_create):
        reg = _make_registry()
        eng = reg.get_engine("db_a")
        assert reg.engine_count == 1
        assert eng is not None
        mock_create.assert_called_once_with("db_a")


class TestCacheHit:

    @patch.object(EngineRegistry, '_create_engine', return_value=MagicMock())
    def test_same_db_returns_same_engine(self, mock_create):
        reg = _make_registry()
        eng1 = reg.get_engine("db_a")
        eng2 = reg.get_engine("db_a")
        assert eng1 is eng2
        assert reg.engine_count == 1
        mock_create.assert_called_once()

    @patch.object(EngineRegistry, '_create_engine')
    def test_different_dbs_create_separate_engines(self, mock_create):
        engine_a = MagicMock()
        engine_b = MagicMock()
        mock_create.side_effect = [engine_a, engine_b]

        reg = _make_registry()
        a = reg.get_engine("db_a")
        b = reg.get_engine("db_b")

        assert a is engine_a
        assert b is engine_b
        assert reg.engine_count == 2
        assert mock_create.call_count == 2


class TestDisposeAll:

    @patch.object(EngineRegistry, '_create_engine')
    def test_dispose_all_clears_engines(self, mock_create):
        engine_a = MagicMock()
        engine_b = MagicMock()
        mock_create.side_effect = [engine_a, engine_b]

        reg = _make_registry()
        reg.get_engine("db_a")
        reg.get_engine("db_b")
        assert reg.engine_count == 2

        reg.dispose_all()

        assert reg.engine_count == 0
        engine_a.dispose.assert_called_once()
        engine_b.dispose.assert_called_once()

    @patch.object(EngineRegistry, '_create_engine', return_value=MagicMock())
    def test_dispose_all_on_empty_is_noop(self, mock_create):
        reg = _make_registry()
        reg.dispose_all()  # should not raise
        assert reg.engine_count == 0


class TestThreadSafety:

    @patch.object(EngineRegistry, '_create_engine')
    def test_concurrent_get_creates_one_engine(self, mock_create):
        """Multiple threads calling get_engine for the same DB should only create 1 engine."""
        engine = MagicMock()
        mock_create.return_value = engine

        reg = _make_registry()
        results = []
        errors = []

        def worker():
            try:
                eng = reg.get_engine("db_a")
                results.append(eng)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 10
        # All threads should get the same engine object
        assert all(r is engine for r in results)
        assert reg.engine_count == 1
        # create_engine should only be called once
        mock_create.assert_called_once_with("db_a")
