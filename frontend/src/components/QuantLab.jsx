import React, { useState, useEffect, useRef } from 'react'
import { Play, Download, RefreshCw, Database, Zap, ChevronDown, ChevronUp } from 'lucide-react'
import ProgressTerminal from './ProgressTerminal'
import {
  startBacktest, getBacktestStatus, getBacktestResults,
  startDownload, getDownloadStatus, getDownloadCsvUrl,
  getSymbols, uploadCsv, getSampleData, getSampleCsvUrl
} from '../api/client'
import { Upload, FileText, History as HistoryIcon } from 'lucide-react'

const STRATEGY_DEFAULTS = {
  ema_crossover: { fast: 12, slow: 26 },
  rsi_mean_reversion: { period: 14, oversold: 30, overbought: 70 },
  breakout: { window: 20 },
  macd: { fast: 12, slow: 26, signal_period: 9 },
}

const STRATEGY_LABELS = {
  ema_crossover: 'EMA Crossover',
  rsi_mean_reversion: 'RSI Mean Reversion',
  breakout: 'Breakout (Donchian)',
  macd: 'MACD',
}

function ParamInput({ label, name, value, onChange, min, max, step = 1 }) {
  return (
    <div className="form-group">
      <label className="form-label">{label}</label>
      <input
        type="number"
        className="form-input"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={e => onChange(name, Number(e.target.value))}
      />
    </div>
  )
}

