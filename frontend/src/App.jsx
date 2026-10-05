import { useState, useEffect, useRef, useCallback } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import jsQR from 'jsqr'
import QRCode from 'qrcode'

// API helper
const api = (path, opts) =>
  fetch(path, opts).then(async r => {
    if (!r.ok) {
      const e = await r.json().catch(() => ({}))
      return Promise.reject(e.detail || e.message || JSON.stringify(e))
    }
    return r.json()
  })

const STORAGE_KEY = 'ql_patient_token'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<PatientApp />} />
        <Route path="/manager" element={<ManagerApp />} />
      </Routes>
    </BrowserRouter>
  )
}

function PatientApp() {
  const [screen, setScreen] = useState('init')
  const [services, setServices] = useState([])
  const [tokenCode, setTokenCode] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) { setTokenCode(saved); setScreen('status') }
    else setScreen('scanner')
  }, [])

  const handleQrScanned = async (rawToken) => {
    setError('')
    try {
      const data = await api(`/api/qr/validate/${rawToken}`)
      setServices(data.services || [])
      setScreen('register')
    } catch (e) {
      setError(String(e))
      setTimeout(() => setError(''), 3500)
    }
  }

  const handleRegistered = (code) => {
    localStorage.setItem(STORAGE_KEY, code)
    setTokenCode(code)
    setScreen('status')
  }

  const handleDone = () => {
    localStorage.removeItem(STORAGE_KEY)
    setTokenCode(null)
    setScreen('scanner')
  }

  return (
    <div className="patient-app">
      <header className="patient-header">
        <div className="patient-logo">
          <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
            <circle cx="14" cy="14" r="14" fill="url(#lg)" />
            <path d="M9 14l3.5 3.5L19 10" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
            <defs><linearGradient id="lg" x1="0" y1="0" x2="28" y2="28"><stop stopColor="#6366f1"/><stop offset="1" stopColor="#8b5cf6"/></linearGradient></defs>
          </svg>
          <span>QueueLess</span>
        </div>
        <div className="clinic-name">CityCare Diagnostic Centre</div>
      </header>
      <main className="patient-main">
        {error && <div className="patient-error">{error}</div>}
        {screen === 'init' && <div className="center-screen"><div className="spinner" /></div>}
        {screen === 'scanner' && <QRScanner onScan={handleQrScanned} />}
        {screen === 'register' && <RegisterForm services={services} onRegistered={handleRegistered} onBack={() => setScreen('scanner')} />}
        {screen === 'status' && tokenCode && <PatientStatus tokenCode={tokenCode} onDone={handleDone} onError={(e) => { setError(e); setTimeout(() => setError(''), 4000) }} />}
      </main>
    </div>
  )
}

