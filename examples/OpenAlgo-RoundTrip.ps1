$apiKey = Read-Host 'OpenAlgo API key'

$baseRequest = @{
    apikey      = $apiKey
    strategy    = 'OpenAlgoRoundTripTest'
    underlying  = 'NIFTY'
    exchange    = 'NSE_INDEX'
    expiry_date = '23NOV26'
    offset      = 'ATM'
    quantity    = 65
    pricetype   = 'MARKET'
    product     = 'NRML'
    price       = 0
    trigger_price = 0
    disclosed_quantity = 0
}

$entryRequest = $baseRequest + @{ action = 'BUY' }
$body = $entryRequest | ConvertTo-Json -Depth 5 -Compress
$displayBody = $entryRequest.Clone()
$displayBody.apikey = '********'
Write-Host 'POST https://noviceorderflowtrader.in/api/v1/syntheticfutureorder'
Write-Host ($displayBody | ConvertTo-Json -Depth 5)

$entryResponse = Invoke-RestMethod -Method Post `
    -Uri 'https://noviceorderflowtrader.in/api/v1/syntheticfutureorder' `
    -ContentType 'application/json' `
    -Body $body

$entryResponse | ConvertTo-Json -Depth 10
if ($entryResponse.status -ne 'success' -or $entryResponse.results.Count -ne 2) {
    throw 'Synthetic future entry did not return two successful legs; not submitting a close.'
}

Read-Host 'Wait until both entry legs are filled, then press Enter to close (Ctrl+C to leave open)'

$closeLegs = @(
    foreach ($leg in $entryResponse.results) {
        if ($leg.status -ne 'success' -or -not $leg.symbol -or -not $leg.exchange) {
            throw 'Entry response is missing a successful leg symbol; cannot construct a safe close.'
        }

        @{
            symbol   = $leg.symbol
            exchange = $leg.exchange
            action   = if ($leg.action -eq 'BUY') { 'SELL' } else { 'BUY' }
            quantity = $baseRequest.quantity
            pricetype = 'MARKET'
            product  = $baseRequest.product
        }
    }
)

$closeRequest = @{
    apikey     = $apiKey
    strategy   = $baseRequest.strategy
    underlying = $baseRequest.underlying
    exchange   = $baseRequest.exchange
    action     = 'SELL'
    legs       = $closeLegs
}
$closeBody = $closeRequest | ConvertTo-Json -Depth 8 -Compress
$displayCloseRequest = $closeRequest.Clone()
$displayCloseRequest.apikey = '********'
Write-Host 'Submitting close basket:'
Write-Host ($displayCloseRequest | ConvertTo-Json -Depth 8)

$closeResponse = Invoke-RestMethod -Method Post `
    -Uri 'https://noviceorderflowtrader.in/api/v1/syntheticfutureorder' `
    -ContentType 'application/json' `
    -Body $closeBody

$closeResponse | ConvertTo-Json -Depth 10
if ($closeResponse.status -ne 'success') {
    throw 'Synthetic future close failed after retry; inspect the results and close any remaining leg manually.'
}
