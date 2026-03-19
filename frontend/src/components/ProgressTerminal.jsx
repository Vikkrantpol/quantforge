import React, { useEffect, useRef } from 'react'
import { Terminal, Circle } from 'lucide-react'

function classifyLine(line) {
  if (line.includes('ERROR') || line.includes('error')) return 'error'
  if (line.includes('done') || line.includes('complete') || line.includes('Done') || line.includes('ready')) return 'success'
  if (line.includes('WARN') || line.includes('warn') || line.includes('fallback')) return 'warn'
  if (line.includes('[yfinance]') || line.includes('[csv]') || line.includes('[broker') || line.includes('[alpaca]') || line.includes('[zerodha]')) return 'info'
  return 'default'
}

export default function ProgressTerminal({ logs = [], progress = 0, status = 'idle', title = 'EXECUTION LOG' }) {
  const bodyRef = useRef(null)

  useEffect(() => {
    if (bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight
    }
  }, [logs])

  const isRunning = status === 'running'
  const isError = status === 'error'
  const isComplete = status === 'complete'

  const dotColors = isError
    ? ['#ef4444', '#f59e0b', '#f59e0b']
    : isComplete
    ? ['#00ffaa', '#00ffaa', '#3b82f6']
    : ['#ef4444', '#f59e0b', '#22c55e']

  return (
    <div className="terminal" style={{ width: '100%' }}>
      {/* Header bar */}
      <div className="terminal-header">
        <div className="terminal-dot" style={{ background: dotColors[0] }} />
        <div className="terminal-dot" style={{ background: dotColors[1] }} />
        <div className="terminal-dot" style={{ background: dotColors[2] }} />
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 8, marginLeft: 8 }}>
          <Terminal size={11} color="var(--text-muted)" />
          <span style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
            {title}
          </span>
          {isRunning && (
            <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 4, fontSize: 9, color: 'var(--accent-amber)' }}>
              <div className="spinner" style={{ width: 10, height: 10, borderWidth: 1.5 }} />
              RUNNING
            </span>
          )}
          {isComplete && (
            <span style={{ marginLeft: 'auto', fontSize: 9, color: 'var(--accent-green)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
              ✓ COMPLETE
            </span>
          )}
          {isError && (
            <span style={{ marginLeft: 'auto', fontSize: 9, color: 'var(--accent-red)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
              ✗ FAILED
            </span>
          )}
        </div>
      </div>

      {/* Progress bar */}
      {(isRunning || isComplete || isError) && (
        <div style={{ padding: '6px 14px 0' }}>
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{
                width: `${progress}%`,
                background: isError
                  ? 'linear-gradient(90deg, var(--accent-red), #f97316)'
                  : 'linear-gradient(90deg, var(--accent-green), var(--accent-cyan))',
              }}
            />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 3, fontSize: 9, color: 'var(--text-muted)' }}>
            <span>Progress</span>
            <span style={{ color: isError ? 'var(--accent-red)' : 'var(--accent-green)' }}>{progress}%</span>
          </div>
        </div>
      )}

      {/* Log body */}
      <div ref={bodyRef} className="terminal-body" style={{ minHeight: 120 }}>
        {logs.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>
            {'> '}<span className="blink">_</span>
            <span style={{ marginLeft: 4 }}>Waiting for execution...</span>
          </div>
        ) : (
          logs.map((line, i) => {
            const cls = classifyLine(line)
            const colors = {
              error: 'var(--accent-red)',
              success: 'var(--accent-green)',
              warn: 'var(--accent-amber)',
              info: 'var(--text-code)',
              default: 'var(--text-secondary)',
            }
            return (
              <div
                key={i}
                className="terminal-line animate-fade"
                style={{
                  color: colors[cls],
                  animationDelay: `${Math.min(i * 0.03, 0.3)}s`,
                  display: 'flex',
                  gap: 8,
                }}
              >
                <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>{'>'}</span>
                <span>{line}</span>
              </div>
            )
          })
        )}
        {isRunning && logs.length > 0 && (
          <div style={{ color: 'var(--accent-green)', marginTop: 4 }}>
            {'> '}<span className="blink">█</span>
          </div>
        )}
      </div>
    </div>
  )
}
