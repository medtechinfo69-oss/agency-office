// Sessions stay in HttpOnly cookies; provider keys and owner passwords are never
// persisted in browser storage. Used by both Office and Site Builder requests.
export async function authFetch(input, options) {
  const response = await fetch(input, options)
  if (response.status === 401) window.dispatchEvent(new Event('agency-auth-expired'))
  return response
}
