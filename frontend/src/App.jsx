import React, { useState, useEffect } from 'react'
import Sidebar from './components/Sidebar'
import QuantLab from './components/QuantLab'
import ResultsDashboard from './components/ResultsDashboard'
import BrokerConfig from './components/BrokerConfig'
import HistoryDashboard from './components/HistoryDashboard'
import FyersAuthCallback from './components/FyersAuthCallback'
import { healthCheck, getHistoryDetails, getBrokerDefaults } from './api/client'
import { Wifi, WifiOff } from 'lucide-react'

const BROKER_STORAGE_KEY = 'quantforge.brokerConfig'

function loadStoredBrokerConfig() {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(BROKER_STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export default function App() {
  const [page, setPage] = useState('lab')
  const [results, setResults] = useState(null)
  const [brokerConfig, setBrokerConfig] = useState(() => loadStoredBrokerConfig())
  const [apiStatus, setApiStatus] = useState('checking') // 'checking' | 'ok' | 'error'
  const [historyError, setHistoryError] = useState(null)

  const currentPath = typeof window !== 'undefined' ? window.location.pathname.replace(/\/$/, '') : ''

  useEffect(() => {
    const check = async () => {
      try {
        await healthCheck()
        setApiStatus('ok')
      } catch {
        setApiStatus('error')
      }
    }
    check()
    const id = setInterval(check, 30000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (brokerConfig?.broker) {
      window.localStorage.setItem(BROKER_STORAGE_KEY, JSON.stringify(brokerConfig))
    } else {
      window.localStorage.removeItem(BROKER_STORAGE_KEY)
    }
  }, [brokerConfig])

  useEffect(() => {
    const hydrateBrokerFromEnv = async () => {
      try {
        const defaults = await getBrokerDefaults()
        if (brokerConfig?.broker === 'fyers' && defaults?.fyers?.redirect_uri) {
          setBrokerConfig(prev => {
            if (!prev || prev.broker !== 'fyers') return prev
            if (prev.redirect_uri === defaults.fyers.redirect_uri) return prev
            return {
              ...prev,
              redirect_uri: defaults.fyers.redirect_uri,
            }
          })
          return
        }

        if (brokerConfig?.broker) return

        if (defaults?.fyers?.has_api_key && defaults?.fyers?.has_access_token) {
          setBrokerConfig({
            broker: 'fyers',
            api_key: '',
            secret_key: '',
            base_url: '',
            app_secret: '',
            redirect_uri: defaults.fyers.redirect_uri || '',
          })
          return
        }

        if (defaults?.alpaca?.has_api_key && defaults?.alpaca?.has_secret_key) {
          setBrokerConfig({
            broker: 'alpaca',
            api_key: '',
            secret_key: '',
            base_url: defaults.alpaca.base_url || '',
          })
          return
        }

        if (defaults?.zerodha?.has_api_key && defaults?.zerodha?.has_access_token) {
          setBrokerConfig({
            broker: 'zerodha',
            api_key: '',
            secret_key: '',
            base_url: '',
          })
        }
      } catch {
        // Ignore bootstrap failures; Broker page can still load explicitly.
      }
    }

    hydrateBrokerFromEnv()
    const id = setInterval(hydrateBrokerFromEnv, 10000)
    return () => clearInterval(id)
  }, [brokerConfig?.broker, brokerConfig?.redirect_uri])

  if (currentPath === '/broker/fyers/callback') {
    return <FyersAuthCallback />
  }

  const handleResults = (r) => {
    setResults(r)
    setHistoryError(null)
    setPage('results')
  }

  const handleOpenHistory = async (historyId) => {
    try {
      const res = await getHistoryDetails(historyId)
      setResults(res.result)
      setHistoryError(null)
      setPage('results')
      return res.result
    } catch (err) {
      setHistoryError(err.message)
      setPage('history')
      throw err
    }
  }

  return (
    <div style={{ display: 'flex', width: '100%', minHeight: '100vh' }}>
      <Sidebar active={page} onNav={setPage} hasResults={!!results} onOpenHistory={handleOpenHistory} />

      {/* Main area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>

        {/* Top bar */}
        <header style={{
          height: 48,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 20px',
          borderBottom: '1px solid var(--border)',
          background: 'var(--bg-surface)',
          flexShrink: 0,
        }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
            {page === 'lab' && 'Quant Lab — Backtest Engine'}
            {page === 'download' && '⇩ Data Lab — OHLCV Download'}
            {page === 'results' && '📊 Results — Performance Analysis'}
            {page === 'history' && '🕘 History — Saved Backtests'}
            {page === 'broker' && '⚙ Broker Config — API Credentials'}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {results && (
              <span className="badge badge-green">
                Last: {results.symbol} · {results.strategy?.replace(/_/g, ' ')}
              </span>
            )}
            <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 10 }}>
              {apiStatus === 'ok' ? (
                <>
                  <Wifi size={11} color="var(--accent-green)" />
                  <span style={{ color: 'var(--accent-green)' }}>API ONLINE</span>
                </>
              ) : apiStatus === 'error' ? (
                <>
                  <WifiOff size={11} color="var(--accent-red)" />
                  <span style={{ color: 'var(--accent-red)' }}>API OFFLINE</span>
                </>
              ) : (
                <span style={{ color: 'var(--text-muted)' }}>CHECKING...</span>
              )}
            </div>
          </div>
        </header>

        {/* Page content */}
        <main style={{
          flex: 1,
          padding: '20px 24px',
          overflowY: 'auto',
        }}>
          {/* API offline warning */}
          {apiStatus === 'error' && (
            <div style={{
              background: 'var(--accent-red-dim)',
              border: '1px solid rgba(239,68,68,0.3)',
              borderRadius: 8,
              padding: '10px 16px',
              marginBottom: 16,
              fontSize: 11,
              color: 'var(--accent-red)',
              display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <WifiOff size={13} />
              Backend API is offline. Run <code style={{ background: 'rgba(239,68,68,0.2)', padding: '1px 6px', borderRadius: 4 }}>./run.sh</code> to start the server.
            </div>
          )}

          {historyError && page === 'history' && (
            <div style={{
              background: 'var(--accent-red-dim)',
              border: '1px solid rgba(239,68,68,0.3)',
              borderRadius: 8,
              padding: '10px 16px',
              marginBottom: 16,
              fontSize: 11,
              color: 'var(--accent-red)',
            }}>
              Failed to open historical report: {historyError}
            </div>
          )}

          {page === 'lab' && (
            <QuantLab brokerConfig={brokerConfig} onResults={handleResults} />
          )}

          {page === 'download' && (
            <QuantLab brokerConfig={brokerConfig} onResults={handleResults} initialMode="download" />
          )}

          {page === 'results' && results && (
            <ResultsDashboard results={results} />
          )}

          {page === 'results' && !results && (
            <div style={{ textAlign: 'center', padding: '80px 20px', color: 'var(--text-muted)' }}>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 18, marginBottom: 8 }}>No results yet</div>
              <div style={{ fontSize: 12 }}>Run a backtest from the Quant Lab to see results here.</div>
              <button className="btn btn-primary" style={{ marginTop: 20 }} onClick={() => setPage('lab')}>
                Go to Quant Lab
              </button>
            </div>
          )}

          {page === 'history' && (
            <HistoryDashboard onOpenReport={handleOpenHistory} />
          )}

          {page === 'broker' && (
            <BrokerConfig
              brokerConfig={brokerConfig}
              onSave={(cfg) => {
                setBrokerConfig(cfg)
                setPage('lab')
              }}
            />
          )}
        </main>
      </div>
    </div>
  )
}
