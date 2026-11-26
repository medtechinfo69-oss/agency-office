"""Request-driven, persisted orchestration for Vercel.

No background coroutine survives a request or waits for approval. The browser
advances one bounded step at a time; DB leases prevent duplicate concurrent work.
Scheduled/unattended operation still requires an external durable worker.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import time
import uuid

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from . import db, orchestration as orch
from .events import bus

router = APIRouter(prefix='/api')


def enabled(): return os.getenv('VERCEL') == '1'


def enqueue(pid, text):
    job = db.one('SELECT * FROM cloud_runs WHERE project_id=?', (pid,))
    if job and job['lease_until'] > time.time():
        db.add_memory('project', pid, text, 'preference')
        return
    if job and (job['phase'] == 'tasks' or
                (job['phase'] in ('blocked', 'paused') and job['resume_phase'] == 'tasks')):
        db.execute("UPDATE tasks SET status='todo', description=description || ?, updated_at=? WHERE project_id=? AND status IN ('blocked','progress','rejected')",
                   ('\nBoss guidance: ' + text, db.now(), pid))
        db.execute("UPDATE cloud_runs SET phase='tasks', error='', lease_until=0 WHERE project_id=?", (pid,))
        orch.bump_project(pid, status='running')
        return
    project = db.one('SELECT brief FROM projects WHERE id=?', (pid,))
    brief = (project['brief'] or '') + '\nBoss update: ' + text
    db.execute("INSERT INTO cloud_runs(project_id,phase,brief,updated_at) VALUES(?,'planning',?,?) "
               "ON CONFLICT(project_id) DO UPDATE SET phase='planning', brief=excluded.brief, plan='{}', error='', lease_until=0, updated_at=excluded.updated_at",
               (pid, brief, db.now()))
    orch.bump_project(pid, status='planning', brief=brief)


def _tasks(pid, plan):
    mapping = {}
    for i, task in enumerate(plan.get('tasks', [])):
        task['_row_id'] = task.get('_row_id') or 'task_' + hashlib.sha256((pid + db.jdump(plan.get('summary')) + str(i) + db.jdump(task)).encode()).hexdigest()[:20]
        mapping[str(task.get('id', i))] = task['_row_id']
    for task in plan.get('tasks', []):
        depends = [mapping[str(d)] for d in task.get('depends', []) if str(d) in mapping]
        db.execute("INSERT INTO tasks(id,project_id,title,description,assignee,status,depends,acceptance,created_at,updated_at) "
                   "VALUES(?,?,?,?,?,'todo',?,?,?,?) ON CONFLICT(id) DO NOTHING",
                   (task['_row_id'], pid, task.get('title', 'Task'), task.get('description', ''), task.get('assignee', 'nora'),
                    db.jdump(depends), db.jdump(task.get('acceptance', [])), db.now(), db.now()))
        orch.emit('task', orch._task_row(task['_row_id']), pid)
    db.execute("UPDATE cloud_runs SET phase='tasks',resume_phase='tasks',plan=?,error='' WHERE project_id=?", (db.jdump(plan), pid))
    orch.bump_project(pid, status='running')


def approve(pid, kind, approved, comment=''):
    job = db.one('SELECT * FROM cloud_runs WHERE project_id=?', (pid,))
    if not job: return False
    if kind == 'plan' and job['phase'] == 'awaiting_plan':
        if approved: _tasks(pid, db.jload(job['plan'], {}))
        else:
            db.execute("UPDATE cloud_runs SET phase='planning',brief=brief || ?,error='' WHERE project_id=?",
                       ('\nPlan revision requested: ' + comment, pid))
            orch.bump_project(pid, status='planning')
        return True
    if kind == 'deliverable' and job['phase'] == 'awaiting_delivery':
        if approved:
            db.execute("UPDATE deliverables SET status='approved' WHERE project_id=?", (pid,))
            db.execute("UPDATE cloud_runs SET phase='done' WHERE project_id=?", (pid,))
            orch.bump_project(pid, status='delivered', progress=100)
            orch.emit('delivered', {'package': db.jload(job['plan'], {})}, pid)
        else:
            ids = {t['_row_id'] for t in db.jload(job['plan'], {}).get('tasks', [])}
            for tid in ids:
                db.execute("UPDATE tasks SET status='todo',description=description || ? WHERE id=?",
                           ('\nDelivery revision requested: ' + comment, tid))
            db.execute("UPDATE cloud_runs SET phase='tasks' WHERE project_id=?", (pid,))
            orch.bump_project(pid, status='running')
        return True
    return False


def control(pid, action):
    job = db.one('SELECT * FROM cloud_runs WHERE project_id=?', (pid,))
    if not job: return False
    if action == 'pause' and job['phase'] in ('planning', 'tasks'):
        db.execute("UPDATE cloud_runs SET resume_phase=phase,phase='paused' WHERE project_id=?", (pid,))
    elif action == 'resume' and job['phase'] in ('paused', 'blocked'):
        if job['phase'] == 'blocked':
            db.execute("UPDATE tasks SET status='todo' WHERE project_id=? AND status IN ('progress','blocked','rejected')", (pid,))
        db.execute("UPDATE cloud_runs SET phase=resume_phase,error='' WHERE project_id=?", (pid,))
        orch.bump_project(pid, status='running' if job['resume_phase'] == 'tasks' else 'planning')
    elif action == 'stop':
        db.execute("UPDATE cloud_runs SET phase='stopped' WHERE project_id=?", (pid,))
        orch.bump_project(pid, status='stopped')
    else: return False
    orch.emit('control', {'action': action}, pid)
    return True


async def _step(job):
    pid = job['project_id']
    run = orch.RunControl(project_id=pid)
    if job['phase'] == 'planning':
        plan = await orch.manager_plan(run, job['brief'])
        if not isinstance(plan.get('tasks'), list) or not plan['tasks']:
            raise RuntimeError('The provider returned no actionable tasks. Review the brief and Resume or send guidance to retry planning.')
        if db.one('SELECT phase FROM cloud_runs WHERE project_id=?', (pid,))['phase'] != 'planning': return
        db.execute("UPDATE cloud_runs SET plan=?,phase='awaiting_plan',resume_phase='planning' WHERE project_id=?", (db.jdump(plan), pid))
        if db.kv_get('auto_approve', '0') == '1': _tasks(pid, plan)
        else: orch.emit('approval_required', {'kind': 'plan', 'plan': plan}, pid)
        return
    plan = db.jload(job['plan'], {})
    task_ids = {t['_row_id'] for t in plan.get('tasks', [])}
    tasks = [dict(t) for t in db.query('SELECT * FROM tasks WHERE project_id=? ORDER BY created_at', (pid,)) if t['id'] in task_ids]
    done = {t['id'] for t in tasks if t['status'] == 'done'}
    unfinished = [t for t in tasks if t['id'] not in done]
    if unfinished:
        # A previous process ended mid-step. Do not silently duplicate AI charges.
        if any(t['status'] in ('progress', 'blocked', 'rejected') for t in unfinished):
            raise RuntimeError('A task needs review or was interrupted. Send guidance or use Resume to retry explicitly.')
        ready = [t for t in unfinished if all(d in done for d in db.jload(t['depends'], []))]
        if not ready: raise RuntimeError('Task dependencies are blocked. Review the plan before retrying.')
        task = ready[0]
        task['acceptance'] = db.jload(task['acceptance'], [])
        run.approved_plan = True
        await orch.execute_task(run, task)
        status = db.one('SELECT status FROM tasks WHERE id=?', (task['id'],))['status']
        if status != 'done': raise RuntimeError('Task could not pass QA or its provider failed. Check the activity log, then send guidance or Resume.')
        return
    if db.one('SELECT phase FROM cloud_runs WHERE project_id=?', (pid,))['phase'] != 'tasks': return
    package = {'summary': plan.get('summary', ''), 'tasks_total': len(tasks), 'tasks_done': len(done),
               'notes': 'Review the persisted task outputs before approving delivery.'}
    package_id = 'pkg_' + pid
    db.execute("INSERT INTO deliverables(id,project_id,kind,title,data,status,created_at,updated_at) VALUES(?,?,'package','Final delivery package',?,'pending',?,?) "
               "ON CONFLICT(id) DO UPDATE SET data=excluded.data,status='pending',updated_at=excluded.updated_at",
               (package_id, pid, db.jdump(package), db.now(), db.now()))
    db.execute("UPDATE cloud_runs SET phase='awaiting_delivery' WHERE project_id=? AND phase='tasks'", (pid,))
    orch.bump_project(pid, status='review')
    if db.kv_get('auto_approve', '0') == '1': approve(pid, 'deliverable', True)
    else: orch.emit('approval_required', {'kind': 'deliverable', 'package': package}, pid)


class Advance(BaseModel):
    project_id: str


@router.post('/jobs/advance')
async def advance(body: Advance):
    if not enabled(): raise HTTPException(404)
    pid, token, now = body.project_id, uuid.uuid4().hex, time.time()
    job = db.one("UPDATE cloud_runs SET lease_until=?,lease_token=?,updated_at=? "
                 "WHERE project_id=? AND phase IN ('planning','tasks') AND lease_until<? RETURNING *",
                 (now + 270, token, now, pid, now))
    if not job: return {'advanced': False}
    try:
        await asyncio.wait_for(_step(dict(job)), timeout=240)
        return {'advanced': True}
    except Exception as error:
        from .provider import ProviderError
        message = error.friendly() if isinstance(error, ProviderError) else (
            str(error) if isinstance(error, RuntimeError) else 'The cloud step failed or reached its time limit. Review activity and explicitly retry with Resume.')
        db.execute("UPDATE cloud_runs SET resume_phase=?,phase='blocked',error=? WHERE project_id=? AND lease_token=? AND phase IN ('planning','tasks')",
                   (job['phase'], message, pid, token))
        orch.bump_project(pid, status='error')
        db.log_activity(message, 'error', pid)
        orch.emit('log', {'level': 'error', 'text': message}, pid)
        return {'advanced': False, 'error': message}
    finally:
        db.execute('UPDATE cloud_runs SET lease_until=0 WHERE project_id=? AND lease_token=?', (pid, token))
        db.execute('DELETE FROM cloud_events WHERE created_at<?', (time.time() - 86400,))


@router.get('/events')
def events(after: int = Query(0, ge=0)):
    if not enabled(): raise HTTPException(404)
    if after:
        rows = db.query('SELECT id,payload FROM cloud_events WHERE id>? ORDER BY id LIMIT 200', (after,))
    else:
        rows = list(reversed(db.query('SELECT id,payload FROM cloud_events ORDER BY id DESC LIMIT 100')))
    output = [db.jload(r['payload'], {}) for r in rows]
    if not after:
        output = [event for event in output if event.get('type') not in ('approval_required', 'plan_ready', 'escalation')]
    # Initial state comes from normal API reads; never replay stale UI snapshots.
    if not after:
        output = [event for event in output if event.get('type') not in ('task', 'project', 'progress', 'agent_state', 'cost', 'control')]
    if not after:
        # Rehydrate human approval gates after a refresh, not only from events.
        for job in db.query("SELECT * FROM cloud_runs WHERE phase IN ('awaiting_plan','awaiting_delivery')"):
            plan = db.jload(job['plan'], {})
            output.append({'type': 'approval_required', 'project_id': job['project_id'], 'data':
                {'kind': 'plan', 'plan': plan} if job['phase'] == 'awaiting_plan' else {'kind': 'deliverable', 'package': {'summary': plan.get('summary', '')}}})
    work = db.query("SELECT project_id FROM cloud_runs WHERE phase IN ('planning','tasks') AND lease_until<? ORDER BY updated_at LIMIT 3", (time.time(),))
    return {'events': output, 'cursor': rows[-1]['id'] if rows else after, 'work': [r['project_id'] for r in work],
            'transport': 'poll', 'unattended_jobs': False}
