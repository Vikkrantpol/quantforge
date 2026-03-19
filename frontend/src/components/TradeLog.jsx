import React, { useState } from 'react'
import { Download, ArrowUpDown, List } from 'lucide-react'

function fmtPct(n) {
  if (n == null) return '—'
  const sign = n >= 0 ? '+' : ''
  return `${sign}${Number(n).toFixed(3)}%`
}

function fmtCurrency(n, symbol = '') {
  if (n == null) return '—'
  const isIndian = typeof symbol === 'string' && symbol.toUpperCase().endsWith('.NS')
  const cur = isIndian ? '₹' : '$'
  const sign = n >= 0 ? '+' : ''
  return `${sign}${cur}${Math.abs(n).toLocaleString(isIndian ? 'en-IN' : 'en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function fmtPrice(p, symbol = '') {
  if (p == null) return '—'
  const isIndian = typeof symbol === 'string' && symbol.toUpperCase().endsWith('.NS')
  const cur = isIndian ? '₹' : '$'
  return `${cur}${Number(p).toLocaleString(isIndian ? 'en-IN' : 'en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export default function TradeLog({ trades = [], symbol = '', strategy = '' }) {
  const [sortKey, setSortKey] = useState('entry_date')
  const [sortDir, setSortDir] = useState('asc')
  const [page, setPage] = useState(0)
  const PAGE_SIZE = 25

  const sorted = [...trades].sort((a, b) => {
    let av = a[sortKey], bv = b[sortKey]
    if (typeof av === 'string') av = av.toLowerCase()
    if (typeof bv === 'string') bv = bv.toLowerCase()
    if (av < bv) return sortDir === 'asc' ? -1 : 1
    if (av > bv) return sortDir === 'asc' ? 1 : -1
    return 0
  })

  const paged = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const totalPages = Math.ceil(sorted.length / PAGE_SIZE)

  const handleSort = key => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  const downloadCSV = () => {
    const headers = ['#', 'Entry Date', 'Exit Date', 'Entry Price', 'Exit Price', 'Shares', 'PnL', 'PnL %', 'Type']
    const rows = trades.map((t, i) => [
      i + 1, t.entry_date, t.exit_date,
      t.entry_price, t.exit_price, t.shares,
      t.pnl, t.pnl_pct, t.type
    ])
    const csv = [headers, ...rows].map(r => r.join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${symbol}_${strategy}_trades.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const SortHeader = ({ k, label }) => (
    <th
      style={{ cursor: 'pointer', userSelect: 'none' }}
      onClick={() => handleSort(k)}
    >
      <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        {label}
        <ArrowUpDown size={9} color={sortKey === k ? 'var(--accent-green)' : 'var(--text-muted)'} />
      </span>
    </th>
  )

  if (!trades.length) return (
    <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
      No trades recorded.
    </div>
  )

  return (
    <div>
      <div className="section-header">
        <div className="section-title">
          <List size={12} />
          Trade Log
          <span className="badge badge-blue" style={{ marginLeft: 6 }}>{trades.length} trades</span>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={downloadCSV}>
          <Download size={11} />
          Export CSV
        </button>
      </div>

      <div style={{ overflowX: 'auto', borderRadius: 8, border: '1px solid var(--border)' }}>
        <table className="data-table" style={{ minWidth: 650 }}>
          <thead>
            <tr>
              <th>#</th>
              <SortHeader k="entry_date" label="Entry" />
              <SortHeader k="exit_date" label="Exit" />
              <SortHeader k="entry_price" label="Entry Price" />
              <SortHeader k="exit_price" label="Exit Price" />
              <SortHeader k="shares" label="Shares" />
              <SortHeader k="pnl" label="PnL" />
              <SortHeader k="pnl_pct" label="PnL %" />
              <th>Type</th>
            </tr>
          </thead>
          <tbody>
            {paged.map((t, i) => {
              const isWin = t.pnl >= 0
              return (
                <tr key={i}>
                  <td style={{ color: 'var(--text-muted)' }}>{page * PAGE_SIZE + i + 1}</td>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>{t.entry_date}</td>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>{t.exit_date}</td>
                  <td>{fmtPrice(t.entry_price, symbol)}</td>
                  <td>{fmtPrice(t.exit_price, symbol)}</td>
                  <td>{t.shares?.toLocaleString()}</td>
                  <td className={isWin ? 'positive' : 'negative'} style={{ fontWeight: 600 }}>
                    {fmtCurrency(t.pnl, symbol)}
                  </td>
                  <td className={isWin ? 'positive' : 'negative'}>
                    {fmtPct(t.pnl_pct)}
                  </td>
                  <td>
                    <span className={`badge ${t.type?.includes('STOP') ? 'badge-amber' : isWin ? 'badge-green' : 'badge-red'}`}>
                      {t.type?.includes('STOP') ? 'STOP' : t.type || 'LONG'}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 12, fontSize: 11, color: 'var(--text-muted)' }}>
          <span>Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, trades.length)} of {trades.length}</span>
          <div style={{ display: 'flex', gap: 4 }}>
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => setPage(p => Math.max(0, p - 1))}
              disabled={page === 0}
            >
              ← Prev
            </button>
            <span style={{ padding: '4px 10px', color: 'var(--accent-green)' }}>
              {page + 1} / {totalPages}
            </span>
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
              disabled={page === totalPages - 1}
            >
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
