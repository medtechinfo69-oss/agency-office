/* Logs — project activity stream with level filters + mono timestamps. */
import { useMemo, useState } from 'react'
import { Search, RefreshCw } from 'lucide-react'
import { Empty, Segmented } from '../components/ui'

export default function LogsPage({ t, log, onRefresh }) {
  const [q, setQ] = useState('')
  const [lvl, setLvl] = useState('all')

  const rows = useMemo(() => {
    let list = [...log].reverse()
    if (lvl !== 'all') list = list.filter((l) => (l.level || 'info') === lvl)
    if (q.trim()) list = list.filter((l) => (l.text || '').toLowerCase().includes(q.toLowerCase()))
    return list
  }, [log, q, lvl])

  return (
    <div className="page logs-page">
      <div className="logs-bar">
        <label className="search-box">
          <Search size={14} />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter events…" />
        </label>
        <Segmented ariaLabel="level"
          options={[
            { id: 'all', label: 'All' }, { id: 'info', label: 'Info' },
            { id: 'success', label: 'OK' }, { id: 'warn', label: 'Warn' },
            { id: 'error', label: 'Error' },
          ]}
          value={lvl} onChange={setLvl} />
        <span className="spacer" />
        <button className="btn sm" onClick={onRefresh}><RefreshCw size={13} /> {t('refresh')}</button>
      </div>

      <div className="logs-list card">
        {rows.length === 0 && <Empty icon="📜" title="No log entries" hint="Events from the crew appear here live." />}
        {rows.map((l, i) => (
          <div key={i} className={`log-row lvl-${l.level || 'info'}`}>
            <span className="log-level mono">{(l.level || 'info').toUpperCase()}</span>
            <span className="log-text">{l.text}</span>
            <time className="mono log-time">
              {l.created_at
                ? new Date(l.created_at * 1000).toLocaleString([], {
                  month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
                })
                : '—'}
            </time>
          </div>
        ))}
      </div>
    </div>
  )
}
