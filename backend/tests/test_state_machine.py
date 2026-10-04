import itertools

import pytest

from app.core.errors import InvalidTransition
from app.models import TokenStatus as S
from app.services.state_machine import ALLOWED, assert_transition, can_transition


def test_every_state_is_defined():
    assert set(ALLOWED) == set(S)


def test_happy_path():
    for a, b in [(S.WAITING, S.CALLED), (S.CALLED, S.IN_SERVICE), (S.IN_SERVICE, S.COMPLETED)]:
        assert can_transition(a, b)


def test_completed_is_terminal():
    for target in S:
        assert not can_transition(S.COMPLETED, target)


def test_cannot_skip_steps():
    assert not can_transition(S.WAITING, S.IN_SERVICE)
    assert not can_transition(S.WAITING, S.COMPLETED)
    assert not can_transition(S.CALLED, S.COMPLETED)


def test_recall_paths():
    assert can_transition(S.NO_SHOW, S.WAITING)
    assert can_transition(S.SKIPPED, S.WAITING)


def test_invalid_raises_with_message():
    with pytest.raises(InvalidTransition) as e:
        assert_transition(S.COMPLETED, S.WAITING)
    assert "completed" in e.value.message


def test_matrix_matches_allowed():
    for a, b in itertools.product(S, S):
        assert can_transition(a, b) == (b in ALLOWED[a])