export default function QuantLab({ brokerConfig, onResults }) {
  const [mode, setMode] = useState('backtest') // 'backtest' | 'download'

  // Form state
  const [symbol, setSymbol] = useState('AAPL')
  const [start, setStart] = useState('2021-01-01')
  const [end, setEnd] = useState('2024-01-01')
  const [interval, setInterval_] = useState('1d')
  const [source, setSource] = useState('yfinance')
  const [strategy, setStrategy] = useState('ema_crossover')
  const [stratParams, setStratParams] = useState(STRATEGY_DEFAULTS.ema_crossover)
  const [capital, setCapital] = useState(100000)
  const [slippage, setSlippage] = useState(0.05)
  const [commission, setCommission] = useState(10)
  const [sizing, setSizing] = useState('pct_capital')
  const [positionPct, setPositionPct] = useState(20)
  const [fixedUnits, setFixedUnits] = useState(100)
  const [stopLoss, setStopLoss] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)

  const [period, setPeriod] = useState('')
  const [executionMode, setExecutionMode] = useState('on_close')
  const [stopLossAtr, setStopLossAtr] = useState('')
  const [csvFile, setCsvFile] = useState(null)
  const [csvPath, setCsvPath] = useState('')
  const [isUploading, setIsUploading] = useState(false)
  const [sampleFiles, setSampleFiles] = useState([])

  // Symbols list
  const [symbolSuggestions, setSymbolSuggestions] = useState([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const fileInputRef = useRef(null)

  // Task state
  const [taskId, setTaskId] = useState(null)
  const [taskStatus, setTaskStatus] = useState('idle')
  const [logs, setLogs] = useState([])
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState(null)
  const pollRef = useRef(null)

  // Download state
  const [dlTaskId, setDlTaskId] = useState(null)
  const [dlStatus, setDlStatus] = useState('idle')
  const [dlLogs, setDlLogs] = useState([])
  const [dlProgress, setDlProgress] = useState(0)
  const [dlResult, setDlResult] = useState(null)

  useEffect(() => {
    getSymbols().then(s => {
      const all = [...(s.us || []), ...(s.india || []), ...(s.crypto || []), ...(s.indices || [])]
      setSymbolSuggestions(all)
    }).catch(() => {})
    getSampleData().then(data => setSampleFiles(data.files || [])).catch(() => {})
  }, [])

  // Strategy param reset on change
  const handleStrategyChange = (s) => {
    setStrategy(s)
    setStratParams(STRATEGY_DEFAULTS[s] || {})
  }

  const updateParam = (key, val) => setStratParams(p => ({ ...p, [key]: val }))

  // ─── Polling ───────────────────────────────────────────────────

  const startPolling = (id, isDownload = false) => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const statusFn = isDownload ? getDownloadStatus : getBacktestStatus
        const data = await statusFn(id)
        if (isDownload) {
          setDlLogs(data.logs || [])
          setDlProgress(data.progress || 0)
          setDlStatus(data.status)
          if (data.status === 'complete') {
            clearInterval(pollRef.current)
            setDlResult(data.result)
          } else if (data.status === 'error') {
            clearInterval(pollRef.current)
          }
        } else {
          setLogs(data.logs || [])
          setProgress(data.progress || 0)
          setTaskStatus(data.status)
          if (data.status === 'complete') {
            clearInterval(pollRef.current)
            const results = await getBacktestResults(id)
            onResults(results)
          } else if (data.status === 'error') {
            clearInterval(pollRef.current)
            setError(data.error)
          }
        }
      } catch (e) {
        clearInterval(pollRef.current)
      }
    }, 500)
  }

  // ─── Backtest ──────────────────────────────────────────────────

  const runBacktest = async () => {
    setTaskStatus('running')
    setLogs([])
    setProgress(0)
    setError(null)

    const payload = {
      symbol: symbol.trim().toUpperCase(),
      start, end, interval,
      period: period || null,
      source: source === 'csv' ? 'csv' : (source === 'broker' && brokerConfig?.broker ? 'broker' : 'yfinance'),
      csv_path: source === 'csv' ? csvPath : null,
      broker: brokerConfig?.broker || null,
      broker_api_key: brokerConfig?.api_key || null,
      broker_secret_key: brokerConfig?.secret_key || null,
      strategy,
      strategy_params: stratParams,
      initial_capital: capital,
      slippage_pct: slippage,
      commission,
      position_sizing: sizing,
      position_pct: positionPct,
      fixed_units: fixedUnits,
      stop_loss_pct: stopLoss ? Number(stopLoss) : null,
      stop_loss_atr_mult: stopLossAtr ? Number(stopLossAtr) : null,
      execution_mode: executionMode,
    }

    try {
      const res = await startBacktest(payload)
      setTaskId(res.backtest_id)
      startPolling(res.backtest_id, false)
    } catch (e) {
      setTaskStatus('error')
      setError(e.message)
    }
  }

  // ─── Download ──────────────────────────────────────────────────

  const runDownload = async () => {
    setDlStatus('running')
    setDlLogs([])
    setDlProgress(0)
    setDlResult(null)

    const payload = {
      symbol: symbol.trim().toUpperCase(),
      start, end, interval,
      source: source === 'broker' && brokerConfig?.broker ? 'broker' : 'yfinance',
      broker: brokerConfig?.broker || null,
      broker_api_key: brokerConfig?.api_key || null,
      broker_secret_key: brokerConfig?.secret_key || null,
    }

    try {
      const res = await startDownload(payload)
      setDlTaskId(res.download_id)
      startPolling(res.download_id, true)
    } catch (e) {
      setDlStatus('error')
      setDlLogs([`ERROR: ${e.message}`])
    }
  }

  const handleDownloadCsv = () => {
    if (dlTaskId) window.open(getDownloadCsvUrl(dlTaskId), '_blank')
  }

  const filteredSymbols = symbolSuggestions.filter(s => s.toLowerCase().includes(symbol.toLowerCase()) && s !== symbol)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 1100, margin: '0 auto' }}>

      {/* Mode tabs */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
        <div className="tabs" style={{ width: 'auto' }}>
          <button className={`tab-btn ${mode === 'backtest' ? 'active' : ''}`} onClick={() => setMode('backtest')}>
            <Zap size={11} style={{ marginRight: 4 }} /> Backtest
          </button>
          <button className={`tab-btn ${mode === 'download' ? 'active' : ''}`} onClick={() => setMode('download')}>
            <Database size={11} style={{ marginRight: 4 }} /> Download Data
          </button>
        </div>
        {source === 'yfinance' && (
          <span className="badge badge-blue">yfinance</span>
        )}
        {source === 'broker' && brokerConfig?.broker && (
          <span className="badge badge-green">{brokerConfig.broker.toUpperCase()}</span>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: 16, alignItems: 'start' }}>

        {/* ── Left panel: Form ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

          {/* Data Source Card */}
          <div className="glass" style={{ padding: 16 }}>
            <div className="section-title" style={{ marginBottom: 14 }}>Data Source</div>

            {/* Symbol with autocomplete */}
            <div className="form-group" style={{ marginBottom: 10, position: 'relative' }}>
              <label className="form-label">Symbol</label>
              <input
                type="text"
                className="form-input"
                value={symbol}
                onChange={e => { setSymbol(e.target.value.toUpperCase()); setShowSuggestions(true) }}
                onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
                placeholder="AAPL, MSFT, BTC-USD..."
              />
              {showSuggestions && filteredSymbols.length > 0 && (
                <div style={{
                  position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 99,
                  background: 'var(--bg-raised)',
                  border: '1px solid var(--border-bright)',
                  borderRadius: 8,
                  marginTop: 2,
                  maxHeight: 160,
                  overflowY: 'auto',
                }}>
                  {filteredSymbols.slice(0, 8).map(s => (
                    <button
                      key={s}
                      onMouseDown={() => { setSymbol(s); setShowSuggestions(false) }}
                      style={{
                        width: '100%', textAlign: 'left', padding: '7px 12px',
                        background: 'transparent', border: 'none', cursor: 'pointer',
                        color: 'var(--text-secondary)', fontSize: 12,
                        fontFamily: 'var(--font-mono)',
                        transition: 'background 0.1s',
                      }}
                      onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-hover)'}
                      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 10 }}>
              <div className="form-group">
                <label className="form-label">Period</label>
                <select className="form-select" value={period} onChange={e => { setPeriod(e.target.value); if(e.target.value) { setStart(''); setEnd('') } }}>
                  <option value="">Custom Range</option>
                  <option value="1m">1 Month</option>
                  <option value="3m">3 Months</option>
                  <option value="6m">6 Months</option>
                  <option value="1y">1 Year</option>
                  <option value="2y">2 Years</option>
                  <option value="3y">3 Years</option>
                  <option value="5y">5 Years</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Interval</label>
                <select className="form-select" value={interval} onChange={e => setInterval_(e.target.value)}>
                  <option value="1d">1 Day</option>
                  <option value="1h">1 Hour</option>
                  <option value="15m">15 Min</option>
                  <option value="5m">5 Min</option>
                  <option value="1wk">1 Week</option>
                </select>
              </div>
            </div>

            {!period && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 10 }}>
                <div className="form-group">
                  <label className="form-label">Start Date</label>
                  <input type="date" className="form-input" value={start} onChange={e => setStart(e.target.value)} />
                </div>
                <div className="form-group">
                  <label className="form-label">End Date</label>
                  <input type="date" className="form-input" value={end} onChange={e => setEnd(e.target.value)} />
                </div>
              </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <div className="form-group">
                <label className="form-label">Source</label>
                <select className="form-select" value={source} onChange={e => setSource(e.target.value)}>
                  <option value="yfinance">yfinance</option>
                  <option value="csv">CSV Upload</option>
                  <option value="broker" disabled={!brokerConfig?.broker}>
                    {brokerConfig?.broker ? brokerConfig.broker.toUpperCase() : 'Broker (not set)'}
                  </option>
                </select>
              </div>
              {source === 'csv' && (
                <div className="form-group">
                  <label className="form-label">File</label>
                  <div style={{ display: 'flex', gap: 4 }}>
                    <button 
                      className="btn btn-secondary btn-sm" 
                      onClick={() => fileInputRef.current?.click()}
                      disabled={isUploading}
                      style={{ flex: 1, height: 32 }}
                    >
                      <Upload size={12} /> {csvFile ? 'Change' : 'Upload'}
                    </button>
                    <input 
                      type="file" 
                      ref={fileInputRef} 
                      onChange={async (e) => {
                        const file = e.target.files[0]
                        if (file) {
                          setCsvFile(file)
                          setIsUploading(true)
                          try {
                            const res = await uploadCsv(file)
                            setCsvPath(res.path)
                          } catch (err) {
                            setError("Upload failed: " + err.message)
                          } finally {
                            setIsUploading(false)
                          }
                        }
                      }} 
                      style={{ display: 'none' }} 
                    />
                  </div>
                  {csvFile && <div style={{ fontSize: 9, color: 'var(--accent-green)', marginTop: 4 }}>✓ {csvFile.name}</div>}
                </div>
              )}
            </div>

            {source === 'csv' && sampleFiles.length > 0 && (
              <div style={{ marginTop: 12, padding: 8, background: 'rgba(255,255,255,0.03)', borderRadius: 6 }}>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 4 }}>
                  <FileText size={10} /> Sample Formats:
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {sampleFiles.map(f => (
                    <a 
                      key={f.filename}
                      href={getSampleCsvUrl(f.filename)}
                      download
                      style={{ fontSize: 9, color: 'var(--accent-blue)', textDecoration: 'none' }}
                      onMouseEnter={e => e.target.style.textDecoration = 'underline'}
                      onMouseLeave={e => e.target.style.textDecoration = 'none'}
                    >
                      {f.filename} ({f.size_kb}kb)
                    </a>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Strategy Card (only for backtest mode) */}
          {mode === 'backtest' && (
            <div className="glass" style={{ padding: 16 }}>
              <div className="section-title" style={{ marginBottom: 14 }}>Strategy</div>

              <div className="form-group" style={{ marginBottom: 12 }}>
                <label className="form-label">Strategy Type</label>
                <select className="form-select" value={strategy} onChange={e => handleStrategyChange(e.target.value)}>
                  {Object.entries(STRATEGY_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
              </div>

              {strategy === 'ema_crossover' && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <ParamInput label="Fast EMA" name="fast" value={stratParams.fast} onChange={updateParam} min={2} max={200} />
                  <ParamInput label="Slow EMA" name="slow" value={stratParams.slow} onChange={updateParam} min={5} max={500} />
                </div>
              )}

              {strategy === 'rsi_mean_reversion' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <ParamInput label="RSI Period" name="period" value={stratParams.period} onChange={updateParam} min={2} max={50} />
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                    <ParamInput label="Oversold" name="oversold" value={stratParams.oversold} onChange={updateParam} min={5} max={45} />
                    <ParamInput label="Overbought" name="overbought" value={stratParams.overbought} onChange={updateParam} min={55} max={95} />
                  </div>
                </div>
              )}

              {strategy === 'breakout' && (
                <ParamInput label="Window (bars)" name="window" value={stratParams.window} onChange={updateParam} min={5} max={200} />
              )}

              {strategy === 'macd' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                    <ParamInput label="Fast" name="fast" value={stratParams.fast} onChange={updateParam} min={2} max={50} />
                    <ParamInput label="Slow" name="slow" value={stratParams.slow} onChange={updateParam} min={5} max={200} />
                  </div>
                  <ParamInput label="Signal Period" name="signal_period" value={stratParams.signal_period} onChange={updateParam} min={2} max={50} />
                </div>
              )}
            </div>
          )}

          {/* Execution params — backtest only */}
          {mode === 'backtest' && (
            <div className="glass" style={{ padding: 16 }}>
              <div
                className="section-title"
                style={{ marginBottom: showAdvanced ? 14 : 0, cursor: 'pointer' }}
                onClick={() => setShowAdvanced(v => !v)}
              >
                Execution Settings
                {showAdvanced ? <ChevronUp size={12} style={{ marginLeft: 'auto' }} /> : <ChevronDown size={12} style={{ marginLeft: 'auto' }} />}
              </div>

              {showAdvanced && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <div className="form-group">
                    <label className="form-label">Initial Capital ($)</label>
                    <input type="number" className="form-input" value={capital} onChange={e => setCapital(Number(e.target.value))} min={1000} step={1000} />
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                    <div className="form-group">
                      <label className="form-label">Slippage %</label>
                      <input type="number" className="form-input" value={slippage} onChange={e => setSlippage(Number(e.target.value))} min={0} max={1} step={0.01} />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Commission ($)</label>
                      <input type="number" className="form-input" value={commission} onChange={e => setCommission(Number(e.target.value))} min={0} step={0.5} />
                    </div>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Position Sizing</label>
                    <select className="form-select" value={sizing} onChange={e => setSizing(e.target.value)}>
                      <option value="pct_capital">% of Capital</option>
                      <option value="fixed">Fixed Units</option>
                      <option value="kelly">Kelly Criterion</option>
                    </select>
                  </div>
                  {sizing === 'pct_capital' && (
                    <div className="form-group">
                      <label className="form-label">Position % of Capital</label>
                      <input type="number" className="form-input" value={positionPct} onChange={e => setPositionPct(Number(e.target.value))} min={1} max={100} />
                    </div>
                  )}
                  {sizing === 'fixed' && (
                    <div className="form-group">
                      <label className="form-label">Fixed Units (shares)</label>
                      <input type="number" className="form-input" value={fixedUnits} onChange={e => setFixedUnits(Number(e.target.value))} min={1} />
                    </div>
                  )}
                  <div className="form-group">
                    <label className="form-label">Execution Mode</label>
                    <select className="form-select" value={executionMode} onChange={e => setExecutionMode(e.target.value)}>
                      <option value="on_close">On Bar Close</option>
                      <option value="intrabar">Intrabar (Immediate Trigger)</option>
                    </select>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                    <div className="form-group">
                      <label className="form-label">Stop Loss %</label>
                      <input type="number" className="form-input" value={stopLoss} onChange={e => { setStopLoss(e.target.value); setStopLossAtr('') }} min={0} max={50} step={0.5} placeholder="e.g. 5" />
                    </div>
                    <div className="form-group">
                      <label className="form-label">ATR Stop Mult</label>
                      <input type="number" className="form-input" value={stopLossAtr} onChange={e => { setStopLossAtr(e.target.value); setStopLoss('') }} min={0} max={10} step={0.1} placeholder="e.g. 2.0" />
                    </div>
                  </div>
                </div>
              )}

              {!showAdvanced && (
                <div style={{ marginTop: 8, fontSize: 10, color: 'var(--text-muted)' }}>
                  Capital: ${capital.toLocaleString()} · Slippage: {slippage}% · Commission: ${commission}
                </div>
              )}
            </div>
          )}

          {/* Action button */}
          {mode === 'backtest' ? (
            <button
              className="btn btn-primary btn-lg"
              onClick={runBacktest}
              disabled={taskStatus === 'running'}
              style={{ width: '100%' }}
            >
              {taskStatus === 'running'
                ? <><div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Running Backtest...</>
                : <><Play size={14} /> Run Backtest</>
              }
            </button>
          ) : (
            <button
              className="btn btn-primary btn-lg"
              onClick={runDownload}
              disabled={dlStatus === 'running'}
              style={{ width: '100%' }}
            >
              {dlStatus === 'running'
                ? <><div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Downloading...</>
                : <><Download size={14} /> Download OHLCV Data</>
              }
            </button>
          )}
        </div>

        {/* ── Right panel: Terminal + results summary ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {mode === 'backtest' ? (
            <ProgressTerminal
              logs={logs}
              progress={progress}
              status={taskStatus}
              title={`BACKTEST — ${symbol} / ${strategy.toUpperCase()}`}
            />
          ) : (
            <ProgressTerminal
              logs={dlLogs}
              progress={dlProgress}
              status={dlStatus}
              title={`DATA DOWNLOAD — ${symbol}`}
            />
          )}

          {/* Download result */}
          {mode === 'download' && dlStatus === 'complete' && dlResult && (
            <div className="glass-accent" style={{ padding: 16 }}>
              <div style={{ marginBottom: 10, display: 'flex', alignItems: 'center', gap: 8 }}>
                <span className="badge badge-green">✓ Complete</span>
                <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{dlResult.rows?.toLocaleString()} rows · {dlResult.symbol} · {dlResult.interval}</span>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn btn-primary btn-sm" onClick={handleDownloadCsv}>
                  <Download size={11} /> Download CSV
                </button>
                <span style={{ fontSize: 10, color: 'var(--text-muted)', alignSelf: 'center' }}>
                  Columns: {dlResult.columns?.join(', ')}
                </span>
              </div>
            </div>
          )}

          {/* Error display */}
          {(taskStatus === 'error' || dlStatus === 'error') && (
            <div style={{
              background: 'var(--accent-red-dim)',
              border: '1px solid rgba(239,68,68,0.3)',
              borderRadius: 8,
              padding: '12px 16px',
              fontSize: 11,
              color: 'var(--accent-red)',
            }}>
              <strong>Error:</strong> {error || 'Check terminal for details'}
            </div>
          )}

          {/* Quick start hint */}
          {taskStatus === 'idle' && mode === 'backtest' && logs.length === 0 && (
            <div style={{
              padding: 20,
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              borderRadius: 10,
              fontSize: 11,
              color: 'var(--text-muted)',
              lineHeight: 1.8,
            }}>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 700, color: 'var(--text-secondary)', marginBottom: 10 }}>
                Quick Start
              </div>
              <div>1. Set your <strong style={{ color: 'var(--text-primary)' }}>symbol</strong> (e.g. AAPL, MSFT, BTC-USD)</div>
              <div>2. Choose a <strong style={{ color: 'var(--text-primary)' }}>date range</strong> and <strong style={{ color: 'var(--text-primary)' }}>interval</strong></div>
              <div>3. Select a <strong style={{ color: 'var(--text-primary)' }}>strategy</strong> and tune parameters</div>
              <div>4. Click <strong style={{ color: 'var(--accent-green)' }}>Run Backtest</strong> and watch the terminal</div>
              <div>5. View results in the <strong style={{ color: 'var(--text-primary)' }}>Results</strong> tab</div>
            </div>
          )}

          {dlStatus === 'idle' && mode === 'download' && (
            <div style={{
              padding: 20,
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              borderRadius: 10,
              fontSize: 11,
              color: 'var(--text-muted)',
              lineHeight: 1.8,
            }}>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 700, color: 'var(--text-secondary)', marginBottom: 10 }}>
                Data Download
              </div>
              <div>• Fetches OHLCV data from <strong style={{ color: 'var(--text-primary)' }}>yfinance</strong> or your broker</div>
              <div>• Choose symbol, date range, and interval</div>
              <div>• Downloads as a clean <strong style={{ color: 'var(--accent-green)' }}>CSV file</strong></div>
              <div>• Supports US stocks, Indian markets (NSE), crypto, and indices</div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
