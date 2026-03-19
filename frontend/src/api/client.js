import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 60000,
})

api.interceptors.response.use(
  res => res.data,
  err => {
    const msg = err.response?.data?.detail || err.message || 'Unknown error'
    return Promise.reject(new Error(msg))
  }
)

export default api

// ─── Backtest ───────────────────────────────────────────────

export const startBacktest = (payload) => api.post('/backtest', payload)
export const getBacktestStatus = (id) => api.get(`/backtest/${id}/status`)
export const getBacktestResults = (id) => api.get(`/backtest/${id}/results`)

// ─── Download ───────────────────────────────────────────────

export const startDownload = (payload) => api.post('/download-data', payload)
export const getDownloadStatus = (id) => api.get(`/download-data/${id}/status`)
export const getDownloadCsvUrl = (id) => `/api/download-data/${id}/csv`

// ─── Meta ────────────────────────────────────────────────────

export const getSymbols = () => api.get('/symbols')
export const getSampleData = () => api.get('/sample-data')
export const getSampleCsvUrl = (filename) => `/api/sample-data/${filename}`
export const validateBroker = (payload) => api.post('/validate-broker', payload)
export const getBrokerDefaults = () => api.get('/broker/defaults')
export const createFyersLoginUrl = (payload) => api.post('/broker/fyers/login-url', payload)
export const exchangeFyersAuthCode = (payload) => api.post('/broker/fyers/exchange-token', payload)
export const saveFyersSession = (payload) => api.post('/broker/fyers/save-session', payload)
export const healthCheck = () => api.get('/health')

// ─── History ─────────────────────────────────────────────────

export const getHistory = (limit = 50) => api.get('/history', { params: { limit } })
export const getHistoryDetails = (id) => api.get(`/history/${id}`)

// ─── Upload ──────────────────────────────────────────────────

export const uploadCsv = (file) => {
  const formData = new FormData()
  formData.append('file', file)
  return api.post('/upload-csv', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}
