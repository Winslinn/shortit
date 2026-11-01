import { useMemo, useState } from 'react'
import './App.css'

const initialState = {
  status: 'idle',
  shortUrl: '',
  error: '',
}

function App() {
  const [url, setUrl] = useState('')
  const [result, setResult] = useState(initialState)
  const [copied, setCopied] = useState(false)

  const canSubmit = useMemo(() => {
    return url.trim().length > 0 && result.status !== 'loading'
  }, [url, result.status])

  async function handleSubmit(event) {
    event.preventDefault()
    setCopied(false)
    setResult({ ...initialState, status: 'loading' })

    try {
      const response = await fetch('/api/shorten', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ url: url.trim() }),
      })

      const data = await response.json().catch(() => ({}))

      if (!response.ok) {
        throw new Error(data.detail || 'Could not shorten this link.')
      }

      setResult({
        status: 'success',
        shortUrl: data.short_url,
        error: '',
      })
    } catch (error) {
      setResult({
        status: 'error',
        shortUrl: '',
        error: error.message,
      })
    }
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
              onChange={(event) => setUrl(event.target.value)}
              required
            />
            <button type="submit" disabled={!canSubmit}>
              {result.status === 'loading' ? 'Shortening...' : 'Shorten'}
            </button>
          </div>

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