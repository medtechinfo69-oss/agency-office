/* ============================================================
   Isometric office — original layered SVG scene (no pixel art).
   Wood floor, navy walls, desks, plant, coffee, sofa, whiteboard,
   server rack + clay robots at their desks with status bubbles.
   ============================================================ */
import { useEffect, useRef, useState, useCallback } from 'react'
import {
  ZoomIn, ZoomOut, Crosshair, Maximize2, SlidersHorizontal,
} from 'lucide-react'
import { AgentBot } from './Characters'

/* ---------- isometric projection ---------- */
const TW = 36, TH = 18, ZH = 26, OX = 500, OY = 64
const iso = (x, y, z = 0) => [OX + (x - y) * TW, OY + (x + y) * TH - z * ZH]
const pts = (arr) => arr.map((c) => iso(...c).join(',')).join(' ')

/* one extruded box → top / right / left faces */
function Box({ x, y, w, d, h, top, right, left, opacity = 1 }) {
  const topFace = pts([[x, y, h], [x + w, y, h], [x + w, y + d, h], [x, y + d, h]])
  const rightFace = pts([[x + w, y, h], [x + w, y + d, h], [x + w, y + d, 0], [x + w, y, 0]])
  const leftFace = pts([[x, y + d, h], [x + w, y + d, h], [x + w, y + d, 0], [x, y + d, 0]])
  return (
    <g opacity={opacity}>
      <polygon points={leftFace} fill={left} />
      <polygon points={rightFace} fill={right} />
      <polygon points={topFace} fill={top} />
    </g>
  )
}

/* desk + monitor + chair set */
function Workstation({ x, y }) {
  return (
    <g>
      {/* chair (in front of desk) */}
      <Box x={x + 0.55} y={y + 1.5} w={0.9} d={0.8} h={0.35}
        top="#3b4252" right="#2a303d" left="#222733" />
      <Box x={x + 0.55} y={y + 2.1} w={0.9} d={0.18} h={0.85}
        top="#454d61" right="#333a4a" left="#2a303d" />
      {/* desk */}
      <Box x={x} y={y} w={2} d={1.3} h={0.78}
        top="#e7dcc8" right="#c9bda6" left="#b9ad96" />
      {/* legs hint */}
      <Box x={x + 0.1} y={y + 0.15} w={0.18} d={0.18} h={0.78}
        top="#a99d86" right="#94896f" left="#877c64" />
      {/* monitor */}
      <Box x={x + 0.55} y={y + 0.25} w={0.95} d={0.14} h={0.62}
        top="#2b3140" right="#232836" left="#1d2230" />
      <polygon
        points={pts([
          [x + 0.6, y + 0.24, 0.5], [x + 1.45, y + 0.24, 0.5],
          [x + 1.45, y + 0.24, 1.28], [x + 0.6, y + 0.24, 1.28],
        ])}
        fill="#7dd3fc" opacity=".85" className="iso-screen"
      />
      {/* keyboard */}
      <Box x={x + 0.6} y={y + 0.75} w={0.85} d={0.35} h={0.05}
        top="#d7d2c6" right="#bcb6a8" left="#aca694" />
    </g>
  )
}

