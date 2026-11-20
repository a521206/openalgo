import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook, waitFor } from '@/test/test-utils'
import { useLivePrice } from './useLivePrice'

/**
 * The closed-position branch.
 *
 * `useLivePrice` freezes an item's REST values when its quantity is zero, so a
 * closed position's realized P&L percentage does not drift as the market moves.
 * `quantity` is optional on `PriceableItem`, and `item.quantity || 0` read the
 * same zero for "this position is closed" and "this is not a position at all",
 * which silently froze every watchlist row at its REST price.
 *
 * The gate is now on the field being present. These tests pin both readings,
 * because this hook also prices Positions and Holdings and nothing else covered
 * it.
 */
const marketData = new Map<string, { data: { ltp: number }; lastUpdate: number }>()

vi.mock('./useMarketData', () => ({
  useMarketData: () => ({
    data: marketData,
    isConnected: true,
    isAuthenticated: true,
    isPaused: false,
    isFallbackMode: false,
    error: null,
  }),
}))

vi.mock('./useMarketStatus', () => ({
  useMarketStatus: () => ({
    isMarketOpen: () => true,
    isAnyMarketOpen: () => true,
  }),
}))

vi.mock('@/stores/authStore', () => ({
  useAuthStore: () => ({ apiKey: 'k' }),
}))

vi.mock('@/api/trading', () => ({
  tradingApi: {
    getMultiQuotes: vi.fn(async () => ({
      status: 'success',
      results: [{ symbol: 'RELIANCE', exchange: 'NSE', data: { ltp: 1300, prev_close: 1280 } }],
    })),
  },
}))

describe('useLivePrice closed-position gate', () => {
  beforeEach(() => {
    marketData.clear()
    marketData.set('NSE:RELIANCE', { data: { ltp: 1350 }, lastUpdate: Date.now() })
  })

  it('takes live prices for an item that carries no quantity at all', async () => {
    // A watchlist row. Not a position, so it must never be frozen.
    const { result } = renderHook(() =>
      useLivePrice([{ symbol: 'RELIANCE', exchange: 'NSE' }], { enabled: true })
    )

    await waitFor(() => expect(result.current.data[0].ltp).toBe(1350))
  })

  it('keeps the REST values for a position that has been closed', async () => {
    // quantity is present and zero, which is what "closed" means here.
    const { result } = renderHook(() =>
      useLivePrice([{ symbol: 'RELIANCE', exchange: 'NSE', quantity: 0, ltp: 1000 }], {
        enabled: true,
      })
    )

    await waitFor(() => expect(result.current.data).toHaveLength(1))
    expect(result.current.data[0].ltp).toBe(1000)
  })

  it('keeps realized P&L for a closed position with string-zero quantity', async () => {
    const { result } = renderHook(() =>
      useLivePrice(
        [
          {
            symbol: 'TEST',
            exchange: 'NSE',
            quantity: '0' as unknown as number,
            average_price: 1000,
            ltp: 1100,
            pnl: 250,
          },
        ],
        { enabled: true }
      )
    )

    await waitFor(() => expect(result.current.data[0].pnl).toBe(250))
    expect(result.current.data[0].ltp).toBe(1100)
  })

  it('takes live prices for an open position', async () => {
    const { result } = renderHook(() =>
      useLivePrice([{ symbol: 'RELIANCE', exchange: 'NSE', quantity: 5, ltp: 1000 }], {
        enabled: true,
      })
    )

    await waitFor(() => expect(result.current.data[0].ltp).toBe(1350))
  })

  it('includes the contract multiplier in P&L percentage', async () => {
    const { result } = renderHook(() =>
      useLivePrice(
        [
          {
            symbol: 'TEST',
            exchange: 'NSE',
            quantity: 2,
            average_price: 100,
            ltp: 110,
            pnl: 0,
            contract_multiplier: 0.5,
          },
        ],
        { enabled: true }
      )
    )

    await waitFor(() => expect(result.current.data[0].pnlpercent).toBeCloseTo(10))
  })

  it('adds normalized realized P&L to live unrealized P&L', async () => {
    const { result } = renderHook(() =>
      useLivePrice(
        [
          {
            symbol: 'RELIANCE',
            exchange: 'NSE',
            quantity: 2,
            average_price: 1000,
            pnl: 0,
            realized_pnl: 250,
          },
        ],
        { enabled: true, useMultiQuotesFallback: false }
      )
    )

    await waitFor(() => expect(result.current.data[0].pnl).toBe(950))
  })

  it('uses realized P&L as a fallback when P&L and quotes are unavailable', async () => {
    marketData.clear()

    const { result } = renderHook(() =>
      useLivePrice(
        [
          {
            symbol: 'RELIANCE',
            exchange: 'NSE',
            quantity: 5,
            average_price: 1000,
            today_realized_pnl: 125,
          },
        ],
        { enabled: true, useMultiQuotesFallback: false }
      )
    )

    await waitFor(() => expect(result.current.data[0].pnl).toBe(125))
    expect(result.current.data[0].ltp).toBeUndefined()
  })
})
