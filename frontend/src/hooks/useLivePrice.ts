import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { type QuotesData, tradingApi } from '@/api/trading'
import { useMarketData } from '@/hooks/useMarketData'
import { useMarketStatus } from '@/hooks/useMarketStatus'
import { usePageVisibility } from '@/hooks/usePageVisibility'
import { useAuthStore } from '@/stores/authStore'

/**
 * Base interface for items that can have live price data
 */
export interface PriceableItem {
  symbol: string
  exchange: string
  ltp?: number
  pnl?: number
  pnlpercent?: number
  quantity?: number
  average_price?: number
  realized_pnl?: number // Normalized realized component included in total P&L
  today_realized_pnl?: number // Sandbox: today's realized P&L from closed partial trades
  contract_multiplier?: number // Normalized value multiplier; 1 when quantity is in underlying units
}

/**
 * Configuration options for useLivePrice hook
 */
export interface UseLivePriceOptions {
  /** Whether the hook is enabled (default: true) */
  enabled?: boolean
  /** Time in ms after which WebSocket data is considered stale (default: 5000) */
  staleThreshold?: number
  /** Whether to use MultiQuotes API as fallback when WebSocket unavailable (default: true) */
  useMultiQuotesFallback?: boolean
  /** Interval in ms to refresh MultiQuotes data (default: 30000) */
  multiQuotesRefreshInterval?: number
  /** Pause WebSocket and polling when tab is hidden (default: true) */
  pauseWhenHidden?: boolean
  /** Time in ms to wait before pausing when hidden (default: 5000) */
  pauseDelay?: number
}

/**
 * Return type for useLivePrice hook
 */
export interface UseLivePriceResult<T extends PriceableItem> {
  /** Enhanced items with real-time LTP and recalculated PnL */
  data: T[]
  /** Whether real-time data is available (WebSocket connected AND market open) */
  isLive: boolean
  /** Whether WebSocket is connected */
  isConnected: boolean
  /** Whether WebSocket is paused due to tab being hidden */
  isPaused: boolean
  /** Whether using REST API fallback instead of WebSocket */
  isFallbackMode: boolean
  /** Whether any market is currently open */
  isAnyMarketOpen: boolean
  /** Map of MultiQuotes data for external access if needed */
  multiQuotes: Map<string, QuotesData>
  /** Manually refresh MultiQuotes data */
  refreshMultiQuotes: () => Promise<void>
}

/**
 * Centralized hook for real-time price data with automatic fallback.
 *
 * Priority chain:
 * 1. WebSocket LTP (when market is open and data is fresh)
 * 2. MultiQuotes API (fallback when WebSocket unavailable)
 * 3. REST API data (baseline from initial fetch)
 *
 * @example
 * ```tsx
 * const { data: enhancedHoldings, isLive } = useLivePrice(holdings, {
 *   enabled: holdings.length > 0,
 *   useMultiQuotesFallback: true,
 * });
 * ```
 */