/* ---------- furniture ---------- */
function Furniture() {
  return (
    <g>
      {/* whiteboard on back-right wall (y=0) */}
      <polygon
        points={pts([[6.4, 0.02, 0.7], [9.6, 0.02, 0.7], [9.6, 0.02, 2.3], [6.4, 0.02, 2.3]])}
        fill="#f4f5f7" stroke="#c9cdd6" strokeWidth="1.5"
      />
      <path
        d={`M ${iso(6.7, 0.02, 1.9)[0]} ${iso(6.7, 0.02, 1.9)[1]}
            L ${iso(7.6, 0.02, 1.2)[0]} ${iso(7.6, 0.02, 1.2)[1]}
            L ${iso(8.3, 0.02, 1.7)[0]} ${iso(8.3, 0.02, 1.7)[1]}
            L ${iso(9.3, 0.02, 1.0)[0]} ${iso(9.3, 0.02, 1.0)[1]}`}
        stroke="#6366f1" strokeWidth="2" fill="none" strokeLinecap="round"
      />
      {/* server rack — back-left corner */}
      <Box x={0.35} y={0.35} w={1.1} d={1.1} h={2.4}
        top="#31384a" right="#262c3b" left="#1f2431" />
      {[0.5, 1.0, 1.5, 2.0].map((z, i) => (
        <g key={i}>
          <polygon
            points={pts([[1.46, 0.5, z], [1.46, 1.3, z], [1.46, 1.3, z + 0.22], [1.46, 0.5, z + 0.22]])}
            fill="#0f1420"
          />
          <circle className="iso-led" cx={iso(1.47, 1.1, z + 0.11)[0]}
            cy={iso(1.47, 1.1, z + 0.11)[1]} r="2.4"
            fill={i % 2 ? '#4ade80' : '#38bdf8'} style={{ animationDelay: `${i * 0.4}s` }} />
        </g>
      ))}
      {/* coffee machine — left wall */}
      <Box x={0.4} y={4.2} w={1} d={1.4} h={1.5}
        top="#8b5a44" right="#714633" left="#5f3a2a" />
      <Box x={0.55} y={4.45} w={0.7} d={0.9} h={0.5}
        top="#2f3542" right="#262b36" left="#20242e" />
      <Box x={0.7} y={5.7} w={0.35} d={0.35} h={0.3}
        top="#f5f5f4" right="#d6d3d1" left="#c2beb9" />
      {/* plant — back right corner */}
      <Box x={12.2} y={0.5} w={0.9} d={0.9} h={0.7}
        top="#c2703f" right="#a35c33" left="#8c4e2b" />
      <circle cx={iso(12.65, 0.95, 1.35)[0]} cy={iso(12.65, 0.95, 1.35)[1] - 8}
        r="17" fill="#2f9e5e" />
      <circle cx={iso(12.3, 0.7, 1.1)[0]} cy={iso(12.3, 0.7, 1.1)[1] - 2}
        r="10" fill="#37b56c" />
      <circle cx={iso(13.0, 1.2, 1.15)[0]} cy={iso(13.0, 1.2, 1.15)[1] - 3}
        r="9" fill="#268a51" />
      {/* sofa — front right */}
      <Box x={10.4} y={7.6} w={2.6} d={1.5} h={0.55}
        top="#6d7ff0" right="#5a6bd8" left="#4d5cc4" />
      <Box x={10.4} y={8.85} w={2.6} d={0.35} h={1.15}
        top="#8292f5" right="#6d7ff0" left="#5a6bd8" />
      <Box x={10.4} y={7.6} w={0.35} d={1.5} h={1.0}
        top="#8292f5" right="#6d7ff0" left="#5a6bd8" />
      {/* rug */}
      <polygon
        points={pts([[9.6, 6.6], [12.8, 6.6], [12.8, 9.6], [9.6, 9.6]])}
        fill="var(--accent-subtle)" opacity=".8"
      />
    </g>
  )
}

/* ---------- agent at desk ---------- */
const STATUS_DOT = {
  working: 'var(--green)', reviewing: 'var(--purple)', thinking: 'var(--purple)',
  waiting: 'var(--amber)', research: 'var(--teal)', idle: '#9aa1ad',
  error: 'var(--red)', blocked: 'var(--red)',
}

