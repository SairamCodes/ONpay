export function getAuthState(ready, user) {
  if (!ready) return 'loading'
  return user ? 'authenticated' : 'unauthenticated'
}

export async function restoreAuthSession(request) {
  try {
    const result = await request('/api/auth/me')
    if (result?.user && typeof result.user === 'object') {
      return { status: 'authenticated', user: result.user }
    }
    return { status: 'error', error: new Error('ONPay returned an invalid session response.') }
  } catch (error) {
    if (error && typeof error === 'object' && 'status' in error && error.status === 401) {
      return { status: 'unauthenticated' }
    }
    return { status: 'error', error }
  }
}
