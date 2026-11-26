"""No live providers. Serverless checkpoints/leases use an isolated SQLite DB."""
import os
import sys
import time
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import db, cloud, agents
from app.config import settings


@pytest.fixture
def office(tmp_path, monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.delenv('VERCEL', raising=False)
    monkeypatch.setattr(settings, 'db_path', str(tmp_path / 'cloud.db'))
    monkeypatch.setattr(db, '_conn', None)
    db.get_conn()
    agents.seed_agents()
    db.execute("INSERT INTO projects(id,name,created_at,updated_at) VALUES('p','Test',?,?)", (db.now(), db.now()))
    monkeypatch.setenv('VERCEL', '1')
    yield
    db._conn.close()


def plan():
    return {'summary': 'Test plan', 'tasks': [
        {'id': 'a', 'title': 'First', 'description': 'Do it', 'assignee': 'sami', 'depends': [], 'acceptance': ['Meets brief']},
        {'id': 'b', 'title': 'Second', 'description': 'Next', 'assignee': 'rami', 'depends': ['a'], 'acceptance': []},
    ]}


def test_enqueue_is_durable_and_no_provider_is_started(office):
    cloud.enqueue('p', 'Brief')
    assert db.one('SELECT phase FROM cloud_runs')['phase'] == 'planning'
    assert 'Brief' in db.one('SELECT brief FROM projects')['brief']
    assert cloud.events(after=0)['work'] == ['p']


@pytest.mark.asyncio
async def test_plan_approval_survives_refresh_and_task_dependencies(office, monkeypatch):
    cloud.enqueue('p', 'Brief')
    mocked = AsyncMock(return_value=plan())
    monkeypatch.setattr(cloud.orch, 'manager_plan', mocked)
    assert (await cloud.advance(cloud.Advance(project_id='p')))['advanced']
    job = db.one('SELECT * FROM cloud_runs')
    assert job['phase'] == 'awaiting_plan' and job['lease_until'] == 0
    assert cloud.events(after=0)['work'] == []
    assert any(e['type'] == 'approval_required' for e in cloud.events(after=0)['events'])
    assert cloud.approve('p', 'plan', True)
    tasks = db.query('SELECT * FROM tasks ORDER BY created_at')
    assert len(tasks) == 2
    assert db.jload(tasks[1]['depends']) == [tasks[0]['id']]
    assert db.one('SELECT resume_phase FROM cloud_runs')['resume_phase'] == 'tasks'


@pytest.mark.asyncio
async def test_lease_prevents_concurrent_provider_work(office, monkeypatch):
    cloud.enqueue('p', 'Brief')
    db.execute('UPDATE cloud_runs SET lease_until=?', (time.time() + 200,))
    mocked = AsyncMock()
    monkeypatch.setattr(cloud.orch, 'manager_plan', mocked)
    assert not (await cloud.advance(cloud.Advance(project_id='p')))['advanced']
    mocked.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_provider_blocks_and_explicit_resume_retries(office, monkeypatch):
    cloud.enqueue('p', 'Brief')
    monkeypatch.setattr(cloud.orch, 'manager_plan', AsyncMock(side_effect=ValueError('bad response')))
    result = await cloud.advance(cloud.Advance(project_id='p'))
    assert not result['advanced'] and result['error']
    job = db.one('SELECT * FROM cloud_runs')
    assert job['phase'] == 'blocked' and job['lease_until'] == 0
    assert cloud.events(after=0)['work'] == []
    assert cloud.control('p', 'resume')
    assert db.one('SELECT phase FROM cloud_runs')['phase'] == 'planning'


@pytest.mark.asyncio
async def test_steps_wait_for_dependencies_and_delivery_approval(office, monkeypatch):
    cloud.enqueue('p', 'Brief')
    cloud._tasks('p', plan())
    seen = []
    async def execute(run, task):
        seen.append(task['title'])
        db.execute("UPDATE tasks SET status='done' WHERE id=?", (task['id'],))
    monkeypatch.setattr(cloud.orch, 'execute_task', execute)
    await cloud.advance(cloud.Advance(project_id='p'))
    assert seen == ['First']
    assert not cloud.approve('p', 'deliverable', True)
    await cloud.advance(cloud.Advance(project_id='p'))
    assert seen == ['First', 'Second']
    await cloud.advance(cloud.Advance(project_id='p'))
    assert db.one('SELECT phase FROM cloud_runs')['phase'] == 'awaiting_delivery'
    assert db.one('SELECT status FROM projects')['status'] == 'review'
    assert cloud.approve('p', 'deliverable', True)
    assert db.one('SELECT status FROM projects')['status'] == 'delivered'


@pytest.mark.asyncio
async def test_interrupted_task_requires_explicit_retry_not_duplicate_charge(office, monkeypatch):
    cloud.enqueue('p', 'Brief')
    cloud._tasks('p', plan())
    db.execute("UPDATE tasks SET status='progress' WHERE title='First'")
    mocked = AsyncMock()
    monkeypatch.setattr(cloud.orch, 'execute_task', mocked)
    result = await cloud.advance(cloud.Advance(project_id='p'))
    assert not result['advanced']
    mocked.assert_not_awaited()
    assert cloud.control('p', 'resume')
    assert db.one("SELECT status FROM tasks WHERE title='First'")['status'] == 'todo'


def test_pause_resume_stop_and_revision(office):
    cloud.enqueue('p', 'Brief')
    cloud._tasks('p', plan())
    assert cloud.control('p', 'pause')
    assert cloud.events(after=0)['work'] == []
    assert cloud.control('p', 'resume')
    assert cloud.events(after=0)['work'] == ['p']
    assert cloud.control('p', 'stop')
    assert cloud.events(after=0)['work'] == []
    assert db.one('SELECT status FROM projects')['status'] == 'stopped'


def test_events_are_persisted_ordered_and_cursor_based(office):
    cloud.bus.publish_sync('test', {'value': 1}, 'p')
    first = cloud.events(after=0)
    assert first['events'][-1]['data']['value'] == 1
    cloud.bus.publish_sync('test', {'value': 2}, 'p')
    second = cloud.events(after=first['cursor'])
    assert [e['data']['value'] for e in second['events']] == [2]


def test_refresh_does_not_replay_approved_gate_or_old_task_snapshot(office):
    cloud.enqueue('p', 'Brief')
    cloud.bus.publish_sync('approval_required', {'kind': 'plan', 'plan': plan()}, 'p')
    cloud.bus.publish_sync('task', {'id': 'old', 'status': 'progress'}, 'p')
    initial = cloud.events(after=0)
    assert not any(e['type'] in ('approval_required', 'task') for e in initial['events'])
    db.execute("UPDATE cloud_runs SET phase='awaiting_plan',plan=? WHERE project_id='p'", (db.jdump(plan()),))
    assert any(e['type'] == 'approval_required' for e in cloud.events(after=0)['events'])
