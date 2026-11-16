import { useCallback, useEffect, useRef, useState } from 'react'
import { clearAccessToken, refreshSession, setAccessToken } from './auth.js'

let googleScriptPromise
let googleConfigPromise

function loadGoogleIdentity() {
  if (window.google?.accounts?.id) return Promise.resolve(window.google)
  if (!googleScriptPromise) {
    googleScriptPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script')
      script.src = 'https://accounts.google.com/gsi/client'
      script.async = true
      script.defer = true
      const fail = (error) => {
        googleScriptPromise = null
        reject(error)
      }
      const timeout = window.setTimeout(
        () => fail(new Error('Google sign-in script timed out.')),
        10000,
      )
      script.addEventListener(
        'load',
        () => {
          window.clearTimeout(timeout)
          if (window.google?.accounts?.id) resolve(window.google)
          else fail(new Error('Google sign-in script initialized incorrectly.'))
        },
        { once: true },
      )
      script.addEventListener(
        'error',
        () => {
          window.clearTimeout(timeout)
          fail(new Error('Google sign-in script failed to load.'))
        },
        { once: true },
      )
      document.head.appendChild(script)
    })
  }
  return googleScriptPromise
}

function loadGoogleClientId() {
  if (!googleConfigPromise) {
    googleConfigPromise = fetch('/users/google/config', {
      signal: AbortSignal.timeout(10000),
    })
      .then(async (response) => {
        if (!response.ok) throw new Error('Google sign-in settings could not be loaded.')
        const { client_id: clientId } = await response.json()
        return typeof clientId === 'string' ? clientId : ''
      })
      .catch((error) => {
        googleConfigPromise = null
        throw error
      })
  }
  return googleConfigPromise
}

function GoogleSignIn({ mode, onCredential, onReady, disabled }) {
  const container = useRef(null)
  const [buttonState, setButtonState] = useState({ mode, status: 'loading' })
  const [unavailableMessage, setUnavailableMessage] = useState('')
  const status = buttonState.mode === mode ? buttonState.status : 'loading'

  useEffect(() => {
    let active = true
    const buttonContainer = container.current

    async function setupGoogleButton() {
      try {
        const clientId = await loadGoogleClientId()
        if (!active) return
        if (!clientId) {
          setUnavailableMessage('Google sign-in is not configured on the server yet.')
          setButtonState({ mode, status: 'unavailable' })
          onReady()
          return
        }

        const google = await loadGoogleIdentity()
        if (!active) return
        if (!buttonContainer) throw new Error('Google sign-in button container is unavailable.')

        google.accounts.id.initialize({
          client_id: clientId,
          callback: (response) => {
            const credential = response?.credential
            if (typeof credential === 'string' && credential) onCredential(credential)
          },
          auto_select: false,
          use_fedcm_for_prompt: true,
        })
        buttonContainer.replaceChildren()
        google.accounts.id.renderButton(buttonContainer, {
          theme: 'outline',
          size: 'large',
          shape: 'rectangular',
          text: mode === 'register' ? 'signup_with' : 'signin_with',
          logo_alignment: 'left',
          width: Math.floor(
            Math.min(
              420,
              buttonContainer.parentElement?.clientWidth || buttonContainer.clientWidth || 420,
            ),
          ),
        })
        setButtonState({ mode, status: 'ready' })
        onReady()
      } catch {
        if (active) {
          setUnavailableMessage(
            'Google sign-in could not load. Check your connection and try again.',
          )
          setButtonState({ mode, status: 'unavailable' })
          onReady()
        }
      }
    }

    setupGoogleButton()
    return () => {
      active = false
      buttonContainer?.replaceChildren()
    }
  }, [mode, onCredential, onReady])

  return (
    <div className="auth-google-slot" aria-busy={status === 'loading'}>
      <div
        className={`auth-google-button${status === 'ready' ? '' : ' is-hidden'}${disabled ? ' is-disabled' : ''
          }`}
        ref={container}
      />
      {status === 'unavailable' && (
        <p aria-live="polite">{unavailableMessage}</p>
      )}
    </div>
  )
}

function getErrorMessage(detail) {
  if (typeof detail === 'string') return detail
  if (detail?.message) return detail.message
  return 'Something went wrong. Please try again.'
}

