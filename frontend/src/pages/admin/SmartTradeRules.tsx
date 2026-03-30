import { ArrowLeft, Save, Shield, TrendingUp } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { webClient } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'

interface SmartTradeRulesConfig {
  smart_trade_enabled: boolean
  prevent_duplicate_buy: boolean
  prevent_duplicate_sell: boolean
  max_position_size: number | null
  max_order_value: number | null
  allow_intraday_only: boolean
  block_cnc_orders: boolean
  block_nrml_orders: boolean
  liquidity_fallback: boolean
}

export default function SmartTradeRules() {
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)

  // Form state
  const [smartTradeEnabled, setSmartTradeEnabled] = useState(true)
  const [preventDuplicateBuy, setPreventDuplicateBuy] = useState(true)
  const [preventDuplicateSell, setPreventDuplicateSell] = useState(true)
  const [maxPositionSize, setMaxPositionSize] = useState<number | null>(null)
  const [maxOrderValue, setMaxOrderValue] = useState<number | null>(null)
  const [allowIntradayOnly, setAllowIntradayOnly] = useState(false)
  const [blockCncOrders, setBlockCncOrders] = useState(false)
  const [blockNrmlOrders, setBlockNrmlOrders] = useState(false)
  const [liquidityFallback, setLiquidityFallback] = useState(true)

  useEffect(() => {
    fetchConfig()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const fetchConfig = async () => {
    try {
      const response = await webClient.get<{ status: string; data: SmartTradeRulesConfig }>(
        '/settings/smart-trade-rules'
      )
      const configData = response.data.data
      setSmartTradeEnabled(configData.smart_trade_enabled)
      setPreventDuplicateBuy(configData.prevent_duplicate_buy)
      setPreventDuplicateSell(configData.prevent_duplicate_sell)
      setMaxPositionSize(configData.max_position_size)
      setMaxOrderValue(configData.max_order_value)
      setAllowIntradayOnly(configData.allow_intraday_only)
      setBlockCncOrders(configData.block_cnc_orders)
      setBlockNrmlOrders(configData.block_nrml_orders)
      setLiquidityFallback(configData.liquidity_fallback)
    } catch (error) {
      console.error('Error fetching config:', error)
      toast.error('Failed to load configuration')
    } finally {
      setIsLoading(false)
    }
  }

  const handleSave = async () => {
    setIsSaving(true)
    try {
      const updateData = {
        smart_trade_enabled: smartTradeEnabled,
        prevent_duplicate_buy: preventDuplicateBuy,
        prevent_duplicate_sell: preventDuplicateSell,
        max_position_size: maxPositionSize,
        max_order_value: maxOrderValue,
        allow_intraday_only: allowIntradayOnly,
        block_cnc_orders: blockCncOrders,
        block_nrml_orders: blockNrmlOrders,
        liquidity_fallback: liquidityFallback,
      }

      const response = await webClient.post<{ status: string; message: string }>(
        '/settings/smart-trade-rules',
        updateData
      )

      if (response.data.status === 'success') {
        toast.success('Smart trade rules saved successfully')
        fetchConfig() // Refresh config
      } else {
        toast.error(response.data.message || 'Failed to save configuration')
      }
    } catch (error: unknown) {
      const err = error as { response?: { data?: { message?: string } } }
      toast.error(err.response?.data?.message || 'Failed to save configuration')
    } finally {
      setIsSaving(false)
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    )
  }

  return (
    <div className="py-6 space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <Link to="/admin" className="text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Shield className="h-6 w-6" />
            Smart Trade Rules
          </h1>
        </div>
        <p className="text-muted-foreground">Configure automated trading rules and risk controls</p>
      </div>

      {/* Master Switch */}
      <Card className={smartTradeEnabled ? 'border-green-500/50' : ''}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5" />
            Enable Smart Trade Rules
          </CardTitle>
          <CardDescription>
            Master switch to enable/disable all smart trade rules. When disabled, all rules below are
            ignored.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div>
              <Label className="text-base">Smart Trade Rules</Label>
              <p className="text-sm text-muted-foreground">
                {smartTradeEnabled ? 'Rules are active' : 'Rules are disabled'}
              </p>
            </div>
            <Switch checked={smartTradeEnabled} onCheckedChange={setSmartTradeEnabled} />
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Position Rules */}
        <Card>
          <CardHeader>
            <CardTitle>Position Rules</CardTitle>
            <CardDescription>Control position entry and exit behavior</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Prevent Duplicate Buy */}
            <div className="flex items-center justify-between">
              <div>
                <Label>Prevent Duplicate BUY</Label>
                <p className="text-sm text-muted-foreground">
                  Block BUY orders if an open position already exists
                </p>
              </div>
              <Switch
                checked={preventDuplicateBuy}
                onCheckedChange={setPreventDuplicateBuy}
                disabled={!smartTradeEnabled}
              />
            </div>

            {/* Prevent Duplicate Sell */}
            <div className="flex items-center justify-between">
              <div>
                <Label>Prevent Duplicate SELL</Label>
                <p className="text-sm text-muted-foreground">
                  Block SELL orders if no open position exists
                </p>
              </div>
              <Switch
                checked={preventDuplicateSell}
                onCheckedChange={setPreventDuplicateSell}
                disabled={!smartTradeEnabled}
              />
            </div>

            {/* Max Position Size */}
            <div className="space-y-2">
              <Label>Maximum Position Size (Lots)</Label>
              <Input
                type="number"
                placeholder="No limit"
                value={maxPositionSize || ''}
                onChange={(e) =>
                  setMaxPositionSize(e.target.value ? parseInt(e.target.value, 10) : null)
                }
                min={0}
                disabled={!smartTradeEnabled}
              />
              <p className="text-xs text-muted-foreground">
                Maximum number of lots for F&O, quantity for equity (leave empty for no limit)
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Order Rules */}
        <Card>
          <CardHeader>
            <CardTitle>Order Rules</CardTitle>
            <CardDescription>Control order types and limits</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Max Order Value */}
            <div className="space-y-2">
              <Label>Maximum Order Value (₹)</Label>
              <Input
                type="number"
                placeholder="No limit"
                value={maxOrderValue || ''}
                onChange={(e) =>
                  setMaxOrderValue(e.target.value ? parseInt(e.target.value, 10) : null)
                }
                min={0}
                disabled={!smartTradeEnabled}
              />
              <p className="text-xs text-muted-foreground">
                Maximum order value in INR (leave empty for no limit)
              </p>
            </div>

            {/* Allow Intraday Only */}
            <div className="flex items-center justify-between">
              <div>
                <Label>Intraday Only (MIS)</Label>
                <p className="text-sm text-muted-foreground">Only allow MIS orders, block CNC/NRML</p>
              </div>
              <Switch
                checked={allowIntradayOnly}
                onCheckedChange={setAllowIntradayOnly}
                disabled={!smartTradeEnabled}
              />
            </div>

            {/* Block CNC Orders */}
            <div className="flex items-center justify-between">
              <div>
                <Label>Block CNC Orders</Label>
                <p className="text-sm text-muted-foreground">Block delivery (CNC) orders</p>
              </div>
              <Switch
                checked={blockCncOrders}
                onCheckedChange={setBlockCncOrders}
                disabled={!smartTradeEnabled || allowIntradayOnly}
              />
            </div>

            {/* Block NRML Orders */}
            <div className="flex items-center justify-between">
              <div>
                <Label>Block NRML Orders</Label>
                <p className="text-sm text-muted-foreground">Block carryforward (NRML) orders</p>
              </div>
              <Switch
                checked={blockNrmlOrders}
                onCheckedChange={setBlockNrmlOrders}
                disabled={!smartTradeEnabled || allowIntradayOnly}
              />
            </div>

            {/* Liquidity Fallback */}
            <div className="flex items-center justify-between">
              <div>
                <Label>Liquidity Fallback</Label>
                <p className="text-sm text-muted-foreground">
                  Auto-select most liquid strike when requested option has no buyers/sellers
                </p>
              </div>
              <Switch
                checked={liquidityFallback}
                onCheckedChange={setLiquidityFallback}
                disabled={!smartTradeEnabled}
              />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Save Button */}
      <div className="flex justify-end">
        <Button onClick={handleSave} disabled={isSaving} size="lg">
          <Save className="h-4 w-4 mr-2" />
          {isSaving ? 'Saving...' : 'Save Configuration'}
        </Button>
      </div>

      {/* Documentation */}
      <Card>
        <CardHeader>
          <CardTitle>About Smart Trade Rules</CardTitle>
        </CardHeader>
        <CardContent className="prose prose-sm dark:prose-invert max-w-none">
          <div className="space-y-4 text-muted-foreground">
            <p>
              Smart Trade Rules provide automated risk controls and position management for your trading
              operations. These rules are applied to all incoming orders before execution.
            </p>

            <div>
              <h4 className="text-base font-semibold mb-2 text-foreground">Position Rules:</h4>
              <ul className="space-y-1 list-disc list-inside text-sm">
                <li>
                  <strong>Prevent Duplicate BUY:</strong> Blocks BUY orders if you already have an open
                  position in that symbol. Useful to prevent accidentally doubling your position.
                </li>
                <li>
                  <strong>Prevent Duplicate SELL:</strong> Blocks SELL orders if you don't have an open
                  position. Prevents accidental short selling.
                </li>
                <li>
                  <strong>Maximum Position Size:</strong> Limits the number of lots for futures & options
                  or quantity for equity per symbol. Orders that would exceed this limit will be rejected.
                </li>
              </ul>
            </div>

            <div>
              <h4 className="text-base font-semibold mb-2 text-foreground">Order Rules:</h4>
              <ul className="space-y-1 list-disc list-inside text-sm">
                <li>
                  <strong>Maximum Order Value:</strong> Limits the total value (price × quantity) of any
                  single order. Helps prevent large accidental orders.
                </li>
                <li>
                  <strong>Intraday Only:</strong> When enabled, only MIS (intraday) orders are allowed.
                  CNC and NRML orders will be automatically blocked.
                </li>
                <li>
                  <strong>Block CNC Orders:</strong> Prevents delivery (CNC) orders from being placed.
                </li>
                <li>
                  <strong>Block NRML Orders:</strong> Prevents carryforward (NRML) orders from being
                  placed.
                </li>
              </ul>
            </div>

            <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-4 mt-4">
              <p className="text-sm">
                <span className="font-semibold">⚠️ Important:</span> These rules apply to all order
                placement methods including API, webhooks, TradingView, and manual orders. Make sure to
                test your configuration in Analyzer mode before enabling in live trading.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

