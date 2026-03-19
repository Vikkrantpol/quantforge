import React from 'react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine
} from 'recharts'
import { TrendingDown } from 'lucide-react'

function formatDate(dateStr) {
  try {
    const d = new Date(dateStr)
    return d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' })
  } catch {
    return dateStr
  }
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  const val = payload[0]?.value
  return (
    <div style={{
      background: 'rgba(5, 5, 8, 0.95)',
      border: '1px solid rgba(239,68,68,0.3)',
      borderRadius: 8,
      padding: '10px 14px',
      backdropFilter: 'blur(12px)',
    }}>
      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 15, fontFamily: 'var(--font-display)', color: 'var(--accent-red)', fontWeight: 700 }}>
        {val?.toFixed(2)}%
      </div>
    </div>
  )
}

export default function DrawdownChart({ drawdownSeries, maxDrawdown }) {
  if (!drawdownSeries?.length) return null

  const thin = drawdownSeries.length > 500
    ? drawdownSeries.filter((_, i) => i % Math.ceil(drawdownSeries.length / 500) === 0)
    : drawdownSeries

  const data = thin.map(p => ({
    date: formatDate(p.date),
    drawdown: p.drawdown,
  }))

  const minDD = Math.min(...data.map(d => d.drawdown))

  return (
    <div>
      <div className="section-header">
        <div className="section-title">
          <TrendingDown size={12} style={{ color: 'var(--accent-red)' }} />
          <span style={{ color: 'var(--accent-red)' }}>Drawdown</span>
        </div>
        <div style={{ fontSize: 10, color: 'var(--accent-red)' }}>
          Max: {maxDrawdown?.toFixed(2)}%
        </div>
      </div>

      <ResponsiveContainer width="100%" height={160}>
        <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
          <defs>
            <linearGradient id="ddGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#ef4444" stopOpacity={0.25} />
              <stop offset="100%" stopColor="#ef4444" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(99,130,230,0.06)" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 9, fill: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}
            tickLine={false}
            axisLine={{ stroke: 'var(--border)' }}
            interval="preserveStartEnd"
          />
          <YAxis
            domain={[minDD * 1.1, 2]}
            tick={{ fontSize: 9, fill: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}
            tickLine={false}
            axisLine={false}
            tickFormatter={v => `${v.toFixed(0)}%`}
            width={50}
          />
          <Tooltip content={<CustomTooltip />} />
          <ReferenceLine y={0} stroke="rgba(99,130,230,0.2)" />
          <Area
            type="monotone"
            dataKey="drawdown"
            stroke="var(--accent-red)"
            strokeWidth={1.5}
            fill="url(#ddGrad)"
            dot={false}
            activeDot={{ r: 4, fill: 'var(--accent-red)', stroke: 'var(--bg-void)', strokeWidth: 2 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
