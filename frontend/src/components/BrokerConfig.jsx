import React, { useEffect, useRef, useState } from 'react'
import { Check, X, Loader, ExternalLink, Shield, Link as LinkIcon, Wifi, WifiOff, Save } from 'lucide-react'
import {
  validateBroker,
  getBrokerDefaults,
  createFyersLoginUrl,
  exchangeFyersAuthCode,
  saveFyersSession,
} from '../api/client'

const FYERS_CALLBACK_PATH = '/broker/fyers/callback'

const BROKERS = [
  {
    id: 'alpaca',
    name: 'Alpaca Markets',
    desc: 'US stocks & ETFs. Paper & live trading.',
    url: 'https://alpaca.markets',
    fields: [
      { key: 'api_key', label: 'API Key', placeholder: 'PK...' },
      { key: 'secret_key', label: 'Secret Key', placeholder: 'Your secret key', secret: true },
      { key: 'base_url', label: 'Base URL', placeholder: 'https://paper-api.alpaca.markets', optional: true },
    ],
  },
  {
    id: 'zerodha',
    name: 'Zerodha / Kite',
    desc: 'Indian markets (NSE/BSE). Requires Kite Connect subscription.',
    url: 'https://kite.trade',
    fields: [
      { key: 'api_key', label: 'Kite API Key', placeholder: 'Your Kite API key' },
      { key: 'secret_key', label: 'Access Token', placeholder: 'Session access token', secret: true },
    ],
  },
  {
    id: 'fyers',
    name: 'Fyers',
    desc: 'Indian markets & Crypto. Multi-asset trading platform.',
    url: 'https://fyers.in',
    fields: [
      { key: 'api_key', label: 'App ID', placeholder: 'Optional if set in .env' },
      { key: 'app_secret', label: 'Secret ID', placeholder: 'Optional if set in .env', secret: true },
      { key: 'redirect_uri', label: 'Redirect URL', placeholder: 'Required for the login tab flow' },
      { key: 'access_token', label: 'Access Token / Auth Code', placeholder: 'Paste token, auth code, or redirect URL', secret: true },
    ],
  },
]

const EMPTY_FIELDS = {
  api_key: '',
  secret_key: '',
  base_url: '',
  app_secret: '',
  redirect_uri: '',
  access_token: '',
}

function buildExpectedFyersRedirect() {
  if (typeof window === 'undefined') return ''
  return `${window.location.origin}${FYERS_CALLBACK_PATH}`
}

function isValidFyersRedirect(value) {
  if (!value) return false
  try {
    const url = new URL(value)
    return url.pathname.replace(/\/$/, '') === FYERS_CALLBACK_PATH
  } catch {
    return false
  }
}

function isAbsoluteHttpUrl(value) {
  if (!value) return false
  try {
    const url = new URL(value)
    return ['http:', 'https:'].includes(url.protocol)
  } catch {
    return false
  }
}

