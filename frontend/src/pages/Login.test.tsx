import { StrictMode } from 'react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { BrokerList } from '@/api/broker-config'
import { useAuthStore } from '@/stores/authStore'
import { brokerEntry, brokerList, saved } from '@/test/brokerList'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import Login from './Login'

// After the password step, a trader with exactly one configured broker goes
// straight to it; with none or several, Select Broker lists the choice.

const realLocation = window.location
let assigned: string[] = []
let posts: { url: string; body: unknown }[] = []
let list: BrokerList
let loginReply: Record<string, unknown>
let sessionStatus: Record<string, unknown>

function Location() {
  return <div data-testid="location">{useLocation().pathname}</div>
}

function renderLogin(strict = false) {
  const routes = (
    <MemoryRouter initialEntries={['/login']}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Location />} />
      </Routes>
    </MemoryRouter>
  )
  return render(strict ? <StrictMode>{routes}</StrictMode> : routes)
}

function serve() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const json = (body: unknown, status = 200) =>
        new Response(JSON.stringify(body), {
          status,
          headers: { 'Content-Type': 'application/json' },
        })
      if (url === '/auth/check-setup') return json({ needs_setup: false })
      if (url === '/auth/session-status') return json(sessionStatus)
      if (url === '/auth/csrf-token') return json({ csrf_token: 'tok' })
      if (url === '/auth/login') return json(loginReply)
      if (url === '/api/broker/list') return json({ status: 'success', data: list })
      if (init?.method === 'POST') {
        const body = init.body ? JSON.parse(String(init.body)) : null
        posts.push({ url, body })
        if (url === '/auth/broker/login') {
          return json({ status: 'success', url: `https://broker.example/${body.broker}/login` })
        }
        if (url === '/auth/broker/resume') return json({ status: 'success' })
      }
      return json({}, 404)
    })
  )
}

async function signIn() {
  fireEvent.change(await screen.findByLabelText('Username'), { target: { value: 'trader' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'secret' } })
  fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
}

beforeEach(() => {
  assigned = []
  posts = []
  loginReply = { status: 'success' }
  sessionStatus = { status: 'success', authenticated: false, logged_in: false }
  useAuthStore.setState({ user: null, isAuthenticated: false, apiKey: null })
  list = brokerList([
    brokerEntry('zerodha', 'Zerodha', 'redirect'),
    brokerEntry('fyers', 'Fyers', 'redirect'),
  ])
  const loc = { ...realLocation, origin: 'http://127.0.0.1:5000', search: '' }
  Object.defineProperty(loc, 'href', {
    get: () => assigned[assigned.length - 1] ?? 'http://127.0.0.1:5000/login',
    set: (v: string) => assigned.push(v),
  })
  Object.defineProperty(window, 'location', { configurable: true, value: loc })
})

afterEach(() => {
  Object.defineProperty(window, 'location', { configurable: true, value: realLocation })
  vi.unstubAllGlobals()
})

describe('Login with one configured broker', () => {
  it('goes straight to that broker instead of Select Broker', async () => {
    list = brokerList([saved(brokerEntry('zerodha', 'Zerodha', 'redirect'), {})])
    serve()
    renderLogin()
    await signIn()
    await waitFor(() => expect(assigned).toEqual(['https://broker.example/zerodha/login']))
    expect(posts).toEqual([{ url: '/auth/broker/login', body: { broker: 'zerodha' } }])
  })

  it('opens its dashboard when the server already has it logged in', async () => {
    list = brokerList([
      { ...saved(brokerEntry('zerodha', 'Zerodha', 'redirect'), {}), active: true },
    ])
    serve()
    renderLogin()
    await signIn()
    await waitFor(() => expect(assigned).toEqual(['/dashboard']))
    expect(posts).toEqual([{ url: '/auth/broker/resume', body: {} }])
  })

  it('starts one sign-in when the login page loads already signed in', async () => {
    sessionStatus = { status: 'success', authenticated: true, logged_in: false }
    list = brokerList([saved(brokerEntry('zerodha', 'Zerodha', 'redirect'), {})])
    serve()
    renderLogin(true)
    await waitFor(() => expect(assigned).toEqual(['https://broker.example/zerodha/login']))
    expect(posts).toEqual([{ url: '/auth/broker/login', body: { broker: 'zerodha' } }])
  })
})

describe('Login with no single configured broker', () => {
  it('opens Select Broker when several brokers are configured', async () => {
    list = brokerList([
      saved(brokerEntry('zerodha', 'Zerodha', 'redirect'), {}),
      saved(brokerEntry('fyers', 'Fyers', 'redirect'), {}),
    ])
    serve()
    renderLogin()
    await signIn()
    expect(await screen.findByTestId('location')).toHaveTextContent('/broker')
    expect(posts).toEqual([])
    expect(assigned).toEqual([])
  })

  it('opens Select Broker when no broker is configured', async () => {
    serve()
    renderLogin()
    await signIn()
    expect(await screen.findByTestId('location')).toHaveTextContent('/broker')
    expect(posts).toEqual([])
    expect(assigned).toEqual([])
  })
})
