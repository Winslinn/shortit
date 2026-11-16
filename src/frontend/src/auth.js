let accessToken = null
let refreshPromise = null

function publishSession(session) {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('shortit:session', { detail: session }))
  }
}

export function setAccessToken(token) {
  accessToken = typeof token === 'string' && token ? token : null
}

export function clearAccessToken() {
  accessToken = null
  publishSession(null)
}

export function refreshSession() {
  if (!refreshPromise) {
    refreshPromise = fetch('/users/refresh', {
      method: 'POST',
      credentials: 'include',
      signal: AbortSignal.timeout(10000),
    })
      .then(async (response) => {
        const data = await response.json().catch(() => ({}))
        if (!response.ok) {
          const error = new Error(data.detail || 'Session expired.')
          error.status = response.status
          throw error
        }
        setAccessToken(data.access_token)
        publishSession(data)
        return data
      })
      .catch((error) => {
        clearAccessToken()
        throw error
      })
      .finally(() => {
        refreshPromise = null
      })
  }

  return refreshPromise
}

export async function authenticatedFetch(url, options = {}) {
  let token = accessToken
  if (!token) token = (await refreshSession()).access_token

  const sendRequest = (access) => {
    const headers = new Headers(options.headers)
    headers.set('Authorization', `Bearer ${access}`)

    return fetch(url, {
      ...options,
      credentials: 'include',
      headers,
    })
  }

  let response = await sendRequest(token)
  if (response.status !== 401) return response

  try {
    token = (await refreshSession()).access_token
    response = await sendRequest(token)
  } catch {
    clearAccessToken()
  }

  if (response.status === 401) clearAccessToken()
  return response
}