function parseFyersAuthCodeCandidate(value) {
  const input = (value || '').trim()
  if (!input) return { accessToken: '', authCode: '' }

  const readParams = (raw) => {
    const params = new URLSearchParams(raw)
    return params.get('auth_code') || params.get('code') || ''
  }

  if (isAbsoluteHttpUrl(input)) {
    try {
      const url = new URL(input)
      const authCode = readParams(url.search) || readParams((url.hash || '').replace(/^#/, ''))
      if (authCode) return { accessToken: '', authCode }
    } catch {
      // Ignore parse failures and fall through to raw token handling.
    }
  }

  const queryLike = input.replace(/^[?#]/, '')
  if (queryLike.includes('=')) {
    const authCode = readParams(queryLike)
    if (authCode) return { accessToken: '', authCode }
  }

  if (!input.includes('.') && !input.includes(':') && /^[A-Za-z0-9_-]+$/.test(input)) {
    return { accessToken: '', authCode: input }
  }

  return { accessToken: input, authCode: '' }
}

export default function BrokerConfig({ brokerConfig, onSave }) {
  const [selected, setSelected] = useState(brokerConfig?.broker || '')
  const [fields, setFields] = useState({
    ...EMPTY_FIELDS,
    api_key: brokerConfig?.api_key || '',
    secret_key: brokerConfig?.broker === 'fyers' ? '' : (brokerConfig?.secret_key || ''),
    base_url: brokerConfig?.base_url || '',
    app_secret: brokerConfig?.app_secret || '',
    redirect_uri: brokerConfig?.redirect_uri || '',
    access_token: brokerConfig?.broker === 'fyers' ? (brokerConfig?.secret_key || '') : '',
  })
  const [defaults, setDefaults] = useState(null)
  const [status, setStatus] = useState(null) // null | 'testing' | 'saving' | 'ok' | 'error'
  const [statusMsg, setStatusMsg] = useState('')
  const [linking, setLinking] = useState(false)
  const [pendingFyersState, setPendingFyersState] = useState('')
  const [pendingAuthRedirect, setPendingAuthRedirect] = useState('')
  const [manualAuthUrl, setManualAuthUrl] = useState('')
  const [liveStatus, setLiveStatus] = useState('unknown') // unknown | checking | online | offline
  const [liveMsg, setLiveMsg] = useState('')
  const [lastCheckedAt, setLastCheckedAt] = useState('')
  const lastSyncedRedirectRef = useRef(brokerConfig?.redirect_uri || '')

  const broker = BROKERS.find(b => b.id === selected)
  const fyersDefaults = defaults?.fyers || {}
  const expectedFyersRedirect = buildExpectedFyersRedirect()
  const resolvedFyersRedirect = (fields.redirect_uri || fyersDefaults.redirect_uri || expectedFyersRedirect || '').trim()
  const isCallbackRedirect = isValidFyersRedirect(resolvedFyersRedirect)
  const resolvedFyersApiKey = (fields.api_key || '').trim()
  const resolvedFyersAppSecret = (fields.app_secret || '').trim()
  const resolvedFyersAccessToken = (fields.access_token || '').trim()

  useEffect(() => {
    const loadDefaults = async () => {
      try {
        const res = await getBrokerDefaults()
        setDefaults(res)
      } catch {
        // Ignore refresh failures; the current form state still works.
      }
    }

    loadDefaults()
    const timer = window.setInterval(loadDefaults, 10000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    setSelected(brokerConfig?.broker || '')
    if (!brokerConfig) return
    lastSyncedRedirectRef.current = brokerConfig.redirect_uri || lastSyncedRedirectRef.current
    setFields(prev => ({
      ...prev,
      api_key: brokerConfig.api_key || '',
      secret_key: brokerConfig.broker === 'fyers' ? '' : (brokerConfig.secret_key || ''),
      base_url: brokerConfig.base_url || '',
      app_secret: brokerConfig.app_secret || '',
      redirect_uri: brokerConfig.redirect_uri || prev.redirect_uri,
      access_token: brokerConfig.broker === 'fyers' ? (brokerConfig.secret_key || '') : prev.access_token,
    }))
  }, [brokerConfig])

  useEffect(() => {
    if (selected !== 'fyers') return

    const nextRedirect = fyersDefaults.redirect_uri || expectedFyersRedirect

    if (
      nextRedirect &&
      (
        !fields.redirect_uri ||
        fields.redirect_uri === lastSyncedRedirectRef.current ||
        fields.redirect_uri === (brokerConfig?.broker === 'fyers' ? (brokerConfig.redirect_uri || '') : '')
      )
    ) {
      lastSyncedRedirectRef.current = nextRedirect
      setFields(prev => ({ ...prev, redirect_uri: nextRedirect }))
      return
    }

    if (nextRedirect) {
      lastSyncedRedirectRef.current = nextRedirect
    }
  }, [
    selected,
    fyersDefaults.redirect_uri,
    expectedFyersRedirect,
    fields.redirect_uri,
    brokerConfig?.broker,
    brokerConfig?.redirect_uri,
  ])

  const refreshDefaults = async () => {
    try {
      const res = await getBrokerDefaults()
      setDefaults(res)
      return res
    } catch {
      return defaults
    }
  }

  const applyConnectedStatus = (res, messageOverride = '') => {
    setStatus('ok')
    setStatusMsg(messageOverride || `Connected! ${res.user_name || res.account_id || res.user_id || ''}`.trim())
    setLiveStatus('online')
    setLiveMsg(res.user_name || res.account_id || res.user_id || 'Connected')
    setLastCheckedAt(new Date().toLocaleTimeString())
  }

  const applyDisconnectedStatus = (message) => {
    setStatus('error')
    setStatusMsg(message || 'Connection failed')
    setLiveStatus('offline')
    setLiveMsg(message || 'Disconnected')
    setLastCheckedAt(new Date().toLocaleTimeString())
  }

  const buildValidatePayload = (accessTokenOverride = '') => {
    if (selected === 'fyers') {
      return {
        broker: 'fyers',
        api_key: resolvedFyersApiKey,
        secret_key: accessTokenOverride || resolvedFyersAccessToken,
        base_url: '',
      }
    }

    return {
      broker: selected,
      api_key: (fields.api_key || '').trim(),
      secret_key: (fields.secret_key || '').trim(),
      base_url: (fields.base_url || '').trim(),
    }
  }

  const buildLiveValidatePayload = () => {
    if (selected !== 'fyers') return null

    if (brokerConfig?.broker === 'fyers' && brokerConfig?.secret_key) {
      return {
        broker: 'fyers',
        api_key: brokerConfig.api_key || '',
        secret_key: brokerConfig.secret_key,
        base_url: '',
      }
    }

    if (fyersDefaults.has_api_key && fyersDefaults.has_access_token) {
      return {
        broker: 'fyers',
        api_key: '',
        secret_key: '',
        base_url: '',
      }
    }

    return null
  }

  const resolveFyersCredentialInput = async (rawValue = '', options = {}) => {
    const input = (rawValue || '').trim()
    if (!input) return ''

    const { accessToken, authCode } = parseFyersAuthCodeCandidate(input)
    if (!authCode) return accessToken

    if (!options.silent) {
      setStatus('testing')
      setStatusMsg('Exchanging FYERS auth code for an access token...')
    }

    const tokenRes = await exchangeFyersAuthCode({
      auth_code: authCode,
      api_key: resolvedFyersApiKey,
      app_secret: resolvedFyersAppSecret,
      redirect_uri: resolvedFyersRedirect || expectedFyersRedirect,
    })

    const nextAccessToken = (tokenRes.access_token || '').trim()
    if (!nextAccessToken) {
      throw new Error('FYERS did not return an access token.')
    }

    setFields(prev => ({ ...prev, access_token: nextAccessToken }))
    return nextAccessToken
  }

  const canValidatePayload = (payload) => {
    if (!broker) return false
    if (selected === 'fyers') {
      return Boolean((payload.secret_key || fyersDefaults.has_access_token) && (payload.api_key || fyersDefaults.has_api_key))
    }
    return Boolean(payload.api_key && payload.secret_key)
  }

  const handleTest = async (accessTokenOverride = '', options = {}) => {
    let effectiveAccessToken = accessTokenOverride

    try {
      if (selected === 'fyers' && (accessTokenOverride || resolvedFyersAccessToken)) {
        effectiveAccessToken = await resolveFyersCredentialInput(accessTokenOverride || resolvedFyersAccessToken, options)
      }
    } catch (e) {
      const message = e.message || 'FYERS auth code exchange failed'
      if (!options.silent) {
        applyDisconnectedStatus(message)
      } else {
        setLiveStatus('offline')
        setLiveMsg(message)
        setLastCheckedAt(new Date().toLocaleTimeString())
      }
      return null
    }

    const payload = buildValidatePayload(effectiveAccessToken)
    if (!canValidatePayload(payload)) return null

    if (!options.silent) {
      setStatus('testing')
      setStatusMsg('')
    }

    try {
      const res = await validateBroker(payload)
      if (res.status === 'connected') {
        if (!options.silent) {
          applyConnectedStatus(res)
        } else {
          setLiveStatus('online')
          setLiveMsg(res.user_name || res.account_id || res.user_id || 'Connected')
          setLastCheckedAt(new Date().toLocaleTimeString())
        }
      } else if (!options.silent) {
        applyDisconnectedStatus(res.error || 'Connection failed')
      } else {
        setLiveStatus('offline')
        setLiveMsg(res.error || 'Disconnected')
        setLastCheckedAt(new Date().toLocaleTimeString())
      }
      return res
    } catch (e) {
      const message = e.message || 'Connection failed'
      if (!options.silent) {
        applyDisconnectedStatus(message)
      } else {
        setLiveStatus('offline')
        setLiveMsg(message)
        setLastCheckedAt(new Date().toLocaleTimeString())
      }
      return null
    }
  }

  useEffect(() => {
    const handleMessage = async (event) => {
      if (event.origin !== window.location.origin || selected !== 'fyers') return

      if (event.data?.type === 'quantforge-fyers-auth-error') {
        applyDisconnectedStatus(event.data.error || 'FYERS login failed.')
        setPendingFyersState('')
        return
      }

      if (event.data?.type !== 'quantforge-fyers-auth-code') return
      if (pendingFyersState && event.data.state && event.data.state !== pendingFyersState) return

      setStatus('testing')
      setStatusMsg('Exchanging FYERS auth code for an access token...')

      try {
        const tokenRes = await exchangeFyersAuthCode({
          auth_code: event.data.authCode,
          api_key: resolvedFyersApiKey,
          app_secret: resolvedFyersAppSecret,
          redirect_uri: pendingAuthRedirect || resolvedFyersRedirect || expectedFyersRedirect,
        })

        const accessToken = tokenRes.access_token || ''
        setFields(prev => ({ ...prev, access_token: accessToken }))
        const res = await handleTest(accessToken)
        if (res?.status === 'connected') {
          setStatusMsg('Connected. Click Save & Use to persist the token in .env and activate it in the app.')
        }
      } catch (e) {
        applyDisconnectedStatus(e.message)
      } finally {
        setPendingFyersState('')
        setPendingAuthRedirect('')
      }
    }

    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [
    selected,
    pendingFyersState,
    pendingAuthRedirect,
    resolvedFyersApiKey,
    resolvedFyersAppSecret,
    resolvedFyersRedirect,
    expectedFyersRedirect,
  ])

  useEffect(() => {
    if (selected !== 'fyers') {
      setLiveStatus('unknown')
      setLiveMsg('')
      return
    }

    const hasSavedSession = Boolean(
      (brokerConfig?.broker === 'fyers' && brokerConfig?.secret_key) ||
      (fyersDefaults.has_api_key && fyersDefaults.has_access_token)
    )

    if (!hasSavedSession) {
      setLiveStatus('unknown')
      setLiveMsg('No saved FYERS session')
      return
    }

    let active = true

    const pollStatus = async () => {
      if (!active) return
      const livePayload = buildLiveValidatePayload()
      if (!livePayload) {
        setLiveStatus('unknown')
        setLiveMsg('No saved FYERS session')
        return
      }
      setLiveStatus(prev => prev === 'online' || prev === 'offline' ? prev : 'checking')
      const res = await validateBroker(livePayload).catch(() => null)
      if (!active) return
      if (!res) {
        setLiveStatus('offline')
        setLiveMsg('Connection check failed')
        setLastCheckedAt(new Date().toLocaleTimeString())
      } else if (res.status === 'connected') {
        setLiveStatus('online')
        setLiveMsg(res.user_name || res.user_id || 'Connected')
        setLastCheckedAt(new Date().toLocaleTimeString())
      } else {
        setLiveStatus('offline')
        setLiveMsg(res.error || 'Disconnected')
        setLastCheckedAt(new Date().toLocaleTimeString())
      }
    }

    pollStatus()
    const timer = window.setInterval(pollStatus, 30000)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [
    selected,
    brokerConfig?.broker,
    brokerConfig?.secret_key,
    fyersDefaults.has_api_key,
    fyersDefaults.has_access_token,
  ])

  const handleFyersLink = async () => {
    setLinking(true)
    setStatus(null)
    setStatusMsg('')
    setManualAuthUrl('')

    const redirectUri = resolvedFyersRedirect || expectedFyersRedirect
    const callbackReady = isValidFyersRedirect(redirectUri)
    const authTab = window.open('', '_blank')

    try {
      if (!isAbsoluteHttpUrl(redirectUri)) {
        throw new Error('FYERS Redirect URL must be a valid absolute http/https URL.')
      }

      const res = await createFyersLoginUrl({
        api_key: resolvedFyersApiKey,
        app_secret: resolvedFyersAppSecret,
        redirect_uri: redirectUri,
      })
      setPendingFyersState(callbackReady ? res.state : '')
      setPendingAuthRedirect(callbackReady ? redirectUri : '')

      if (!authTab) {
        setManualAuthUrl(res.auth_url)
        setStatus('error')
        setStatusMsg('Browser blocked the FYERS login tab. Use Open FYERS Login below.')
      } else {
        authTab.location.href = res.auth_url
        authTab.focus()
        setStatus('ok')
        setStatusMsg(
          callbackReady
            ? 'FYERS login opened in a new tab. Complete sign-in there and QuantForge will fill the access token automatically.'
            : `FYERS login opened in a new tab using ${redirectUri}. Complete sign-in there, then paste the redirect URL, auth code, or access token here and click Save & Use.`
        )
      }
    } catch (e) {
      if (authTab) {
        authTab.close()
      }
      applyDisconnectedStatus(e.message)
    } finally {
      setLinking(false)
    }
  }

  const handleSaveAndUse = async () => {
    if (!broker || status === 'testing' || status === 'saving') return

    setStatus('saving')
    setStatusMsg(selected === 'fyers' ? 'Validating and saving FYERS session...' : 'Validating broker credentials...')

    let fyersAccessTokenToSave = resolvedFyersAccessToken
    if (selected === 'fyers' && resolvedFyersAccessToken) {
      try {
        fyersAccessTokenToSave = await resolveFyersCredentialInput(resolvedFyersAccessToken)
      } catch (e) {
        applyDisconnectedStatus(e.message || 'FYERS auth code exchange failed')
        return
      }
    }

    const nextConfig = selected === 'fyers'
      ? {
          broker: 'fyers',
          api_key: resolvedFyersApiKey,
          secret_key: fyersAccessTokenToSave,
          base_url: '',
          app_secret: resolvedFyersAppSecret,
          redirect_uri: resolvedFyersRedirect || expectedFyersRedirect,
        }
      : {
          broker: selected,
          api_key: (fields.api_key || '').trim(),
          secret_key: (fields.secret_key || '').trim(),
          base_url: (fields.base_url || '').trim(),
        }

    if (selected === 'fyers') {
      try {
        const redirectUri = nextConfig.redirect_uri
        if (!isAbsoluteHttpUrl(redirectUri)) {
          throw new Error('FYERS Redirect URL must be a valid absolute http/https URL.')
        }

        if (!fyersAccessTokenToSave && !fyersDefaults.has_access_token) {
          throw new Error('FYERS access token is required before the session can be saved.')
        }

        if (!resolvedFyersAppSecret && !fyersDefaults.has_secret_key) {
          throw new Error('FYERS Secret ID is required before the token can be saved to .env.')
        }

        if (fyersAccessTokenToSave) {
          setStatusMsg('Saving FYERS session to .env...')
          await saveFyersSession({
            api_key: resolvedFyersApiKey,
            app_secret: resolvedFyersAppSecret,
            redirect_uri: redirectUri,
            access_token: fyersAccessTokenToSave,
          })
        }
        await refreshDefaults()

        const validationPayload = buildValidatePayload(fyersAccessTokenToSave)
        if (!canValidatePayload(validationPayload)) {
          throw new Error('Required broker credentials are missing.')
        }

        setStatusMsg('FYERS session saved. Validating live broker connection...')
        const validation = await validateBroker(validationPayload).catch((e) => ({ status: 'error', error: e.message }))
        if (!validation || validation.status !== 'connected') {
          setStatus('error')
          setStatusMsg(`FYERS token saved to .env, but live validation failed: ${validation?.error || 'Connection failed'}`)
          return
        }

        onSave?.(nextConfig)
        applyConnectedStatus(
          validation,
          isValidFyersRedirect(redirectUri)
            ? (
                fyersAccessTokenToSave
                  ? 'FYERS connected. Access token saved to .env and active in this session.'
                  : 'FYERS connected using the saved .env token and active in this session.'
              )
            : (
                fyersAccessTokenToSave
                  ? 'FYERS connected. Access token saved to .env and active in this session. Link Broker will keep using your saved redirect URL.'
                  : 'FYERS connected using the saved .env token and your saved redirect URL.'
              )
        )
      } catch (e) {
        onSave?.(nextConfig)
        setStatus('error')
        setStatusMsg(`FYERS connected for this session, but saving to .env failed: ${e.message}`)
      }
      return
    }

    onSave?.(nextConfig)
    applyConnectedStatus(validation, 'Broker connected and loaded for the current session.')
  }

  const liveBadge = liveStatus === 'online'
    ? { icon: <Wifi size={12} />, color: 'var(--accent-green)', label: 'LIVE' }
    : liveStatus === 'offline'
      ? { icon: <WifiOff size={12} />, color: 'var(--accent-red)', label: 'OFFLINE' }
      : { icon: <Loader size={12} className={liveStatus === 'checking' ? 'spin' : ''} />, color: 'var(--text-muted)', label: liveStatus === 'checking' ? 'CHECKING' : 'UNKNOWN' }

  const canTest = selected === 'fyers'
    ? Boolean((resolvedFyersAccessToken || fyersDefaults.has_access_token) && (resolvedFyersApiKey || fyersDefaults.has_api_key))
    : Boolean((fields.api_key || '').trim() && (fields.secret_key || '').trim())

  const canLinkFyers = Boolean(
    selected === 'fyers' &&
    (resolvedFyersApiKey || fyersDefaults.has_api_key) &&
    (resolvedFyersAppSecret || fyersDefaults.has_secret_key) &&
    isAbsoluteHttpUrl(resolvedFyersRedirect || expectedFyersRedirect)
  )

  const canSave = selected === 'fyers'
    ? Boolean(
        (resolvedFyersAccessToken || fyersDefaults.has_access_token) &&
        (resolvedFyersApiKey || fyersDefaults.has_api_key) &&
        (resolvedFyersAppSecret || fyersDefaults.has_secret_key) &&
        isAbsoluteHttpUrl(resolvedFyersRedirect || expectedFyersRedirect)
      )
    : Boolean((fields.api_key || '').trim() && (fields.secret_key || '').trim())

  return (
    <div style={{ maxWidth: 760, margin: '0 auto' }} className="animate-fade">
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 800, marginBottom: 6 }}>
          Broker Connection
        </div>
        <div style={{ color: 'var(--text-muted)', fontSize: 12, lineHeight: 1.6 }}>
          Connect your broker for live data and potential order routing.
          FYERS access tokens can now be saved in `.env` and reused until they expire.
        </div>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          marginTop: 10, fontSize: 10, color: 'var(--accent-amber)',
        }}>
          <Shield size={11} />
          <span>Broker connection is optional. yfinance remains the default for backtesting.</span>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 20 }}>
        {BROKERS.map(b => (
          <button
            key={b.id}
            onClick={() => { setSelected(b.id); setStatus(null); setStatusMsg(''); setManualAuthUrl('') }}
            style={{
              background: selected === b.id ? 'var(--accent-blue-dim)' : 'var(--bg-surface)',
              border: `1px solid ${selected === b.id ? 'var(--accent-blue)' : 'var(--border)'}`,
              borderRadius: 10,
              padding: '14px 16px',
              cursor: 'pointer',
              textAlign: 'left',
              transition: 'all 0.15s',
            }}
          >
            <div style={{
              fontFamily: 'var(--font-display)',
              fontSize: 13,
              fontWeight: 700,
              color: selected === b.id ? 'var(--accent-blue)' : 'var(--text-primary)',
              marginBottom: 4,
            }}>
              {b.name}
            </div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', lineHeight: 1.5 }}>{b.desc}</div>
            <a
              href={b.url}
              target="_blank"
              rel="noreferrer"
              style={{ fontSize: 9, color: 'var(--accent-blue)', display: 'inline-flex', alignItems: 'center', gap: 3, marginTop: 6 }}
              onClick={e => e.stopPropagation()}
            >
              <ExternalLink size={8} /> {b.url.replace('https://', '')}
            </a>
          </button>
        ))}
      </div>

      {broker && (
        <form
          className="glass"
          style={{ padding: 20, marginBottom: 16 }}
          onSubmit={(e) => {
            e.preventDefault()
            handleSaveAndUse()
          }}
        >
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 12,
            marginBottom: 16,
            flexWrap: 'wrap',
          }}>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 700, color: 'var(--accent-blue)' }}>
              {broker.name} — Connection Setup
            </div>
            {selected === 'fyers' && (
              <div style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                padding: '6px 10px',
                borderRadius: 999,
                background: 'rgba(255,255,255,0.04)',
                border: '1px solid var(--border)',
                fontSize: 10,
                color: liveBadge.color,
              }}>
                {liveBadge.icon}
                <span>Broker {liveBadge.label}</span>
                {lastCheckedAt && <span style={{ color: 'var(--text-muted)' }}>· {lastCheckedAt}</span>}
              </div>
            )}
          </div>

          {selected === 'fyers' && (
            <div style={{
              marginBottom: 16,
              padding: '12px 14px',
              borderRadius: 8,
              background: 'rgba(59,130,246,0.10)',
              border: '1px solid rgba(59,130,246,0.25)',
              fontSize: 11,
              color: 'var(--text-secondary)',
              lineHeight: 1.65,
            }}>
              <div style={{ color: 'var(--text-primary)', marginBottom: 6, fontWeight: 700 }}>Recommended FYERS flow</div>
              <div>1. Put `FYERS_APP_ID`, `FYERS_SECRET_KEY`, and a redirect URL in `.env` if you want a permanent setup.</div>
              <div>2. Click <strong style={{ color: 'var(--text-primary)' }}>Link Broker</strong> to open FYERS in a new tab using the redirect URL currently configured below.</div>
              <div>3. If that redirect ends with <strong style={{ color: 'var(--text-primary)' }}>{FYERS_CALLBACK_PATH}</strong>, QuantForge fills the access token automatically after login.</div>
              <div>4. If you use another redirect URL like `https://www.google.com`, finish login there, then paste the redirect URL, auth code, or access token here and press <strong style={{ color: 'var(--text-primary)' }}>Enter</strong> or click <strong style={{ color: 'var(--text-primary)' }}>Save &amp; Use</strong>.</div>
              <div style={{ marginTop: 8 }}>
                .env status:
                {' '}
                App ID {fyersDefaults.has_api_key ? 'configured' : 'missing'}
                {' · '}
                Secret ID {fyersDefaults.has_secret_key ? 'configured' : 'missing'}
                {' · '}
                Access Token {fyersDefaults.has_access_token ? 'stored' : 'missing'}
                {' · '}
                Redirect URL {
                  fyersDefaults.redirect_uri_valid
                    ? `${fyersDefaults.redirect_uri || 'missing'} (callback-ready)`
                    : fyersDefaults.redirect_uri_absolute
                      ? `${fyersDefaults.redirect_uri || 'missing'} (manual-token mode)`
                      : 'missing'
                }
              </div>
              {!isCallbackRedirect && expectedFyersRedirect && (
                <div style={{ marginTop: 8, color: 'var(--accent-amber)' }}>
                  This saved redirect URL will be used by Link Broker exactly as shown. QuantForge can only auto-fill the access token if you switch it to {expectedFyersRedirect}.
                </div>
              )}
              {liveMsg && (
                <div style={{ marginTop: 8, color: liveStatus === 'online' ? 'var(--accent-green)' : 'var(--text-secondary)' }}>
                  Live status: {liveMsg}
                </div>
              )}
            </div>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {broker.fields.map(f => (
              <div key={f.key} className="form-group">
                <label className="form-label">
                  {f.label}
                  {f.optional && <span style={{ color: 'var(--text-muted)', marginLeft: 4 }}>(optional)</span>}
                </label>
                <input
                  type={f.secret ? 'password' : 'text'}
                  className="form-input"
                  placeholder={f.key === 'redirect_uri' && expectedFyersRedirect ? expectedFyersRedirect : f.placeholder}
                  value={fields[f.key] || ''}
                  onChange={e => {
                    const value = e.target.value
                    setFields(prev => ({ ...prev, [f.key]: value }))
                    if (status && status !== 'testing' && status !== 'saving') {
                      setStatus(null)
                      setStatusMsg('')
                    }
                  }}
                />
              </div>
            ))}
          </div>

          {manualAuthUrl && (
            <div style={{
              marginTop: 14,
              padding: '10px 14px',
              borderRadius: 8,
              background: 'rgba(245,158,11,0.10)',
              border: '1px solid rgba(245,158,11,0.30)',
              fontSize: 11,
              color: 'var(--text-secondary)',
              lineHeight: 1.6,
            }}>
              Browser blocked the automatic FYERS tab. Open it manually:
              {' '}
              <a href={manualAuthUrl} target="_blank" rel="noreferrer" style={{ color: 'var(--accent-blue)' }}>
                Open FYERS Login
              </a>
            </div>
          )}

          {status && status !== 'testing' && status !== 'saving' && (
            <div style={{
              marginTop: 14,
              padding: '10px 14px',
              borderRadius: 8,
              background: status === 'ok' ? 'var(--accent-green-dim)' : 'var(--accent-red-dim)',
              border: `1px solid ${status === 'ok' ? 'rgba(0,255,170,0.3)' : 'rgba(239,68,68,0.3)'}`,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              fontSize: 11,
              color: status === 'ok' ? 'var(--accent-green)' : 'var(--accent-red)',
            }}>
              {status === 'ok' ? <Check size={13} /> : <X size={13} />}
              {statusMsg}
            </div>
          )}

          {(status === 'testing' || status === 'saving') && (
            <div style={{
              marginTop: 14,
              padding: '10px 14px',
              borderRadius: 8,
              background: 'rgba(59,130,246,0.10)',
              border: '1px solid rgba(59,130,246,0.25)',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              fontSize: 11,
              color: 'var(--text-primary)',
            }}>
              <Loader size={13} className="spin" />
              {statusMsg || (status === 'saving' ? 'Saving broker session...' : 'Testing broker connection...')}
            </div>
          )}

          <div style={{ display: 'flex', gap: 10, marginTop: 16, flexWrap: 'wrap' }}>
            {selected === 'fyers' && (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleFyersLink}
                disabled={linking || !canLinkFyers}
              >
                {linking
                  ? <><Loader size={12} className="spin" /> Preparing login...</>
                  : <><LinkIcon size={13} /> Link Broker</>
                }
              </button>
            )}

            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => handleTest()}
              disabled={status === 'testing' || status === 'saving' || !canTest}
            >
              {status === 'testing'
                ? <><div className="spinner" style={{ width: 12, height: 12, borderWidth: 1.5 }} /> Testing...</>
                : 'Test Connection'
              }
            </button>

            <button
              type="submit"
              className="btn btn-primary"
              disabled={status === 'testing' || status === 'saving' || !canSave}
            >
              {status === 'saving'
                ? <><Loader size={12} className="spin" /> Saving...</>
                : <><Save size={13} /> Save &amp; Use</>
              }
            </button>
          </div>
        </form>
      )}

      {brokerConfig?.broker && (
        <div style={{
          background: liveStatus === 'offline' ? 'var(--accent-red-dim)' : 'var(--accent-green-dim)',
          border: `1px solid ${liveStatus === 'offline' ? 'rgba(239,68,68,0.3)' : 'var(--border-accent)'}`,
          borderRadius: 8,
          padding: '10px 14px',
          fontSize: 11,
          color: liveStatus === 'offline' ? 'var(--accent-red)' : 'var(--accent-green)',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}>
          {liveStatus === 'offline' ? <WifiOff size={13} /> : <Check size={13} />}
          Active broker: <strong>{brokerConfig.broker.toUpperCase()}</strong>
          <span style={{ color: 'var(--text-muted)' }}>· {liveStatus === 'offline' ? 'connection lost or token expired' : 'configuration loaded'}</span>
        </div>
      )}
    </div>
  )
}
