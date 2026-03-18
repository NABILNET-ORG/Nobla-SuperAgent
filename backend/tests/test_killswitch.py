import pytest
from nobla.security.killswitch import KillSwitch, KillState


@pytest.fixture
def ks():
    return KillSwitch()


def test_initial_state(ks):
    assert ks.state == KillState.RUNNING


@pytest.mark.asyncio
async def test_soft_kill(ks):
    await ks.soft_kill()
    assert ks.state == KillState.SOFT_KILLING


@pytest.mark.asyncio
async def test_hard_kill(ks):
    await ks.hard_kill()
    assert ks.state == KillState.KILLED


@pytest.mark.asyncio
async def test_resume(ks):
    await ks.hard_kill()
    assert ks.state == KillState.KILLED
    await ks.resume()
    assert ks.state == KillState.RUNNING


def test_is_accepting_requests(ks):
    assert ks.is_accepting_requests is True


@pytest.mark.asyncio
async def test_killed_not_accepting(ks):
    await ks.hard_kill()
    assert ks.is_accepting_requests is False


@pytest.mark.asyncio
async def test_double_kill_triggers_hard(ks):
    await ks.soft_kill()
    assert ks.state == KillState.SOFT_KILLING
    await ks.soft_kill()  # second call during soft = hard kill
    assert ks.state == KillState.KILLED