function QRScanner({ onScan }) {
  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const rafRef = useRef(null)
  const streamRef = useRef(null)
  const scannedRef = useRef(false)
  const [camReady, setCamReady] = useState(false)
  const [permDenied, setPermDenied] = useState(false)
  const [camError, setCamError] = useState('')

  useEffect(() => {
    let active = true
    scannedRef.current = false
    const startCamera = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment', width: { ideal: 640 }, height: { ideal: 480 } } })
        if (!active) { stream.getTracks().forEach(t => t.stop()); return }
        streamRef.current = stream
        if (videoRef.current) { videoRef.current.srcObject = stream; videoRef.current.play(); setCamReady(true) }
      } catch (e) {
        if (!active) return
        if (e.name === 'NotAllowedError') setPermDenied(true)
        else setCamError('Camera error: ' + e.message)
      }
    }
    startCamera()
    return () => { active = false; if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop()); if (rafRef.current) cancelAnimationFrame(rafRef.current) }
  }, [])

  const tick = useCallback(() => {
    if (scannedRef.current) return
    const video = videoRef.current
    const canvas = canvasRef.current
    if (!video || !canvas || video.readyState !== video.HAVE_ENOUGH_DATA) { rafRef.current = requestAnimationFrame(tick); return }
    const ctx = canvas.getContext('2d')
    canvas.width = video.videoWidth; canvas.height = video.videoHeight
    ctx.drawImage(video, 0, 0)
    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height)
    const code = jsQR(imageData.data, imageData.width, imageData.height, { inversionAttempts: 'dontInvert' })
    if (code && code.data) {
      scannedRef.current = true
      if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop())
      onScan(code.data)
    } else { rafRef.current = requestAnimationFrame(tick) }
  }, [onScan])

  useEffect(() => {
    if (camReady) rafRef.current = requestAnimationFrame(tick)
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current) }
  }, [camReady, tick])

  if (permDenied) return <div className="scanner-wrap"><div className="scanner-card"><div className="scanner-icon">📷</div><h2>Camera Access Required</h2><p className="scanner-hint">Please allow camera access in your browser settings to scan your registration QR code.</p></div></div>
  if (camError) return <div className="scanner-wrap"><div className="scanner-card"><div className="scanner-icon">⚠️</div><h2>Camera Error</h2><p className="scanner-hint">{camError}</p></div></div>

  return (
    <div className="scanner-wrap">
      <div className="scanner-card">
        <div className="scanner-title"><span className="scanner-pulse" />Scan Your Registration QR</div>
        <p className="scanner-hint">Point your camera at the QR code displayed at the reception desk</p>
        <div className="viewfinder-wrap">
          <video ref={videoRef} className="viewfinder-video" playsInline muted />
          <canvas ref={canvasRef} className="viewfinder-canvas" />
          <div className="viewfinder-corners"><div className="corner tl" /><div className="corner tr" /><div className="corner bl" /><div className="corner br" /></div>
          {!camReady && <div className="viewfinder-loading"><div className="spinner" /><span>Starting camera...</span></div>}
        </div>
        <div className="scanner-footer">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="#6366f1"><path d="M2 2h4v4H2V2zm8 0h4v4h-4V2zM2 10h4v4H2v-4zm8 2h2v2h-2v-2zm2-2h2v2h-2v-2zm-2-2h2v2h-2V8zm2 0h2v2h-2V8z"/></svg>
          Ask reception for your QR code
        </div>
      </div>
    </div>
  )
}

function RegisterForm({ services, onRegistered, onBack }) {
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [service, setService] = useState(services[0]?.code || '')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const submit = async () => {
    if (!name.trim()) { setError('Please enter your name'); return }
    if (!service) { setError('Please select a service'); return }
    setError(''); setLoading(true)
    try {
      const result = await api('/api/tokens', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ patient_name: name.trim(), service_code: service, phone: phone.trim() || null, is_walk_in: false, priority: 0 })
      })
      onRegistered(result.code)
    } catch (e) { setError(String(e)) }
    finally { setLoading(false) }
  }

  return (
    <div className="register-wrap">
      <div className="register-card">
        <div className="register-check">✓</div>
        <h2 className="register-title">QR Verified!</h2>
        <p className="register-sub">Enter your details to join the queue</p>
        {error && <div className="form-error">{error}</div>}
        <div className="form-field">
          <label htmlFor="reg-name">Full Name *</label>
          <input id="reg-name" type="text" value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Anita Sharma" autoFocus onKeyDown={e => e.key === 'Enter' && submit()} />
        </div>
        <div className="form-field">
          <label htmlFor="reg-phone">Phone Number (optional)</label>
          <input id="reg-phone" type="tel" value={phone} onChange={e => setPhone(e.target.value)} placeholder="e.g. 9876543210" />
        </div>
        <div className="form-field">
          <label>Service Required *</label>
          <div className="service-pills">
            {services.map(s => (
              <button key={s.code} type="button" className={`service-pill ${service === s.code ? 'active' : ''}`} onClick={() => setService(s.code)}>{s.name}</button>
            ))}
          </div>
        </div>
        <button id="btn-join-queue" className="btn-register" onClick={submit} disabled={loading || !name.trim() || !service}>
          {loading ? <><span className="btn-spinner" />Joining queue...</> : '→ Join Queue'}
        </button>
        <button className="btn-back" onClick={onBack}>← Scan Again</button>
      </div>
    </div>
  )
}

