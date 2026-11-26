/* Shop — dress the crew: agent chips, big preview, character cards
   (Current / Worn by X / Available), category tabs, Apply + undo/redo. */
import { useMemo, useState } from 'react'
import { Undo2, Redo2, Check } from 'lucide-react'
import { AgentBot, CHARACTER_IDS } from '../components/Characters'
import { Card, StatusPill, Segmented, Empty } from '../components/ui'
import { api } from '../api'

const TABS = ['Furniture', 'Decoration', 'Characters', 'Colours', 'Accessories', 'Themes']

const CATALOG = {
  Furniture: [
    { id: 'desk-oak', name: 'Oak standing desk', price: 120, icon: '🪵' },
    { id: 'chair-cloud', name: 'Cloud chair', price: 90, icon: '🪑' },
    { id: 'sofa-moss', name: 'Moss sofa', price: 240, icon: '🛋️' },
    { id: 'rack-mini', name: 'Mini server rack', price: 400, icon: '🗄️' },
  ],
  Decoration: [
    { id: 'plant-fiddle', name: 'Fiddle-leaf fig', price: 45, icon: '🪴' },
    { id: 'poster-grid', name: 'Grid poster', price: 30, icon: '🖼️' },
    { id: 'lamp-arc', name: 'Arc lamp', price: 80, icon: '💡' },
    { id: 'rug-round', name: 'Round rug', price: 70, icon: '🧶' },
  ],
  Accessories: [
    { id: 'acc-headphones', name: 'Indigo headphones', price: 25, icon: '🎧' },
    { id: 'acc-badge', name: 'ID badge', price: 10, icon: '🪪' },
    { id: 'acc-visor', name: 'Futuristic visor', price: 35, icon: '🥽' },
    { id: 'acc-tie', name: 'Tiny tie', price: 15, icon: '👔' },
  ],
  Themes: [
    { id: 'theme-ocean', name: 'Ocean office', price: 150, icon: '🌊' },
    { id: 'theme-sunset', name: 'Sunset studio', price: 150, icon: '🌅' },
    { id: 'theme-matrix', name: 'Terminal green', price: 200, icon: '🖥️' },
  ],
  Colours: [
    { id: '#4f46e5', name: 'Indigo', price: 0, icon: '🟦' },
    { id: '#0d9488', name: 'Teal', price: 0, icon: '🟩' },
    { id: '#db2777', name: 'Pink', price: 0, icon: '🟪' },
    { id: '#ea580c', name: 'Orange', price: 0, icon: '🟧' },
    { id: '#7c3aed', name: 'Purple', price: 0, icon: '🟪' },
    { id: '#0f172a', name: 'Ink', price: 0, icon: '⬛' },
  ],
  Characters: [], // built from CHARACTER_IDS
}

const CHAR_INFO = {
  manager: { name: 'Manager Bot', price: 0, rarity: 'Core', desc: 'Headphones + badge. Runs the floor.' },
  designer: { name: 'Cat Bot', price: 150, rarity: 'Rare', desc: 'Fox ears, whisker sensors, taste.' },
  developer: { name: 'Tracked Bot', price: 150, rarity: 'Rare', desc: 'Tank treads, riveted hull, ships code.' },
  owl: { name: 'Night Owl', price: 120, rarity: 'Epic', desc: 'Wise eyes. Works the late shift.' },
  penguin: { name: 'Tux Bot', price: 90, rarity: 'Common', desc: 'Formal, calm, always on time.' },
  blob: { name: 'Blob Bot', price: 60, rarity: 'Common', desc: 'Squishy intern energy.' },
  astronaut: { name: 'Astro Bot', price: 260, rarity: 'Legendary', desc: 'For out-of-this-world campaigns.' },
}

