import React from 'react'
import { TrendingUp, TrendingDown, Target, Zap, Shield, Activity, BarChart2, Award } from 'lucide-react'

function MetricCard({ label, value, sub, positive, icon: Icon, color }) {
  const isPos = positive === true
  const isNeg = positive === false
  const valColor = color || (isPos ? 'var(--accent-green)' : isNeg ? 'var(--accent-red)' : 'var(--text-primary)')

  return (
    <div className="metric-card animate-fade">
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 8 }}>
        <div className="metric-label">{label}</div>
        {Icon && <Icon size={12} color="var(--text-muted)" />}
      </div>
      <div className="metric-value" style={{ color: valColor, fontSize: 20 }}>
        {value}
      </div>
      {sub && <div className="metric-sub">{sub}</div>}
    </div>
  )
}

function fmt(n, decimals = 2, suffix = '') {
  if (n == null || isNaN(n)) return '—'
  return `${Number(n).toFixed(decimals)}${suffix}`
}

function fmtPct(n, decimals = 2) {
  if (n == null || isNaN(n)) return '—'
  const sign = n >= 0 ? '+' : ''
  return `${sign}${Number(n).toFixed(decimals)}%`
}

function fmtCurrency(n) {
  if (n == null || isNaN(n)) return '—'
  return `$${Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export default function MetricsGrid({ metrics }) {
  if (!metrics) return null

  const totalReturn = metrics.total_return_pct
  const finalValue = metrics.final_value
  const initCapital = metrics.initial_capital

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* Row 1: Key P&L metrics */}
      <div>
        <div className="section-title" style={{ marginBottom: 12 }}>Performance Overview</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
          <MetricCard
            label="Total Return"
            value={fmtPct(totalReturn)}
            sub={`${fmtCurrency(initCapital)} → ${fmtCurrency(finalValue)}`}
            positive={totalReturn >= 0}
            icon={TrendingUp}
          />
          <MetricCard
            label="CAGR"
            value={fmtPct(metrics.cagr_pct)}
            sub={`Over ${fmt(metrics.years_backtested, 1)} years`}
            positive={metrics.cagr_pct >= 0}
            icon={Activity}
          />
          <MetricCard
            label="Max Drawdown"
            value={fmtPct(metrics.max_drawdown_pct)}
            sub={`${metrics.max_dd_start} → ${metrics.max_dd_end}`}
            positive={false}
            icon={TrendingDown}
          />
          <MetricCard
            label="Win Rate"
            value={`${fmt(metrics.win_rate, 1)}%`}
            sub={`${metrics.winning_trades}W / ${metrics.losing_trades}L of ${metrics.total_trades}`}
            positive={metrics.win_rate >= 50}
            icon={Target}
          />
        </div>
      </div>

      {/* Row 2: Risk-Adjusted */}
      <div>
        <div className="section-title" style={{ marginBottom: 12 }}>Risk-Adjusted Metrics</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
          <MetricCard
            label="Sharpe Ratio"
            value={fmt(metrics.sharpe_ratio, 3)}
            sub={metrics.sharpe_ratio >= 1 ? 'Good' : metrics.sharpe_ratio >= 0 ? 'Acceptable' : 'Poor'}
            positive={metrics.sharpe_ratio >= 1}
            icon={Zap}
            color={metrics.sharpe_ratio >= 2 ? 'var(--accent-green)' : metrics.sharpe_ratio >= 1 ? 'var(--accent-amber)' : 'var(--accent-red)'}
          />
          <MetricCard
            label="Sortino Ratio"
            value={fmt(metrics.sortino_ratio, 3)}
            sub="Downside risk adjusted"
            positive={metrics.sortino_ratio >= 1}
            icon={Shield}
            color={metrics.sortino_ratio >= 2 ? 'var(--accent-green)' : metrics.sortino_ratio >= 1 ? 'var(--accent-amber)' : 'var(--accent-red)'}
          />
          <MetricCard
            label="Calmar Ratio"
            value={fmt(metrics.calmar_ratio, 3)}
            sub="CAGR / Max DD"
            positive={metrics.calmar_ratio >= 0.5}
            icon={BarChart2}
          />
          <MetricCard
            label="Ann. Volatility"
            value={fmtPct(metrics.annualized_volatility_pct)}
            sub="Annualized std dev"
            icon={Activity}
            color="var(--text-secondary)"
          />
        </div>
      </div>

      {/* Row 3: Trade stats */}
      <div>
        <div className="section-title" style={{ marginBottom: 12 }}>Trade Statistics</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
          <MetricCard
            label="Expectancy"
            value={`$${fmt(metrics.expectancy, 2)}`}
            sub="Avg $ per trade"
            positive={metrics.expectancy >= 0}
            icon={Award}
          />
          <MetricCard
            label="Profit Factor"
            value={fmt(metrics.profit_factor, 3)}
            sub="Gross profit / loss"
            positive={metrics.profit_factor >= 1.5}
            color={metrics.profit_factor >= 2 ? 'var(--accent-green)' : metrics.profit_factor >= 1 ? 'var(--accent-amber)' : 'var(--accent-red)'}
          />
          <MetricCard
            label="Avg Win"
            value={fmtCurrency(metrics.avg_win)}
            sub={`Best: ${fmtCurrency(metrics.largest_win)}`}
            positive={true}
          />
          <MetricCard
            label="Avg Loss"
            value={`-${fmtCurrency(metrics.avg_loss)}`}
            sub={`Worst: ${fmtCurrency(metrics.largest_loss)}`}
            positive={false}
          />
        </div>
      </div>

      {/* Row 4: Additional */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
        <MetricCard
          label="VaR 95%"
          value={fmtPct(metrics.var_95_pct)}
          sub="Daily value at risk"
          positive={false}
        />
        <MetricCard
          label="Total Trades"
          value={metrics.total_trades}
          sub={`Avg PnL: ${fmtCurrency(metrics.avg_trade_pnl)}`}
          color="var(--text-secondary)"
        />
        <MetricCard
          label="Total PnL"
          value={fmtCurrency(metrics.total_pnl)}
          sub={`Net of slippage & commissions`}
          positive={metrics.total_pnl >= 0}
        />
      </div>
    </div>
  )
}
