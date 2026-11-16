import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import './App.css'
import AuthPage from './AuthPage.jsx'
import { authenticatedFetch, clearAccessToken, refreshSession } from './auth.js'

const turnstileSiteKey = import.meta.env.VITE_TURNSTILE_SITE_KEY || '0x4AAAAAAFww43GtJVl5TVWE'
let turnstileScriptPromise

function loadTurnstile() {
  if (window.turnstile) return Promise.resolve(window.turnstile)
  if (!turnstileScriptPromise) {
    turnstileScriptPromise = new Promise((resolve, reject) => {
      const existingScript = document.querySelector(
        'script[src="https://challenges.cloudflare.com/turnstile/v0/api.js"]',
      )
      const script = existingScript || document.createElement('script')
      script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
      script.async = true
      script.defer = true
      script.addEventListener('load', () => resolve(window.turnstile), { once: true })
      script.addEventListener('error', reject, { once: true })
      if (!existingScript) document.head.appendChild(script)
    })
  }
  return turnstileScriptPromise
}

const initialState = {
  status: 'idle',
  shortUrl: '',
  error: '',
}

function ShortenerPage() {
  const [url, setUrl] = useState('')
  const [result, setResult] = useState(initialState)
  const [account, setAccount] = useState(null)
  const [accountChecked, setAccountChecked] = useState(false)
  const [loggingOut, setLoggingOut] = useState(false)
  const [accountError, setAccountError] = useState('')
  const [copied, setCopied] = useState(false)
  const [turnstileToken, setTurnstileToken] = useState('')
  const [turnstileError, setTurnstileError] = useState('')
  const [widgetReady, setWidgetReady] = useState(false)
  const widgetContainer = useRef(null)
  const widgetId = useRef(null)
  const accountMenu = useRef(null)

  useEffect(() => {
    let active = true
    const updateSession = (event) => {
      if (!active) return
      setAccount(event.detail?.user || null)
      setAccountChecked(true)
    }

    window.addEventListener('shortit:session', updateSession)

    refreshSession()
      .then((session) => {
        updateSession({ detail: session })
      })
      .catch(() => {
        updateSession({ detail: null })
      })

    return () => {
      active = false
      window.removeEventListener('shortit:session', updateSession)
    }
  }, [])

  useEffect(() => {
    function closeAccountMenu(event) {
      if (accountMenu.current && !accountMenu.current.contains(event.target)) {
        accountMenu.current.open = false
      }
    }

    document.addEventListener('pointerdown', closeAccountMenu)
    return () => document.removeEventListener('pointerdown', closeAccountMenu)
  }, [])

  async function logout() {
    setLoggingOut(true)
    setAccountError('')
    try {
      const response = await fetch('/users/logout', {
        method: 'POST',
        credentials: 'include',
      })
      if (!response.ok) throw new Error('Logout request failed.')
      clearAccessToken()
      setAccount(null)
      if (accountMenu.current) accountMenu.current.open = false
    } catch {
      setAccountError('Could not log out. Please try again.')
    } finally {
      setLoggingOut(false)
    }
  }

  const canSubmit = useMemo(() => {
    return (
      url.trim().length > 0 &&
      widgetReady &&
      Boolean(turnstileToken) &&
      result.status !== 'loading'
    )
  }, [url, widgetReady, turnstileToken, result.status])

  useEffect(() => {
    let mounted = true

    loadTurnstile()
      .then((turnstile) => {
        if (!mounted || !widgetContainer.current) return
        widgetId.current = turnstile.render(widgetContainer.current, {
          sitekey: turnstileSiteKey,
          action: 'shorten',
          appearance: 'always',
          callback: (token) => {
            setTurnstileToken(token)
            setTurnstileError('')
          },
          'expired-callback': () => setTurnstileToken(''),
          'error-callback': () => {
            setResult(initialState)
            setTurnstileToken('')
            setTurnstileError('Security check failed to load. Please try again.')
          },
        })
        setWidgetReady(true)
      })
      .catch(() => {
        if (mounted) setTurnstileError('Security check could not load. Please refresh the page.')
      })

    return () => {
      mounted = false
      if (widgetId.current !== null && window.turnstile) {
        window.turnstile.remove(widgetId.current)
        widgetId.current = null
      }
    }
  }, [])

  async function submitUrl(submittedUrl, token) {
    setCopied(false)
    setResult({ ...initialState, status: 'loading' })
    let shortened = false

    try {
      const response = await authenticatedFetch('/links/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          url: submittedUrl,
          turnstile_token: token,
        }),
      })

      const data = await response.json().catch(() => ({}))

      if (!response.ok) {
        throw new Error(data.detail || 'Could not shorten this link.')
      }

      if (typeof data.id !== 'string' || !data.id) {
        throw new Error('The server returned an invalid shortened link.')
      }

      setResult({
        status: 'success',
        shortUrl: new URL(`/s/${encodeURIComponent(data.id)}`, window.location.origin).href,
        error: '',
      })
      shortened = true
    } catch (error) {
      setResult({
        status: 'error',
        shortUrl: '',
        error: error.message,
      })
    } finally {
      setTurnstileToken('')
      if (!shortened && widgetId.current !== null && window.turnstile) {
        window.turnstile.reset(widgetId.current)
      }
    }
  }

  function handleUrlChange(event) {
    setUrl(event.target.value)
    if (result.status === 'success') {
      setResult(initialState)
      setCopied(false)
      if (widgetId.current !== null && window.turnstile) {
        window.turnstile.reset(widgetId.current)
      }
    }
  }

  function handleSubmit(event) {
    event.preventDefault()
    setCopied(false)
    setTurnstileError('')
    if (!turnstileToken) {
      setTurnstileError('Complete the security check before shortening a link.')
      return
    }
    submitUrl(url.trim(), turnstileToken)
  }

  async function copyShortUrl() {
    if (!result.shortUrl) return

    await navigator.clipboard.writeText(result.shortUrl)
    setCopied(true)
  }

  return (
    <main className="site-shell">
      <header className="site-header" aria-label="Short it">
        <a className="site-brand" href="/" aria-label="Short it home">
          <picture>
            <source
              media="(prefers-color-scheme: dark)"
              srcSet="/brand/short-it-horizontal-dark.svg"
            />
            <img src="/brand/short-it-horizontal.svg" alt="Short it" />
          </picture>
        </a>
        <nav className="site-actions" aria-label="Account">
          {!accountChecked ? (
            <span aria-hidden="true" />
          ) : account ? (
            <details className="account-menu" ref={accountMenu}>
              <summary aria-label={`Account menu for ${account.email}`}>
                <svg
                  aria-hidden="true"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M18 20a6 6 0 0 0-12 0" />
                  <circle cx="12" cy="10" r="4" />
                </svg>
                <span title={account.email}>
                  {account.email}
                </span>
                <svg
                  aria-hidden="true"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="m6 9 6 6 6-6" />
                </svg>
              </summary>
              <ul>
                {accountError && (
                  <li role="alert">
                    {accountError}
                  </li>
                )}
                <li>
                  <button type="button" onClick={logout} disabled={loggingOut}>
                    {loggingOut ? 'Logging out…' : 'Log out'}
                  </button>
                </li>
              </ul>
            </details>
          ) : (
            <>
              <a href="/login">
                Log In
              </a>
              <a className="button button--primary button--small" href="/signup">
                Sign Up
              </a>
            </>
          )}
        </nav>
      </header>

      <section className="page-layout page-layout--split" id="shortener">
        <div className="page-intro">
          <h1 className="page-title">Shorten links. Keep things simple.</h1>
          <p className="page-lead">
            Paste a long URL, get a short link, and share it wherever every
            character counts.
          </p>
        </div>

        <form className="card" onSubmit={handleSubmit}>
          <label htmlFor="url">Long URL</label>
          <div className="form-row">
            <input
              id="url"
              className="form-control"
              name="url"
              type="url"
              placeholder="https://example.com/very/long/link"
              value={url}
              onChange={handleUrlChange}
              required
            />
            <button
              className="button button--primary"
              type="submit"
              disabled={!canSubmit}
            >
              {result.status === 'loading' ? 'Shortening...' : 'Shorten'}
            </button>
          </div>

          <div className="turnstile-widget" ref={widgetContainer} />
          {turnstileError && (
            <p role="alert">
              {turnstileError}
            </p>
          )}

          {result.status === 'success' && (
            <div className="result-card" role="status">
              <span>{result.shortUrl}</span>
              <button type="button" className="button button--primary" onClick={copyShortUrl}>
                {copied ? 'Copied' : 'Copy'}
              </button>
            </div>
          )}

          {result.status === 'error' && (
            <p role="alert">
              {result.error}
            </p>
          )}
        </form>
      </section>
    </main>
  )
}

function App() {
  const [pathname, setPathname] = useState(window.location.pathname)

  useEffect(() => {
    const updatePathname = () => setPathname(window.location.pathname)
    window.addEventListener('popstate', updatePathname)
    return () => window.removeEventListener('popstate', updatePathname)
  }, [])

  const navigate = useCallback((path) => {
    window.history.pushState({}, '', path)
    setPathname(path)
  }, [])

  if (pathname === '/signup' || pathname === '/login' || pathname === '/auth') {
    return (
      <AuthPage
        mode={pathname === '/login' ? 'login' : 'register'}
        navigate={navigate}
      />
    )
  }

  return <ShortenerPage />
}

export default App
