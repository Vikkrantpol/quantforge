import React, { useEffect } from 'react'

function readCallbackParams() {
  const searchParams = new URLSearchParams(window.location.search)
  const hashParams = new URLSearchParams((window.location.hash || '').replace(/^#/, ''))
  const get = (key) => searchParams.get(key) || hashParams.get(key) || ''

  return {
    authCode: get('auth_code') || get('code'),
    state: get('state'),
    error: get('error') || get('message'),
  }
}

export default function FyersAuthCallback() {
  useEffect(() => {
    const { authCode, state, error } = readCallbackParams()

    if (window.opener && !window.opener.closed) {
      const payload = authCode
        ? { type: 'quantforge-fyers-auth-code', authCode, state }
        : { type: 'quantforge-fyers-auth-error', error: error || 'FYERS login did not return an auth code.' }

      window.opener.postMessage(payload, window.location.origin)
      setTimeout(() => window.close(), 250)
    }
  }, [])

  const { authCode, error } = readCallbackParams()

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'var(--bg-void)',
      color: 'var(--text-primary)',
      padding: 24,
      textAlign: 'center',
    }}>
      <div className="glass" style={{ maxWidth: 520, padding: 24 }}>
        <div style={{ fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 800, marginBottom: 8 }}>
          Fyers Broker Link
        </div>
        {authCode ? (
          <div style={{ color: 'var(--accent-green)', fontSize: 12, lineHeight: 1.6 }}>
            Login complete. Returning the FYERS auth code to QuantForge.
            If this window does not close automatically, you can close it now.
          </div>
        ) : (
          <div style={{ color: 'var(--accent-red)', fontSize: 12, lineHeight: 1.6 }}>
            {error || 'FYERS did not return an auth code.'}
            If QuantForge is still open, go back and try the broker link flow again.
          </div>
        )}
      </div>
    </div>
  )
}
