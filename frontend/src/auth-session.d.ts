export type AuthState = 'loading' | 'authenticated' | 'unauthenticated'

export type AuthSessionResult<User> =
  | { status: 'authenticated'; user: User }
  | { status: 'unauthenticated' }
  | { status: 'error'; error: unknown }

export function getAuthState(ready: boolean, user: unknown): AuthState

export function restoreAuthSession<User>(
  request: (path: string) => Promise<{ user?: User | null }>,
): Promise<AuthSessionResult<User>>
