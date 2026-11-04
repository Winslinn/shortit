import { useEffect, useMemo, useRef, useState } from 'react'
import './App.css'

const turnstileSiteKey = '0x4AAAAAAFww43GtJVl5TVWE'
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

function App() {
  const [url, setUrl] = useState('')
  const [result, setResult] = useState(initialState)
  const [copied, setCopied] = useState(false)
  const [turnstileToken, setTurnstileToken] = useState('')
  const [turnstileError, setTurnstileError] = useState('')
  const [widgetReady, setWidgetReady] = useState(false)
  const widgetContainer = useRef(null)
  const widgetId = useRef(null)

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
      const response = await fetch('/links/', {
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
    <main className="shell">
      <header className="topbar" aria-label="Short it">
        <a className="brand" href="/" aria-label="Short it home">
          <picture>
            <source
              media="(prefers-color-scheme: dark)"
              srcSet="/brand/short-it-horizontal-dark.svg"
            />
            <img src="/brand/short-it-horizontal.svg" alt="Short it" />
          </picture>
        </a>
      </header>

      <section className="hero" id="shortener">
        <div className="hero-copy">
          <h1>Shorten links. Keep things simple.</h1>
          <p className="intro">
            Paste a long URL, get a short link, and share it wherever every
            character counts.
          </p>
        </div>

        <form className="shortener" onSubmit={handleSubmit}>
          <label htmlFor="url">Long URL</label>
          <div className="input-row">
            <input
              id="url"
              name="url"
              type="url"
              placeholder="https://example.com/very/long/link"
              value={url}
              onChange={handleUrlChange}
              required
            />
            <button type="submit" disabled={!canSubmit}>
              {result.status === 'loading' ? 'Shortening...' : 'Shorten'}
            </button>
          </div>

          <div className="turnstile-widget" ref={widgetContainer} />
          {turnstileError && (
            <p className="error" role="alert">
              {turnstileError}
            </p>
          )}

          {result.status === 'success' && (
            <div className="result" role="status">
              <span>{result.shortUrl}</span>
              <button type="button" className="secondary" onClick={copyShortUrl}>
                {copied ? 'Copied' : 'Copy'}
              </button>
            </div>
          )}

          {result.status === 'error' && (
            <p className="error" role="alert">
              {result.error}
            </p>
          )}
        </form>
      </section>
    </main>
  )
}

export default App
