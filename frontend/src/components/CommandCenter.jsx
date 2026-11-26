import { useEffect, useMemo, useState } from 'react'
import { ArrowRight, Keyboard, Search } from 'lucide-react'
import { Modal, Button, Empty } from './admin-ui'
import { NAV } from './Sidebar'

export default function CommandCenter({ onNavigate }) {
  const [open, setOpen] = useState('')
  const [query, setQuery] = useState('')
  useEffect(() => {
    const key = (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setOpen((v) => v ? '' : 'search') } if (e.key === '?' && !['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName)) setOpen('shortcuts') }
    const show = () => setOpen('search'), shortcuts = () => setOpen('shortcuts')
    window.addEventListener('keydown', key); window.addEventListener('agency:search', show); window.addEventListener('agency:shortcuts', shortcuts)
    return () => { window.removeEventListener('keydown', key); window.removeEventListener('agency:search', show); window.removeEventListener('agency:shortcuts', shortcuts) }
  }, [])
  const items = useMemo(() => NAV.filter((item) => item.label.toLowerCase().includes(query.toLowerCase())), [query])
  return open && <Modal title={open === 'search' ? 'Go anywhere' : 'Keyboard shortcuts'} onClose={() => setOpen('')}>
    {open === 'search' ? <><label className="a-search a-command-search"><Search size={18} /><input autoFocus aria-label="Search pages" placeholder="Search pages…" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && items[0]) { onNavigate(items[0].id); setOpen('') } if (e.key === 'ArrowDown') { e.preventDefault(); document.querySelector('.a-command-list button')?.focus() } }} /></label><div className="a-command-list" onKeyDown={(e) => { if (!['ArrowDown','ArrowUp'].includes(e.key)) return; e.preventDefault(); const buttons=[...e.currentTarget.querySelectorAll('button')]; const i=buttons.indexOf(document.activeElement); buttons[(i+(e.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length]?.focus() }}>{items.map(({ id, label, Icon }) => <Button key={id} variant="ghost" onClick={() => { onNavigate(id); setOpen('') }}><Icon size={18} />{label}<ArrowRight size={14} /></Button>)}{!items.length && <Empty title="No matching page" description="Try Builder, Connections, or Users." />}</div></> : <dl className="a-definition"><dt><Keyboard size={16} />Global search</dt><dd>Ctrl / ⌘ K</dd><dt>Show shortcuts</dt><dd>?</dd><dt>Generate in Builder</dt><dd>Ctrl / ⌘ Enter</dd><dt>Undo / redo in Builder</dt><dd>Ctrl / ⌘ Z / Shift Z</dd><dt>Close overlay</dt><dd>Escape</dd></dl>}
  </Modal>
}
