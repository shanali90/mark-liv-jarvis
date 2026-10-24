import pytest
from core.db import _cosine


def test_cosine_identical_vectors():
    a = [1.0, 2.0, 3.0]
    b = [1.0, 2.0, 3.0]
    sim = _cosine(a, b)
    assert sim is not None
    assert pytest.approx(sim, 0.0001) == 1.0


def test_cosine_orthogonal_vectors():
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    sim = _cosine(a, b)
    assert sim is not None
    assert pytest.approx(sim, 0.0001) == 0.0


def test_cosine_size_mismatch_returns_none():
    a = [1.0, 2.0, 3.0]
    b = [1.0, 2.0]
    assert _cosine(a, b) is None


def test_cosine_zero_norm_returns_none():
    a = [0.0, 0.0, 0.0]
    b = [1.0, 2.0, 3.0]
    assert _cosine(a, b) is None
    assert _cosine(None, b) is None
