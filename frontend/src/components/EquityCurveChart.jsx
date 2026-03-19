import React, { useState } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Legend
} from 'recharts'
import { TrendingUp } from 'lucide-react'

function formatDate(dateStr) {
  try {
    const d = new Date(dateStr)
    return d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' })
  } catch {
    return dateStr
  }
}

function formatCurrency(v) {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000) return `$${(v / 1_000).toFixed(1)}K`
  return `$${v.toFixed(0)}`
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  const val = payload[0]?.value
  const init = payload[0]?.payload?.initial

  return (
    <div style={{
      background: 'rgba(5, 5, 8, 0.95)',
      border: '1px solid var(--border-bright)',
      borderRadius: 8,
      padding: '10px 14px',
      backdropFilter: 'blur(12px)',
    }}>
      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
        {label}
      </div>
      <div style={{ fontSize: 16, fontFamily: 'var(--font-display)', color: 'var(--accent-green)', fontWeight: 700 }}>
        ${val?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </div>
      {init && (
        <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 3 }}>
          {((val - init) / init * 100).toFixed(2)}% return
        </div>
      )}
    </div>
  )
}

export default function EquityCurveChart({ equityCurve, initialCapital }) {
  if (!equityCurve?.length) return null

  // Thin the data for performance (max 500 points)
  const thin = equityCurve.length > 500
    ? equityCurve.filter((_, i) => i % Math.ceil(equityCurve.length / 500) === 0)
    : equityCurve

  const data = thin.map(p => ({
    date: formatDate(p.date),
    fullDate: p.date,
    value: p.value,
    initial: initialCapital,
  }))

  const minVal = Math.min(...data.map(d => d.value))
  const maxVal = Math.max(...data.map(d => d.value))
  const padding = (maxVal - minVal) * 0.05

  return (
    <div>
      <div className="section-header">
        <div className="section-title">
          <TrendingUp size={12} />
          Equity Curve
        </div>
        <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
          {equityCurve.length.toLocaleString()} bars
        </div>
      </div>

      <ResponsiveContainer width="100%" height={280}>
        <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
          <defs>
            <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#00ffaa" stopOpacity={0.3} />
              <stop offset="70%" stopColor="#00ffaa" stopOpacity={0.04} />
              <stop offset="100%" stopColor="#00ffaa" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="rgba(99,130,230,0.07)"
            vertical={false}
          />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 9, fill: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}
            tickLine={false}
            axisLine={{ stroke: 'var(--border)' }}
            interval="preserveStartEnd"
          />
          <YAxis
            domain={[minVal - padding, maxVal + padding]}
            tick={{ fontSize: 9, fill: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}
            tickLine={false}
            axisLine={false}
            tickFormatter={formatCurrency}
            width={60}
          />
          <Tooltip content={<CustomTooltip />} />
          <ReferenceLine
            y={initialCapital}
            stroke="rgba(99,130,230,0.3)"
            strokeDasharray="4 4"
            label={{ value: 'Start', fontSize: 9, fill: 'var(--text-muted)', position: 'right' }}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke="var(--accent-green)"
            strokeWidth={1.5}
            fill="url(#equityGrad)"
            dot={false}
            activeDot={{ r: 4, fill: 'var(--accent-green)', stroke: 'var(--bg-void)', strokeWidth: 2 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