function PatientStatus({ tokenCode, onDone, onError }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState(null)

  const fetchStatus = useCallback(async () => {
    try {
      const t = await api(`/api/tokens/${tokenCode}`)
      setData(t); setLastUpdated(new Date()); setLoading(false)
    } catch (e) { setLoading(false); onError('Could not load status: ' + e) }
  }, [tokenCode])

  useEffect(() => {
    fetchStatus()
    const t = setInterval(fetchStatus, 3000)
    return () => clearInterval(t)
  }, [fetchStatus])

  if (loading) return <div className="center-screen"><div className="spinner" /><p style={{ color: '#a78bfa', marginTop: 16 }}>Loading your status...</p></div>
  if (!data) return null

  const isDone = data.status === 'completed' || data.status === 'no_show'
  const isBeingCalled = data.status === 'called'
  const isInService = data.status === 'in_service'
  const statusConfig = {
    waiting:    { label: 'Waiting',    color: '#f59e0b', bg: 'rgba(245,158,11,0.1)',  icon: '⏳' },
    called:     { label: 'Your Turn!', color: '#f97316', bg: 'rgba(249,115,22,0.15)', icon: '📣' },
    in_service: { label: 'In Service', color: '#22c55e', bg: 'rgba(34,197,94,0.1)',   icon: '✅' },
    completed:  { label: 'Completed',  color: '#6366f1', bg: 'rgba(99,102,241,0.1)',  icon: '🎉' },
    no_show:    { label: 'Missed',     color: '#ef4444', bg: 'rgba(239,68,68,0.1)',    icon: '❌' },
    skipped:    { label: 'Skipped',    color: '#8b5cf6', bg: 'rgba(139,92,246,0.1)',  icon: '⏭️' },
  }
  const sc = statusConfig[data.status] || statusConfig.waiting

  const waitMsg = (() => {
    if (isDone) return null
    if (isInService) return 'Being served now'
    if (isBeingCalled) return `Please go to Counter ${data.counter_code || ''} now`
    if (data.position === 1) return 'You are next!'
    if (data.position > 1) {
      const mins = data.eta_min != null ? ` · ~${data.eta_min}–${data.eta_max} min` : ''
      return `${data.position - 1} patient${data.position - 1 > 1 ? 's' : ''} ahead${mins}`
    }
    return data.eta_text || null
  })()

  return (
    <div className="status-wrap">
      {isBeingCalled && <div className="call-banner">📣 Please proceed to {data.counter_code ? `Counter ${data.counter_code}` : 'the counter'}!</div>}
      <div className="status-card" style={{ borderColor: sc.color + '55' }}>
        <div className="token-hero">
          <div className="token-num">{data.code}</div>
          <div className="token-name">{data.patient_name}</div>
          <div className="token-service">{data.service_name}</div>
        </div>
        <div className="status-badge-wrap" style={{ background: sc.bg }}>
          <span className="status-icon">{sc.icon}</span>
          <span className="status-label" style={{ color: sc.color }}>{sc.label}</span>
        </div>
        {!isDone && waitMsg && (
          <div className="wait-info-box">
            {data.counter_code && !isBeingCalled && <div className="wait-counter">Counter {data.counter_code}</div>}
            <div className="wait-message">{waitMsg}</div>
          </div>
        )}
        {data.last_change_reason && <div className="status-note">💬 {data.last_change_reason}</div>}
        {isDone && (
          <div className="done-section">
            <p className="done-text">{data.status === 'completed' ? 'Your visit is complete. Thank you for visiting!' : 'This token was marked as no-show. Please contact reception.'}</p>
            <button id="btn-register-again" className="btn-new" onClick={onDone}>Register Again</button>
          </div>
        )}
        {lastUpdated && (
          <div className="last-updated">
            <span className="live-dot" />
            Live · {lastUpdated.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </div>
        )}
      </div>
    </div>
  )
}

function ManagerApp() {
  const [tab, setTab] = useState('queue')
  const [queueData, setQueueData] = useState(null)
  const [online, setOnline] = useState(false)

  const refresh = useCallback(async () => {
    try { const d = await api('/api/queue'); setQueueData(d); setOnline(true) }
    catch { setOnline(false) }
  }, [])

  useEffect(() => { refresh(); const t = setInterval(refresh, 3000); return () => clearInterval(t) }, [refresh])

  const counters = queueData?.counters || []
  const tokens   = queueData?.tokens   || []
  const stats    = queueData?.stats    || {}

  return (
    <div className="manager-app">
      <header className="manager-topbar">
        <div className="manager-logo">
          <svg width="24" height="24" viewBox="0 0 28 28" fill="none">
            <circle cx="14" cy="14" r="14" fill="url(#mlg)" />
            <path d="M9 14l3.5 3.5L19 10" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
            <defs><linearGradient id="mlg" x1="0" y1="0" x2="28" y2="28"><stop stopColor="#6366f1"/><stop offset="1" stopColor="#8b5cf6"/></linearGradient></defs>
          </svg>
          <span className="manager-logo-text">QueueLess</span>
          <span className="manager-badge">Manager</span>
        </div>
        <div className="manager-stats">
          {stats.total !== undefined && <>
            <div className="mstat"><span>{stats.waiting ?? 0}</span>Waiting</div>
            <div className="mstat mstat-orange"><span>{stats.called ?? 0}</span>Called</div>
            <div className="mstat mstat-green"><span>{stats.in_service ?? 0}</span>In Service</div>
            <div className="mstat mstat-dim"><span>{stats.completed ?? 0}</span>Done</div>
          </>}
        </div>
        <div className={`manager-dot ${online ? 'online' : 'offline'}`} title={online ? 'Connected' : 'Offline'} />
      </header>
      <nav className="manager-tabs">
        {[['queue', '📋 Queue'], ['qr', '📲 QR Code']].map(([k, label]) => (
          <button key={k} id={`tab-${k}`} className={`manager-tab ${tab === k ? 'active' : ''}`} onClick={() => setTab(k)}>{label}</button>
        ))}
      </nav>
      <div className="manager-content">
        {tab === 'queue' && <QueueTab counters={counters} tokens={tokens} onRefresh={refresh} />}
        {tab === 'qr'    && <QRTab />}
      </div>
    </div>
  )
}

function QueueTab({ counters, tokens, onRefresh }) {
  const [busy, setBusy] = useState({})

  const action = async (url, key) => {
    setBusy(p => ({ ...p, [key]: true }))
    try { await api(url, { method: 'POST' }); await onRefresh() }
    catch (e) { alert('Error: ' + e) }
    finally { setBusy(p => ({ ...p, [key]: false })) }
  }

  const activeTokens   = tokens.filter(t => !['completed','no_show','skipped'].includes(t.status))
  const archivedTokens = tokens.filter(t => ['completed','no_show','skipped'].includes(t.status))

  return (
    <div className="queue-tab">
      <div className="section-header">Counters</div>
      <div className="counters-row">
        {counters.map(c => (
          <div key={c.code} className={`counter-tile ${c.is_open ? 'open' : 'closed'}`}>
            <div className="counter-tile-head">
              <div>
                <span className="counter-code">Counter {c.code}</span>
                <span className={`counter-badge ${c.is_open ? 'badge-open' : 'badge-closed'}`}>{c.is_open ? 'OPEN' : 'CLOSED'}</span>
              </div>
              <div className="counter-tile-stats">
                <span className="ct-stat-inline"><b>{c.waiting_count}</b> waiting</span>
                {c.current_token && <span className="ct-serving">→ {c.current_token}</span>}
              </div>
            </div>
            <div className="counter-tile-actions">
              {c.is_open && (
                <button
                  id={`btn-advance-${c.code}`}
                  className="btn-action btn-purple"
                  onClick={() => action(`/api/counters/${c.code}/advance`, `adv-${c.code}`)}
                  disabled={busy[`adv-${c.code}`] || (c.waiting_count === 0 && !c.current_token)}
                  title="Complete current patient and serve next"
                >
                  {busy[`adv-${c.code}`] ? '...' : '▶ Next Patient'}
                </button>
              )}
              {c.is_open
                ? <button id={`btn-close-${c.code}`} className="btn-action btn-red" onClick={() => action(`/api/counters/${c.code}/close`, `close-${c.code}`)}>Close</button>
                : <button id={`btn-open-${c.code}`} className="btn-action btn-green" onClick={() => action(`/api/counters/${c.code}/open`, `open-${c.code}`)}>Open</button>}
            </div>
          </div>
        ))}
      </div>

      <div className="section-header" style={{ marginTop: 24 }}>
        Active Queue <span className="section-count">{activeTokens.length}</span>
      </div>
      {activeTokens.length === 0 ? (
        <div className="empty-queue">No active patients in queue</div>
      ) : (
        <div className="queue-list">
          {activeTokens.map(t => {
            const smap = {
              waiting:    { label: 'Waiting',    cls: 'sq-waiting'   },
              called:     { label: 'Called',     cls: 'sq-called'    },
              in_service: { label: 'In Service', cls: 'sq-inservice' },
            }
            const sm = smap[t.status] || smap.waiting
            return (
              <div key={t.code} className={`queue-row ${t.status === 'in_service' ? 'row-inservice' : ''}`}>
                <div className="qr-token">{t.code}</div>
                <div className="qr-info">
                  <div className="qr-name">{t.patient_name}</div>
                  <div className="qr-service">{t.service_name}{t.counter_code ? ` · Counter ${t.counter_code}` : ''}</div>
                </div>
                <div className={`qr-status ${sm.cls}`}>{sm.label}</div>
                <div className="qr-eta">{t.eta_text || '—'}</div>
                <div className="qr-actions">
                  {/* Only manual override: mark no-show for patients who don't come */}
                  {t.status === 'waiting' && (
                    <button className="btn-xs btn-red" onClick={() => action(`/api/tokens/${t.code}/no-show`, `ns-${t.code}`)} disabled={busy[`ns-${t.code}`]}>
                      {busy[`ns-${t.code}`] ? '...' : 'No-show'}
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {archivedTokens.length > 0 && <>
        <div className="section-header" style={{ marginTop: 24 }}>
          Completed Today <span className="section-count">{archivedTokens.length}</span>
        </div>
        <div className="queue-list">
          {archivedTokens.map(t => {
            const smap = { completed: { label: 'Done', cls: 'sq-done' }, no_show: { label: 'No-show', cls: 'sq-noshow' }, skipped: { label: 'Skipped', cls: 'sq-done' } }
            const sm = smap[t.status] || smap.completed
            return (
              <div key={t.code} className="queue-row archived-row">
                <div className="qr-token">{t.code}</div>
                <div className="qr-info"><div className="qr-name">{t.patient_name}</div><div className="qr-service">{t.service_name}</div></div>
                <div className={`qr-status ${sm.cls}`}>{sm.label}</div>
                <div className="qr-eta" /><div className="qr-actions" />
              </div>
            )
          })}
        </div>
      </>}
    </div>
  )
}



function QRTab() {
  const [qrDataUrl, setQrDataUrl] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [services, setServices] = useState([])

  const generate = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const data = await api('/api/qr/generate', { method: 'POST' })
      setServices(data.services || [])
      const dataUrl = await QRCode.toDataURL(data.qr_token, { width: 280, margin: 2, color: { dark: '#1e1b4b', light: '#ffffff' }, errorCorrectionLevel: 'H' })
      setQrDataUrl(dataUrl)
    } catch (e) { setError(String(e)) }
    finally { setLoading(false) }
  }, [])

  // Auto-generate on mount
  useEffect(() => { generate() }, [generate])

  return (
    <div className="qr-tab">
      <div className="qr-tab-card">
        <h2 className="qr-tab-title">Patient Registration QR</h2>
        <p className="qr-tab-sub">Show this QR code at reception. Patients scan it to register and join the queue automatically.</p>
        {error && <div className="form-error">{error}</div>}
        {loading && !qrDataUrl && <div style={{ textAlign: 'center', padding: 40 }}><div className="spinner" style={{ margin: '0 auto 12px' }} /><p style={{ color: '#a78bfa', fontSize: 13 }}>Generating...</p></div>}
        {qrDataUrl && <>
          <div className="qr-display">
            <img src={qrDataUrl} alt="Registration QR Code" className="qr-image" />
            <div className="qr-caption">Show this to the patient</div>
          </div>
          {services.length > 0 && (
            <div className="qr-services">
              <div className="qs-label">Available services:</div>
              <div className="qs-chips">{services.map(s => <span key={s.code} className="qs-chip">{s.name}</span>)}</div>
            </div>
          )}
          <button id="btn-new-qr" className="btn-refresh-qr" onClick={generate} disabled={loading}>
            {loading ? 'Refreshing...' : '↻ Generate New QR'}
          </button>
          <div className="qr-note">⏱ Valid for 30 minutes</div>
        </>}
      </div>
    </div>
  )
}
