from core.single_instance import run_with_named_mutex, ERROR_ALREADY_EXISTS


class FakeKernel32:
    def __init__(self, existing: bool = False):
        self.existing = existing
        self.created = False
        self.closed = False
        self.released = False

    def CreateMutexW(self, sec, initial_owner, name):
        self.created = True
        return 12345

    def get_last_error(self):
        return ERROR_ALREADY_EXISTS if self.existing else 0

    def CloseHandle(self, handle):
        self.closed = True
        return True

    def ReleaseMutex(self, handle):
        self.released = True
        return True


def test_first_instance_runs_and_cleans_up():
    api = FakeKernel32(existing=False)
    ran = False

    def runner():
        nonlocal ran
        ran = True
        return 42

    code = run_with_named_mutex("TEST_MUTEX", runner, api=api)
    assert ran is True
    assert code == 42
    assert api.created is True
    assert api.released is True
    assert api.closed is True


def test_second_instance_exits_quietly_zero():
    api = FakeKernel32(existing=True)
    ran = False

    def runner():
        nonlocal ran
        ran = True
        return 1

    code = run_with_named_mutex("TEST_MUTEX", runner, api=api)
    assert ran is False
    assert code == 0
    assert api.created is True
    assert api.closed is True
    assert api.released is False
