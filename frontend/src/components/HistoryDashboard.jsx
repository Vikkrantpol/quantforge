import React, { useEffect, useState } from 'react'
import { Clock3, History as HistoryIcon, RefreshCw, FolderOpen, BarChart2 } from 'lucide-react'
import { getHistory } from '../api/client'

function fmtPct(value, decimals = 2) {
  if (value == null || Number.isNaN(Number(value))) return '—'
  const n = Number(value)
  return `${n >= 0 ? '+' : ''}${n.toFixed(decimals)}%`
}

function fmtDate(value) {
  if (!value) return '—'
  const dt = new Date(value)
  return Number.isNaN(dt.getTime())
    ? value
    : dt.toLocaleString([], { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function fmtStrategy(name) {
  if (!name) return 'Unknown Strategy'
  return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

export default function HistoryDashboard({ onOpenReport }) {
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [openingId, setOpeningId] = useState(null)

  const loadHistory = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getHistory(50)
      setHistory(res.history || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadHistory()
  }, [])

  const handleOpen = async (id) => {
    if (!onOpenReport) return
    setOpeningId(id)
    try {
      await onOpenReport(id)
    } finally {
      setOpeningId(null)
    }
  }

  return (
    <div className="animate-fade" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div className="glass-accent" style={{ padding: '18px 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
              <HistoryIcon size={18} color="var(--accent-green)" />
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 800 }}>Backtest History</div>
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', maxWidth: 720 }}>
              Review saved runs, compare headline performance, and reopen any report that was persisted to local history.
            </div>
          </div>
          <button className="btn btn-secondary" onClick={loadHistory} disabled={loading}>
            <RefreshCw size={12} />
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {error && (
        <div style={{
          background: 'var(--accent-red-dim)',
          border: '1px solid rgba(239,68,68,0.3)',
          borderRadius: 8,
          padding: '12px 16px',
          fontSize: 11,
          color: 'var(--accent-red)',
        }}>
          Failed to load history: {error}
        </div>
      )}

      {!loading && !error && history.length === 0 && (
        <div className="glass" style={{ padding: '48px 24px', textAlign: 'center' }}>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 20, marginBottom: 8 }}>No saved backtests yet</div>
          <div style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
            Run a backtest from the Quant Lab and it will appear here automatically.
          </div>
        </div>
      )}

      {history.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
          {history.map(item => {
            const metrics = item.metrics || {}
            const params = item.parameters || {}
            return (
              <div key={item.id} className="glass" style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 14 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'flex-start' }}>
                  <div>
                    <div style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 800 }}>
                      {item.symbol}
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginTop: 4 }}>
                      {fmtStrategy(item.strategy)} · {item.interval ? item.interval.toUpperCase() : '—'}
                    </div>
                  </div>
                  <span className={`badge ${Number(metrics.total_return_pct) >= 0 ? 'badge-green' : 'badge-red'}`}>
                    {fmtPct(metrics.total_return_pct)}
                  </span>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
                  <div style={{ background: 'var(--bg-surface)', borderRadius: 8, padding: '10px 12px', border: '1px solid var(--border)' }}>
                    <div style={{ fontSize: 9, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 4 }}>CAGR</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: Number(metrics.cagr_pct) >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                      {fmtPct(metrics.cagr_pct)}
                    </div>
                  </div>
                  <div style={{ background: 'var(--bg-surface)', borderRadius: 8, padding: '10px 12px', border: '1px solid var(--border)' }}>
                    <div style={{ fontSize: 9, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 4 }}>Max DD</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--accent-red)' }}>
                      {fmtPct(metrics.max_drawdown_pct)}
                    </div>
                  </div>
                  <div style={{ background: 'var(--bg-surface)', borderRadius: 8, padding: '10px 12px', border: '1px solid var(--border)' }}>
                    <div style={{ fontSize: 9, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 4 }}>Trades</div>
                    <div style={{ fontSize: 14, fontWeight: 700 }}>{metrics.total_trades ?? '—'}</div>
                  </div>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 10, color: 'var(--text-secondary)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Clock3 size={10} color="var(--text-muted)" />
                    <span>{fmtDate(item.timestamp)}</span>
                  </div>
                  <div>
                    Period: <span className="mono">{item.start_date || '—'} → {item.end_date || '—'}</span>
                  </div>
                  <div>
                    Params: <span className="mono">{Object.keys(params).length ? JSON.stringify(params) : 'Default parameters'}</span>
                  </div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginTop: 'auto' }}>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <BarChart2 size={10} />
                    Saved report
                  </div>
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={() => handleOpen(item.id)}
                    disabled={openingId === item.id}
                  >
                    <FolderOpen size={11} />
                    {openingId === item.id ? 'Opening...' : 'Open Report'}
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