export default function ShopPage({ t, agents, onRefresh }) {
  const [agentId, setAgentId] = useState(agents[0]?.id || 'nora')
  const [tab, setTab] = useState('Characters')
  const [sel, setSel] = useState(null)          // pending selection
  const [history, setHistory] = useState([])    // undo stack
  const [future, setFuture] = useState([])      // redo stack
  const [saved, setSaved] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const agent = agents.find((a) => a.id === agentId) || agents[0]
  const outfit = agent?.custom?.outfit || {}
  const current = { char: outfit.char || agentId, color: outfit.color, acc: outfit.acc }

  const wornBy = (charId) =>
    agents.find((a) => (a.custom?.outfit?.char || a.id) === charId && a.id !== agentId)

  const preview = sel && tab === 'Characters'
    ? { char: sel, color: current.color }
    : { char: current.char, color: sel && tab === 'Colours' ? sel : current.color }

  const persist = async (next, afterSave) => {
    if (!agent || busy) return
    setBusy(true); setError('')
    try {
      await api.updateAgent(agent.id, { custom: { ...(agent.custom || {}), outfit: next } })
      await onRefresh?.()
      afterSave()
      setSaved(true)
      setTimeout(() => setSaved(false), 2400)
    } catch (e) { setError(`Could not save the outfit. ${e.message} Try again.`) }
    finally { setBusy(false) }
  }

  const apply = () => {
    if (!agent || !sel) return
    const next = { ...outfit }
    if (tab === 'Characters') next.char = sel
    if (tab === 'Colours') next.color = sel
    if (tab === 'Accessories') next.acc = sel
    if (['Furniture', 'Decoration', 'Themes'].includes(tab)) {
      next.furniture = [...new Set([...(next.furniture || []), sel])]
    }
    persist(next, () => {
      setHistory((h) => [...h, outfit]); setFuture([]); setSel(null)
    })
  }

  const undo = () => {
    if (!history.length) return
    persist(history.at(-1), () => {
      setHistory((h) => h.slice(0, -1)); setFuture((f) => [outfit, ...f])
    })
  }
  const redo = () => {
    if (!future.length) return
    persist(future[0], () => {
      setFuture((f) => f.slice(1)); setHistory((h) => [...h, outfit])
    })
  }

  const items = useMemo(() => {
    if (tab === 'Characters') {
      return CHARACTER_IDS.map((id) => ({ id, ...CHAR_INFO[id] }))
    }
    return CATALOG[tab] || []
  }, [tab])

  if (!agents.length) return <div className="page"><Empty icon="🛒" title="No agents to dress yet" /></div>

  return (
    <div className="page shop-page">
      {error && <div className="feedback-banner error" role="alert">{error}</div>}
      {!['Characters', 'Colours'].includes(tab) && <p className="feedback-banner">Catalog preview: selections are saved, but these items do not change the office scene.</p>}
      {/* agent chips */}
      <div className="shop-agents">
        {agents.map((a) => (
          <button key={a.id}
            className={`agent-chip ${a.id === agentId ? 'on' : ''}`}
            disabled={busy} aria-pressed={a.id === agentId} onClick={() => { setAgentId(a.id); setSel(null); setHistory([]); setFuture([]); setError('') }}>
            <AgentBot agentId={a.custom?.outfit?.char || a.id} size={26} color={a.color} />
            {a.name}
          </button>
        ))}
      </div>

      <div className="shop-grid">
        {/* large preview */}
        <div className="shop-preview card">
          <span className="eyebrow">Preview</span>
          <div className="shop-stage" style={{ '--agent': preview.color || agent.color }}>
            <AgentBot agentId={preview.char} size={200} color={preview.color || agent.color} />
          </div>
          <div className="shop-preview-meta">
            <strong>{agent.name}</strong>
            <span className="mono">{CHAR_INFO[preview.char]?.name || preview.char}</span>
            <StatusPill status={agent.status} />
          </div>
        </div>

        {/* catalog */}
        <div className="shop-catalog card">
          <Segmented ariaLabel="shop category"
            options={TABS.map((x) => ({ id: x, label: x }))} value={tab}
            onChange={(v) => { setTab(v); setSel(null) }} />

          <div className="shop-items">
            {items.map((it) => {
              const worn = tab === 'Characters' ? wornBy(it.id) : null
              const isCurrent = tab === 'Characters' && current.char === it.id
              const owned = ['Furniture', 'Decoration', 'Themes', 'Accessories'].includes(tab) &&
                (outfit.furniture || []).includes(it.id) || (tab === 'Accessories' && current.acc === it.id)
              return (
                <article key={it.id} role="button" tabIndex={0} aria-pressed={sel === it.id} onKeyDown={(e) => { if (['Enter', ' '].includes(e.key)) { e.preventDefault(); setSel(it.id) } }}
                  className={`shop-item card ${sel === it.id ? 'on' : ''} ${isCurrent ? 'current' : ''}`}
                  onClick={() => setSel(it.id)}>
                  <div className="si-cover" style={{ '--agent': agent.color }}>
                    {tab === 'Colours'
                      ? <span className="si-swatch" style={{ background: it.id }} />
                      : <AgentBot agentId={tab === 'Characters' ? it.id : 'round'} size={54} color={tab === 'Colours' ? it.id : agent.color} />}
                  </div>
                  <div className="si-body">
                    <div className="si-title">
                      <span className="mono">{it.name}</span>
                      {isCurrent && <span className="pill pill-indigo">Current</span>}
                      {!isCurrent && worn && <span className="pill">Worn by {worn.name}</span>}
                      {!isCurrent && !worn && !owned && <span className="pill pill-amber">Available</span>}
                      {owned && !isCurrent && <span className="pill pill-green">Owned</span>}
                    </div>
                    <div className="si-foot">
                      <span className="mono si-price">{it.price ? `${it.price} ⌾` : 'free'}</span>
                      <span className="tag mono">{it.rarity || tab.slice(0, -1)}</span>
                    </div>
                  </div>
                </article>
              )
            })}
          </div>

          {/* save bar */}
          <div className="shop-savebar">
            <button className="btn sm" onClick={undo} disabled={busy || !history.length}>
              <Undo2 size={14} /> {t('undo')}
            </button>
            <button className="btn sm" onClick={redo} disabled={busy || !future.length}>
              <Redo2 size={14} /> {t('redo')}
            </button>
            <span role="status" className={`save-flash ${saved ? 'on' : ''}`}>✔ {t('saved')}</span>
            <span className="spacer" />
            <button className="btn primary" onClick={apply} disabled={busy || !sel} aria-busy={busy}>
              <Check size={14} /> {busy ? 'Saving…' : t('apply')}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