function AgentAtDesk({ agent, x, y, picked, onPick, speed }) {
  const [sx, sy] = iso(x + 1, y + 2.05, 0)
  const st = agent.status || 'idle'
  const bubble = st === 'idle' ? 'zZz' : st === 'waiting' ? '?' :
    (st === 'thinking' || st === 'reviewing') ? '…' : ''
  return (
    <g
      className={`iso-agent ${picked ? 'picked' : ''}`}
      transform={`translate(${sx - 21}, ${sy - 74})`}
      onClick={() => onPick(agent.id)}
      data-agent={agent.id}
      role="button" tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter') onPick(agent.id) }}
      style={{ '--spin': `${1.6 / (speed || 1)}s` }}
    >
      {/* full-size transparent hit area so clicks never fall through to desks */}
      <rect x={-8} y={-4} width={66} height={76} fill="transparent" />
      {/* pick ring */}
      {picked && <ellipse cx="21" cy="70" rx="22" ry="8" fill="var(--accent)" opacity=".25" />}
      <svg x="0" y="0" width="42" height="42" viewBox="0 0 64 64" overflow="visible">
        <AgentBot agentId={agent.id} size={42} color={agent.color} />
      </svg>
      {bubble && (
        <text className={`iso-bubble b-${st}`} x="34" y="6" fontSize="13"
          fontWeight="800" fill="var(--text-2)">{bubble}</text>
      )}
      {/* name tag */}
      <g transform="translate(-6, 46)">
        <rect x="0" y="0" width="56" height="17" rx="8.5"
          fill="var(--surface)" stroke="var(--border)" />
        <circle cx="9" cy="8.5" r="4" fill={STATUS_DOT[st] || '#9aa1ad'} />
        <text x="17" y="12" fontSize="9.5" fontWeight="700" fill="var(--text)">
          {agent.name}
        </text>
        <rect x="42" y="3" width="12" height="11" rx="4" fill="var(--accent-subtle)" />
        <text x="48" y="11" fontSize="7.5" fontWeight="800" fill="var(--accent-text)"
          textAnchor="middle">L{agent.level || 1}</text>
      </g>
    </g>
  )
}

/* desk slots for the 10 agents */
const SLOTS = [
  [1.6, 2.1], [4.1, 2.1], [6.6, 2.1], [9.1, 2.1], [11.6, 2.1],
  [1.6, 5.6], [4.1, 5.6], [6.6, 5.6], [9.1, 5.6], [11.6, 5.6],
]

