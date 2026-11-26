/* Page header: bold title + question subtitle · right: provider pill,
   green Live pill, monospace clock. */
export default function TopBar({ title, question, live, clock, provider, demo, right }) {
  return (
    <header className="topbar">
      <div className="topbar-title">
        <h1>{title}</h1>
        <p>{question}</p>
      </div>
      <div className="topbar-right">
        {right}
        {provider !== undefined && (
          <span className={`provider-pill ${demo ? 'demo' : ''}`}
            title={demo ? 'Demo provider' : provider}>
            {demo ? '🧪 DEMO' : provider}
          </span>
        )}
        <span className="live-badge" title={live ? 'Connected' : 'Reconnecting…'}>
          <span className={`live-dot ${live ? 'on' : ''}`} />
          Live
        </span>
        <span className="clock mono">{clock}</span>
      </div>
    </header>
  )
}