function AuthPage({ mode, navigate }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [session, setSession] = useState(null)
  const [sessionMessage, setSessionMessage] = useState('signed-in')
  const [sessionChecked, setSessionChecked] = useState(false)
  const [googleReady, setGoogleReady] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [alreadyRegistered, setAlreadyRegistered] = useState(false)

  useEffect(() => {
    let active = true
    refreshSession()
      .then((data) => {
        if (active) {
          setSession(data)
          if (data) setSessionMessage('already-signed-in')
        }
      })
      .catch(() => { })
      .finally(() => {
        if (active) setSessionChecked(true)
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!session) return undefined

    const refreshIn = Math.max(1000, (session.expires_in - 30) * 1000)
    const timer = window.setTimeout(() => {
      refreshSession()
        .then(setSession)
        .catch(() => setSession(null))
    }, refreshIn)
    return () => window.clearTimeout(timer)
  }, [session])

  const acceptGoogleCredential = useCallback(async (credential) => {
    setBusy(true)
    setError('')
    try {
      const response = await fetch('/users/google', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ credential }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(getErrorMessage(data.detail))
      setAccessToken(data.access_token)
      setSession(data)
      setSessionMessage('signed-in')
      setPassword('')
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy(false)
    }
  }, [])

  const handleGoogleReady = useCallback(() => setGoogleReady(true), [])

  async function submitAuth(event, requestedMode = mode) {
    event?.preventDefault()
    setBusy(true)
    setError('')
    setAlreadyRegistered(false)

    try {
      const response = await fetch(`/users/${requestedMode === 'register' ? 'register' : 'login'}`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        if (requestedMode === 'register' && data.detail?.code === 'already_registered') {
          setAlreadyRegistered(true)
          setError('You’re already registered with this email.')
          return
        }
        throw new Error(getErrorMessage(data.detail))
      }
      setAccessToken(data.access_token)
      setPassword('')
      if (requestedMode === 'register') {
        navigate('/')
        return
      }
      setSession(data)
      setSessionMessage('signed-in')
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy(false)
    }
  }

  async function logout() {
    setBusy(true)
    try {
      await fetch('/users/logout', { method: 'POST', credentials: 'include' })
    } finally {
      setSession(null)
      clearAccessToken()
      setSessionMessage('signed-in')
      setBusy(false)
    }
  }

  function switchMode(nextMode) {
    navigate(nextMode === 'login' ? '/login' : '/signup')
    setError('')
    setAlreadyRegistered(false)
  }

  const pageReady = sessionChecked && (session !== null || googleReady)

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
      </header>

      <section
        className={`page-layout page-layout--centered${pageReady ? '' : ' is-loading'}`}
        aria-labelledby="auth-title"
        aria-busy={!pageReady}
      >
        <div className="card card--narrow" aria-hidden={!pageReady}>
          {session ? (
            <div className="signed-in">
              <div aria-hidden="true">
                <svg
                  width="24"
                  height="24"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="m5 12 4 4L19 6" />
                </svg>
              </div>
              <h1 className="page-title page-title--compact" id="auth-title">
                {sessionMessage === 'already-signed-in'
                  ? 'You’re already signed in'
                  : 'You’re signed in'}
              </h1>
              <p>Signed in as</p>
              <strong>{session.user.email}</strong>
              <button
                className="button button--primary button--block"
                onClick={() => navigate('/')}
              >
                Go to homepage
              </button>
            </div>
          ) : (
            <>
              <div className="card-heading">
                <h1 className="page-title page-title--compact" id="auth-title">
                  {mode === 'register' ? 'Create your account' : 'Welcome back'}
                </h1>
                <p>
                  {mode === 'register' ? 'Already have an account?' : 'New to Short it?'}{' '}
                  <button
                    className="button button--text"
                    type="button"
                    onClick={() => switchMode(mode === 'register' ? 'login' : 'register')}
                  >
                    {mode === 'register' ? 'Log in' : 'Sign up'}
                  </button>
                </p>
              </div>

              <GoogleSignIn
                mode={mode}
                onCredential={acceptGoogleCredential}
                onReady={handleGoogleReady}
                disabled={busy}
              />

              <div className="divider" aria-hidden="true">
                <span>or</span>
              </div>

              <form className="stack" onSubmit={submitAuth}>
                <label htmlFor="email">Email</label>
                <input
                  id="email"
                  className="form-control"
                  name="email"
                  type="email"
                  autoComplete="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  maxLength={254}
                  required
                />

                <label htmlFor="password">Password</label>
                <input
                  id="password"
                  className="form-control"
                  name="password"
                  type="password"
                  autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
                  placeholder={mode === 'register' ? 'At least 8 characters' : 'Your password'}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  minLength={mode === 'register' ? 8 : undefined}
                  maxLength={72}
                  required
                />
                {mode === 'register' && (
                  <p className="field-hint">Use 8 or more characters.</p>
                )}

                {error && (
                  <div
                    className={`form-message${alreadyRegistered ? ' is-info' : ''}`}
                    role="alert"
                  >
                    <span>{error}</span>
                    {alreadyRegistered && (
                      <button
                        type="button"
                        className="button button--text"
                        disabled={busy}
                        onClick={() => {
                          navigate('/login')
                          setError('')
                          setAlreadyRegistered(false)
                          submitAuth(null, 'login')
                        }}
                      >
                        Log in with these details
                      </button>
                    )}
                  </div>
                )}

                <button
                  className="button button--primary button--block"
                  type="submit"
                  disabled={busy}
                >
                  {busy
                    ? mode === 'register' ? 'Creating account…' : 'Logging in…'
                    : mode === 'register' ? 'Create your account' : 'Log in'}
                </button>
              </form>
            </>
          )}
        </div>
        {!pageReady && (
          <p role="status">
            Preparing sign-in…
          </p>
        )}
      </section>
    </main>
  )
}

export default AuthPage