export function useLivePrice<T extends PriceableItem>(
  items: T[],
  options: UseLivePriceOptions = {}
): UseLivePriceResult<T> {
  const {
    enabled = true,
    staleThreshold = 5000,
    useMultiQuotesFallback = true,
    multiQuotesRefreshInterval = 30000,
    pauseWhenHidden = true,
  } = options

  const { apiKey } = useAuthStore()
  const { isMarketOpen, isAnyMarketOpen } = useMarketStatus()
  const { isVisible, wasHidden, timeSinceHidden } = usePageVisibility()
  const anyMarketOpen = isAnyMarketOpen()

  // State for MultiQuotes fallback data
  const [multiQuotes, setMultiQuotes] = useState<Map<string, QuotesData>>(new Map())

  // Track last fetch time for visibility-aware refresh
  const lastFetchRef = useRef<number>(Date.now())

  // Extract symbols for WebSocket subscription
  const symbols = useMemo(
    () =>
      items.map((item) => ({
        symbol: item.symbol,
        exchange: item.exchange,
      })),
    [items]
  )

  // WebSocket market data - connect when enabled, with visibility awareness
  const {
    data: marketData,
    isConnected: wsConnected,
    isPaused: wsPaused,
    isFallbackMode,
  } = useMarketData({
    symbols,
    mode: 'LTP',
    enabled: enabled && items.length > 0,
  })

  // Effective live status
  const isLive = wsConnected && anyMarketOpen && !wsPaused

  /**
   * Fetch MultiQuotes data from API
   */
  const fetchMultiQuotes = useCallback(async () => {
    if (!apiKey || items.length === 0 || !useMultiQuotesFallback) return

    try {
      const symbolsList = items.map((item) => ({
        symbol: item.symbol,
        exchange: item.exchange,
      }))

      const response = await tradingApi.getMultiQuotes(apiKey, symbolsList)

      if (response.status === 'success' && response.results) {
        const quotesMap = new Map<string, QuotesData>()
        response.results.forEach((result) => {
          const key = `${result.exchange}:${result.symbol}`
          if (result.data) {
            quotesMap.set(key, result.data)
          }
        })
        setMultiQuotes(quotesMap)
      }
    } catch {
      // Silently fail - MultiQuotes is a fallback mechanism
    }
  }, [apiKey, items, useMultiQuotesFallback])

  // Fetch MultiQuotes on mount and when items change
  // Visibility-aware: pause polling when tab is hidden
  useEffect(() => {
    if (!enabled || items.length === 0 || !useMultiQuotesFallback) return

    // Don't poll when hidden (if pauseWhenHidden is true)
    if (pauseWhenHidden && !isVisible) return

    // Initial fetch
    fetchMultiQuotes()
    lastFetchRef.current = Date.now()

    // Set up periodic refresh
    const interval = setInterval(() => {
      fetchMultiQuotes()
      lastFetchRef.current = Date.now()
    }, multiQuotesRefreshInterval)

    return () => clearInterval(interval)
  }, [
    enabled,
    items.length,
    useMultiQuotesFallback,
    fetchMultiQuotes,
    multiQuotesRefreshInterval,
    pauseWhenHidden,
    isVisible,
  ])

  // Refresh MultiQuotes immediately when tab becomes visible after being hidden
  useEffect(() => {
    if (!wasHidden || !isVisible || !useMultiQuotesFallback || !enabled) return

    // If we were hidden for more than the refresh interval, fetch immediately
    if (timeSinceHidden > multiQuotesRefreshInterval) {
      fetchMultiQuotes()
      lastFetchRef.current = Date.now()
    }
  }, [
    wasHidden,
    isVisible,
    timeSinceHidden,
    multiQuotesRefreshInterval,
    useMultiQuotesFallback,
    enabled,
    fetchMultiQuotes,
  ])

  /**
   * Enhance items with real-time LTP and recalculated P&L
   * Priority: WebSocket (fresh + market open) → MultiQuotes → REST API
   *
   * For open positions (qty != 0): P&L and P&L% are recalculated using live LTP
   * For closed positions (qty = 0): P&L and P&L% from REST API (realized values)
   */
  const enhancedData = useMemo(() => {
    return items.map((item) => {
      const key = `${item.exchange}:${item.symbol}`
      const wsData = marketData.get(key)
      const mqData = multiQuotes.get(key)

      const qty = Number(item.quantity) || 0
      const avgPrice = item.average_price || 0

      // Check if market is open for this exchange
      const exchangeMarketOpen = isMarketOpen(item.exchange)

      // Check if WebSocket LTP is fresh AND market is open
      const hasWsData =
        exchangeMarketOpen &&
        wsData?.data?.ltp &&
        wsData.lastUpdate &&
        Date.now() - wsData.lastUpdate < staleThreshold

      // Check if we have MultiQuotes data (fallback when WebSocket not available)
      const hasMqData = !hasWsData && mqData?.ltp

      // Determine the best available LTP source
      let currentLtp: number | undefined
      let dataSource: 'websocket' | 'multiquotes' | 'rest' = 'rest'

      if (hasWsData && wsData?.data?.ltp) {
        currentLtp = wsData.data.ltp
        dataSource = 'websocket'
      } else if (hasMqData && mqData?.ltp) {
        currentLtp = mqData.ltp
        dataSource = 'multiquotes'
      } else {
        currentLtp = item.ltp
        dataSource = 'rest'
      }

      // For closed positions (qty=0), preserve ALL REST API values including LTP
      // This ensures P&L% calculation remains stable (realized values don't change)
      //
      // Gated on the field being PRESENT, not just falsy. `quantity` is optional
      // on PriceableItem, and an item that never carried one is not a position
      // at all -- a watchlist row, say. Those must still take live prices, and
      // `item.quantity || 0` reads the same 0 for both cases.
      if (item.quantity !== undefined && qty === 0) {
        return {
          ...item,
          // Keep item.ltp from REST API - don't update with live data
          // This prevents P&L% from recalculating with changing LTP
          _dataSource: 'rest',
        } as T & { _dataSource: string }
      }

      // Preserve realized P&L when the broker exposes it separately. Otherwise,
      // adjust the broker's total by the LTP movement since the REST snapshot.
      const realizedPnl = item.realized_pnl ?? item.today_realized_pnl ?? 0
      const hasBrokerPnl = item.pnl !== undefined && item.pnl !== null
      let calculatedPnl = hasBrokerPnl ? Number(item.pnl) || 0 : realizedPnl
      let calculatedPnlPercent = Number(item.pnlpercent) || 0

      const investment = Math.abs(avgPrice * qty * (item.contract_multiplier ?? 1))

      if (currentLtp !== undefined && avgPrice > 0) {
        const contractMultiplier = item.contract_multiplier ?? 1
        const unrealizedPnl = (currentLtp - avgPrice) * qty * contractMultiplier
        if (item.realized_pnl != null || item.today_realized_pnl != null) {
          calculatedPnl = realizedPnl + unrealizedPnl
        } else if (hasBrokerPnl && item.ltp != null) {
          // Broker P&L may already include realized P&L. Keep its REST total
          // and apply only the change in unrealized P&L since that quote.
          calculatedPnl += (currentLtp - Number(item.ltp)) * qty * contractMultiplier
        } else {
          calculatedPnl = realizedPnl + unrealizedPnl
        }

        calculatedPnlPercent = investment > 0 ? (calculatedPnl / investment) * 100 : 0
      } else if (hasBrokerPnl && item.pnlpercent == null && investment > 0) {
        calculatedPnlPercent = (calculatedPnl / investment) * 100
      }

      return {
        ...item,
        ltp: currentLtp,
        pnl: calculatedPnl,
        pnlpercent: calculatedPnlPercent,
        _dataSource: dataSource,
      } as T & { _dataSource: string }
    })
  }, [items, marketData, multiQuotes, isMarketOpen, staleThreshold])

  return {
    data: enhancedData,
    isLive,
    isConnected: wsConnected,
    isPaused: wsPaused,
    isFallbackMode,
    isAnyMarketOpen: anyMarketOpen,
    multiQuotes,
    refreshMultiQuotes: fetchMultiQuotes,
  }
}

/**
 * Calculate aggregated stats from items with live price data
 */
export function calculateLiveStats<T extends PriceableItem>(
  items: T[],
  originalStats?: {
    totalholdingvalue?: number
    totalinvvalue?: number
    totalprofitandloss?: number
    totalpnlpercentage?: number
  }
) {
  if (!originalStats) return null

  let totalPnl = 0
  let totalInvestment = 0
  let totalHoldingValue = 0

  items.forEach((item) => {
    totalPnl += item.pnl || 0
    const avgPrice = item.average_price || 0
    const qty = item.quantity || 0
    const ltp = item.ltp || avgPrice
    totalInvestment += avgPrice * qty
    totalHoldingValue += ltp * qty
  })

  const totalPnlPercent = totalInvestment > 0 ? (totalPnl / totalInvestment) * 100 : 0

  return {
    ...originalStats,
    totalholdingvalue: totalHoldingValue,
    totalinvvalue: totalInvestment,
    totalprofitandloss: totalPnl,
    totalpnlpercentage: totalPnlPercent,
  }
}
