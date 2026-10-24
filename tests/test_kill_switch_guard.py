from actions.send_message import (
    abort_current_action,
    reset_action_abort,
    is_action_aborted,
    is_action_pending,
    set_action_pending,
)


def test_kill_switch_only_aborts_when_action_is_pending():
    reset_action_abort()
    set_action_pending(False)

    # Calling abort when nothing is pending should NOT trip the abort event
    aborted = abort_current_action()
    assert aborted is False
    assert is_action_aborted() is False

    # Now mark action pending
    set_action_pending(True)
    assert is_action_pending() is True

    aborted = abort_current_action()
    assert aborted is True
    assert is_action_aborted() is True

    # Reset
    reset_action_abort()
    assert is_action_aborted() is False
    set_action_pending(False)
