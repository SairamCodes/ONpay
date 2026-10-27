import test from 'node:test'
import assert from 'node:assert/strict'
import { getAuthState, restoreAuthSession } from '../src/auth-session.js'

test('authentication view distinguishes loading, authenticated, and unauthenticated states', () => {
  assert.equal(getAuthState(false, null), 'loading')
  assert.equal(getAuthState(true, { id: 'student-1' }), 'authenticated')
  assert.equal(getAuthState(true, null), 'unauthenticated')
})

test('restores the signed-in user from the existing /api/auth/me session endpoint', async () => {
  const user = { id: 'student-1', full_name: 'Student' }
  const requested = []
  const result = await restoreAuthSession(async (path) => {
    requested.push(path)
    return { user }
  })

  assert.deepEqual(requested, ['/api/auth/me'])
  assert.deepEqual(result, { status: 'authenticated', user })
})

test('treats only a 401 as an unauthenticated session', async () => {
  assert.deepEqual(
    await restoreAuthSession(async () => { throw Object.assign(new Error('Sign in to continue'), { status: 401 }) }),
    { status: 'unauthenticated' },
  )

  const unavailable = new Error('Server unavailable')
  const result = await restoreAuthSession(async () => { throw unavailable })
  assert.equal(result.status, 'error')
  assert.equal(result.error, unavailable)
})

test('does not mark auth restoration complete before /api/auth/me resolves', async () => {
  let resolveRequest
  const restored = restoreAuthSession(() => new Promise((resolve) => { resolveRequest = resolve }))
  let settled = false
  void restored.then(() => { settled = true })
  await Promise.resolve()
  assert.equal(settled, false)

  resolveRequest({ user: { id: 'student-1' } })
  assert.equal((await restored).status, 'authenticated')
})