/* ============================================================ */
export default function IsometricOffice({
  agents, speed = 1, picked, onPickAgent, apiRef,
  floor = 'ground', onCustomize, connected, status,
}) {
  const [zoom, setZoom] = useState(1)
  const wrapRef = useRef(null)
  const [confetti, setConfetti] = useState(0)

  const recenter = useCallback(() => setZoom(1), [])

  useEffect(() => {
    if (!apiRef) return
    apiRef.current = {
      confetti() {
        setConfetti((c) => c + 1)
        setTimeout(() => setConfetti(0), 1600)
      },
    }
  }, [apiRef])

  const fullscreen = () => {
    const el = wrapRef.current
    if (!el) return
    if (document.fullscreenElement) document.exitFullscreen()
    else el.requestFullscreen?.().catch(() => {})
  }

  const showAgents = floor === 'ground'

  return (
    <div className="iso-wrap" ref={wrapRef} style={{ '--iso-speed': `${1.4 / speed}s` }}>
      <div className="iso-scene-holder" style={{ transform: `scale(${zoom})` }}>
        <svg className="iso-scene" viewBox="0 0 1000 560" preserveAspectRatio="xMidYMid meet"
          role="img" aria-label="Isometric agency office">
          {/* room shell */}
          <polygon points={pts([[0, 0], [13.6, 0], [13.6, 10.4], [0, 10.4]])}
            fill="var(--iso-floor)" />
          {/* floor planks */}
          {Array.from({ length: 14 }, (_, i) => (
            <line key={i}
              x1={iso(i, 0)[0]} y1={iso(i, 0)[1]}
              x2={iso(i, 10.4)[0]} y2={iso(i, 10.4)[1]}
              stroke="var(--iso-floor-2)" strokeWidth="1.4" opacity=".7" />
          ))}
          {Array.from({ length: 11 }, (_, i) => (
            <line key={'h' + i}
              x1={iso(0, i)[0]} y1={iso(0, i)[1]}
              x2={iso(13.6, i)[0]} y2={iso(13.6, i)[1]}
              stroke="var(--iso-floor-2)" strokeWidth="1" opacity=".45" />
          ))}
          {/* walls */}
          <polygon points={pts([[0, 0, 0], [13.6, 0, 0], [13.6, 0, 3.2], [0, 0, 3.2]])}
            fill="var(--iso-wall)" />
          <polygon points={pts([[0, 0, 0], [0, 10.4, 0], [0, 10.4, 3.2], [0, 0, 3.2]])}
            fill="var(--iso-wall-2)" />
          {/* wall trim */}
          <polygon points={pts([[0, 0, 3.2], [13.6, 0, 3.2], [13.6, 0, 3.45], [0, 0, 3.45]])}
            fill="var(--accent)" opacity=".55" />
          <polygon points={pts([[0, 0, 3.2], [0, 10.4, 3.2], [0, 10.4, 3.45], [0, 0, 3.45]])}
            fill="var(--accent)" opacity=".35" />

          {showAgents ? (
            <>
              <Furniture />
              {agents.slice(0, 10).map((a, i) => {
                const [dx, dy] = SLOTS[i] || [1.6, 2.1]
                return <Workstation key={'w' + a.id} x={dx} y={dy} />
              })}
            </>
          ) : (
            <g opacity=".5">
              <Box x={5} y={4} w={3} d={2} h={0.4}
                top="#c9bda6" right="#b9ad96" left="#a99d86" />
            </g>
          )}

          {/* agents (front-to-back draw order) */}
          {showAgents && agents.slice(0, 10).map((a, i) => {
            const [dx, dy] = SLOTS[i] || [1.6, 2.1]
            return (
              <AgentAtDesk key={a.id} agent={a} x={dx} y={dy}
                picked={picked === a.id} onPick={onPickAgent} speed={speed} />
            )
          })}

          {/* confetti burst */}
          {confetti > 0 && (
            <g className="iso-confetti">
              {Array.from({ length: 26 }, (_, i) => {
                const [cx, cy] = iso(6.8, 5.2, 2.6)
                const ang = (i / 26) * Math.PI * 2
                return (
                  <rect key={i} x={cx} y={cy} width="6" height="6" rx="1.5"
                    fill={['#4f46e5', '#f59e0b', '#22c55e', '#ec4899', '#38bdf8'][i % 5]}
                    style={{
                      transform: `translate(${Math.cos(ang) * 90}px, ${Math.sin(ang) * 70}px)`,
                      animation: 'confetti-fly 1.4s ease-out forwards',
                      animationDelay: `${(i % 5) * 0.03}s`,
                    }} />
                )
              })}
            </g>
          )}
        </svg>
      </div>

      {/* map controls */}
      <div className="iso-controls">
        <button className="iso-btn" title="Zoom in" onClick={() => setZoom((z) => Math.min(1.8, z + 0.15))}>
          <ZoomIn size={15} />
        </button>
        <button className="iso-btn" title="Zoom out" onClick={() => setZoom((z) => Math.max(0.6, z - 0.15))}>
          <ZoomOut size={15} />
        </button>
        <button className="iso-btn" title="Recenter" onClick={recenter}>
          <Crosshair size={15} />
        </button>
        <button className="iso-btn" title="Fullscreen" onClick={fullscreen}>
          <Maximize2 size={15} />
        </button>
        <button className="iso-btn wide" title="Customize" onClick={onCustomize}>
          <SlidersHorizontal size={15} /> Customize
        </button>
      </div>

      {/* scene status */}
      <div className="iso-status">
        <span className={`live-dot ${connected ? 'on' : ''}`} />
        <span className="mono">{status || 'idle'}</span>
      </div>

      {!showAgents && (
        <div className="iso-empty">
          <span className="iso-empty-icon">🛋️</span>
          <div>
            <strong>{floor === 'floor1' ? 'Floor 1' : 'Gym'} is quiet</strong>
            <p>Nobody assigned here yet — ground floor is where the team works.</p>
          </div>
        </div>
      )}
    </div>
  )
}

export function officeAction(api, type, payload) {
  try { api?.current?.[type]?.(payload) } catch { /* scene not ready */ }
}
