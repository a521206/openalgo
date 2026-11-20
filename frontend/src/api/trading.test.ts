import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ post: vi.fn() }))

vi.mock('./client', () => ({
  apiClient: { post: mocks.post },
  webClient: { post: vi.fn() },
}))

import { tradingApi } from './trading'

describe('tradingApi.getPositions', () => {
  beforeEach(() => vi.clearAllMocks())

  it('normalizes numeric strings and drops malformed position rows', async () => {
    mocks.post.mockResolvedValue({
      data: {
        status: 'success',
        data: [
          {
            symbol: 'BTCUSD.P',
            exchange: 'CRYPTO',
            product: 'NRML',
            quantity: '-2',
            average_price: '100',
            ltp: '90',
            pnl: '15',
            pnlpercent: '7.5',
            contract_multiplier: '0.001',
            realized_pnl: '5',
          },
          null,
        ],
      },
    })

    const response = await tradingApi.getPositions('api-key')

    expect(response.data).toEqual([
      {
        symbol: 'BTCUSD.P',
        exchange: 'CRYPTO',
        product: 'NRML',
        quantity: -2,
        average_price: 100,
        ltp: 90,
        pnl: 15,
        pnlpercent: 7.5,
        contract_multiplier: 0.001,
        realized_pnl: 5,
      },
    ])
  })
})
