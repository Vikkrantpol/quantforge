import React, { useState, useEffect } from 'react'
import { BarChart2, FlaskConical, Download, Settings, Activity, Cpu, History as HistoryIcon, Clock } from 'lucide-react'
import { getHistory } from '../api/client'

const NAV = [
  { id: 'lab',       icon: FlaskConical, label: 'Quant Lab',    sub: 'Backtest Engine' },
  { id: 'results',   icon: BarChart2,    label: 'Results',      sub: 'Metrics & Charts' },
  { id: 'history',   icon: HistoryIcon,  label: 'History',      sub: 'Past Reports' },
  { id: 'download',  icon: Download,     label: 'Data Fetch',   sub: 'Export OHLCV' },
  { id: 'broker',    icon: Settings,     label: 'Broker',       sub: 'API Config' },
]

export default function Sidebar({ active, onNav, hasResults, onOpenHistory }) {
  const [history, setHistory] = useState([])

  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const res = await getHistory(5)
        setHistory(res.history || [])
      } catch (e) {}
    }
    fetchHistory()
    // Refresh every 30s
    const timer = setInterval(fetchHistory, 30000)
    return () => clearInterval(timer)
  }, [])

  return (
    <aside style={{
      width: 220,
      minWidth: 220,
      background: 'var(--bg-surface)',
      borderRight: '1px solid var(--border)',
      display: 'flex',
      flexDirection: 'column',
      padding: '0',
      position: 'relative',
      zIndex: 10,
    }}>
      {/* Logo */}
      <div style={{
        padding: '20px 20px 16px',
        borderBottom: '1px solid var(--border)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 32, height: 32,
            background: 'linear-gradient(135deg, #00ffaa, #3b82f6)',
            borderRadius: 8,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexShrink: 0,
          }}>
            <Activity size={16} color="#050508" strokeWidth={2.5} />
          </div>
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 800, letterSpacing: '-0.03em', color: 'var(--text-primary)' }}>
              QuantForge
            </div>
            <div style={{ fontSize: 9, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em', marginTop: 1 }}>
              Research Platform
            </div>
          </div>
        </div>
      </div>

      {/* Nav items */}
      <nav style={{ padding: '12px 10px', flex: 1, overflowY: 'auto' }}>
        <div style={{ fontSize: 9, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', margin: '0 12px 10px', fontWeight: 700 }}>
          Menu
        </div>
        {NAV.map(({ id, icon: Icon, label, sub }) => {
          const isActive = active === id
          const isDisabled = id === 'results' && !hasResults
          return (
            <button
              key={id}
              onClick={() => !isDisabled && onNav(id)}
              style={{
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '10px 12px',
                borderRadius: 8,
                border: 'none',
                background: isActive ? 'rgba(0,255,170,0.08)' : 'transparent',
                borderLeft: isActive ? '2px solid var(--accent-green)' : '2px solid transparent',
                cursor: isDisabled ? 'not-allowed' : 'pointer',
                opacity: isDisabled ? 0.4 : 1,
                marginBottom: 2,
                textAlign: 'left',
                transition: 'all 0.15s',
              }}
              onMouseEnter={e => { if (!isActive && !isDisabled) e.currentTarget.style.background = 'var(--bg-hover)' }}
              onMouseLeave={e => { if (!isActive) e.currentTarget.style.background = 'transparent' }}
            >
              <Icon
                size={15}
                color={isActive ? 'var(--accent-green)' : 'var(--text-muted)'}
                strokeWidth={isActive ? 2.5 : 1.5}
              />
              <div>
                <div style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: isActive ? 'var(--accent-green)' : 'var(--text-secondary)',
                  fontFamily: 'var(--font-display)',
                  letterSpacing: '-0.01em',
                }}>
                  {label}
                </div>
              </div>
            </button>
          )
        })}

        {history.length > 0 && (
          <div style={{ marginTop: 24 }}>
            <div style={{ fontSize: 9, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', margin: '0 12px 10px', fontWeight: 700 }}>
              Recent History
            </div>
            {history.map(item => (
              <div 
                key={item.id}
                style={{
                  padding: '8px 12px',
                  fontSize: 10,
                  color: 'var(--text-secondary)',
                  borderRadius: 6,
                  cursor: 'pointer',
                  marginBottom: 2,
                  transition: 'background 0.1s'
                }}
                onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.04)'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                onClick={() => {
                  if (onOpenHistory) {
                    onOpenHistory(item.id).catch(() => {})
                  } else {
                    onNav('history')
                  }
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
                  <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{item.symbol}</span>
                  <span style={{ color: item.metrics?.total_return_pct >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                    {item.metrics?.total_return_pct?.toFixed(1)}%
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 4, color: 'var(--text-muted)', fontSize: 9 }}>
                  <Clock size={8} /> {new Date(item.timestamp).toLocaleDateString()}
                </div>
              </div>
            ))}
          </div>
        )}
      </nav>

      {/* Footer */}
      <div style={{
        padding: '12px 16px',
        borderTop: '1px solid var(--border)',
        fontSize: 9,
        color: 'var(--text-muted)',
        letterSpacing: '0.05em',
        display: 'flex',
        alignItems: 'center',
        gap: 6,
      }}>
        <Cpu size={10} />
        <span>v1.0.0 — QUANTFORGE</span>
      </div>
    </aside>
  )
}
