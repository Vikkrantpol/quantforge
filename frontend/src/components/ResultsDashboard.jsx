import React, { useState } from 'react'
import { Download, BarChart2 } from 'lucide-react'
import MetricsGrid from './MetricsGrid'
import EquityCurveChart from './EquityCurveChart'
import DrawdownChart from './DrawdownChart'
import TradeLog from './TradeLog'

const TABS = ['Overview', 'Charts', 'Trades']

export default function ResultsDashboard({ results }) {
  const [tab, setTab] = useState('Overview')

  if (!results) return null

  const {
    metrics,
    equity_curve = [],
    drawdown_series = [],
    trades = [],
    symbol,
    strategy,
    interval,
    start,
    end,
    history_summary_only,
  } = results

  const metaLine = [
    start && end ? `${start} → ${end}` : null,
    interval ? interval.toUpperCase() : null,
    Number.isFinite(results.total_bars) ? `${results.total_bars.toLocaleString()} bars` : null,
    history_summary_only ? 'Summary-only history entry' : null,
  ].filter(Boolean).join(' · ')

  const downloadResults = () => {
    const blob = new Blob([JSON.stringify(results, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${symbol}_${strategy}_backtest.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="animate-fade">
      {/* Results header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginBottom: 20,
        padding: '14px 18px',
        background: 'var(--bg-glass)',
        border: '1px solid var(--border-accent)',
        borderRadius: 10,
        backdropFilter: 'blur(12px)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <BarChart2 size={18} color="var(--accent-green)" />
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 800 }}>
              {symbol} — {strategy.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
            </div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
              {metaLine || 'Saved backtest'}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 6, marginLeft: 8 }}>
            <span className={`badge ${metrics.total_return_pct >= 0 ? 'badge-green' : 'badge-red'}`}>
              {metrics.total_return_pct >= 0 ? '+' : ''}{metrics.total_return_pct?.toFixed(2)}%
            </span>
            <span className="badge badge-blue">{metrics.total_trades} trades</span>
          </div>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={downloadResults}>
          <Download size={11} />
          Download JSON
        </button>
      </div>

      {history_summary_only && (
        <div style={{
          background: 'var(--accent-blue-dim)',
          border: '1px solid rgba(59,130,246,0.3)',
          borderRadius: 8,
          padding: '10px 14px',
          marginBottom: 16,
          fontSize: 11,
          color: 'var(--text-primary)',
        }}>
          This report was saved before full chart payloads were persisted. Metrics and trades are available, but some charts may be unavailable.
        </div>
      )}

      {/* Tabs */}
      <div className="tabs" style={{ marginBottom: 20 }}>
        {TABS.map(t => (
          <button
            key={t}
            className={`tab-btn ${tab === t ? 'active' : ''}`}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Overview tab */}
      {tab === 'Overview' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          <MetricsGrid metrics={metrics} />
          <div className="glass" style={{ padding: '20px 20px 12px' }}>
            <EquityCurveChart equityCurve={equity_curve} initialCapital={metrics.initial_capital} />
          </div>
          <div className="glass" style={{ padding: '20px 20px 12px' }}>
            <DrawdownChart drawdownSeries={drawdown_series} maxDrawdown={metrics.max_drawdown_pct} />
          </div>
        </div>
      )}

      {/* Charts tab */}
      {tab === 'Charts' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="glass" style={{ padding: '20px 20px 12px' }}>
            <EquityCurveChart equityCurve={equity_curve} initialCapital={metrics.initial_capital} />
          </div>
          <div className="glass" style={{ padding: '20px 20px 12px' }}>
            <DrawdownChart drawdownSeries={drawdown_series} maxDrawdown={metrics.max_drawdown_pct} />
          </div>

          {/* Strategy parameters summary */}
          <div className="glass" style={{ padding: 16 }}>
            <div className="section-title" style={{ marginBottom: 12 }}>Strategy Configuration</div>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              {Object.entries(results.strategy_params || {}).map(([k, v]) => (
                <div key={k} style={{
                  background: 'var(--bg-surface)',
                  border: '1px solid var(--border)',
                  borderRadius: 6,
                  padding: '6px 12px',
                  fontSize: 11,
                }}>
                  <span style={{ color: 'var(--text-muted)' }}>{k}: </span>
                  <span style={{ color: 'var(--accent-cyan)' }}>{v}</span>
                </div>
              ))}
              {Object.keys(results.strategy_params || {}).length === 0 && (
                <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>Default parameters used</span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Trades tab */}
      {tab === 'Trades' && (
        <div className="glass" style={{ padding: 20 }}>
          <TradeLog trades={trades} symbol={symbol} strategy={strategy} />
        </div>
      )}
    </div>
  )
}
