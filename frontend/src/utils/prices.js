export const PRICE_PRIMARY_TO_FIELD = {
  market: 'price_market',
  avg: 'price_market',
  trend: 'price_trend',
  avg1: 'price_avg1',
  avg7: 'price_avg7',
  avg30: 'price_avg30',
  low: 'price_low',
}

export const SEARCH_PRICE_SOURCES = ['cardmarket', 'tcgplayer', 'pricecharting']
export const DEFAULT_SEARCH_PRICE_SOURCE = 'cardmarket'
export const DEFAULT_USD_TO_EUR = 0.91

export const REVERSE_HOLO_VARIANTS = new Set(['Reverse Holo'])
export const HOLO_VARIANTS = new Set(['Holo'])

export const HOLO_FIELD_MAP = {
  price_market: 'price_market_holo',
  price_trend: 'price_trend_holo',
  price_avg1: 'price_avg1_holo',
  price_avg7: 'price_avg7_holo',
  price_avg30: 'price_avg30_holo',
  price_low: 'price_low_holo',
}

export function priceFieldFromPrimary(pricePrimary) {
  return PRICE_PRIMARY_TO_FIELD[pricePrimary] || 'price_trend'
}

export function normalizeSearchPriceSource(value) {
  return SEARCH_PRICE_SOURCES.includes(value) ? value : DEFAULT_SEARCH_PRICE_SOURCE
}

function positivePrice(value) {
  if (value == null) return null
  const price = Number(value)
  return Number.isFinite(price) && price > 0 ? price : null
}

function usdToEur(usd, rate) {
  const convertedRate = Number(rate)
  const safeRate = Number.isFinite(convertedRate) && convertedRate > 0 ? convertedRate : DEFAULT_USD_TO_EUR
  return usd * safeRate
}

export function getTcgPlayerMarketPrice(card, variant = null) {
  if (!card) return 0
  const normal = positivePrice(card.price_tcg_normal_market)
  const holo = positivePrice(card.price_tcg_holo_market)
  const reverse = positivePrice(card.price_tcg_reverse_market)
  const order = REVERSE_HOLO_VARIANTS.has(variant)
    ? [reverse, holo, normal]
    : HOLO_VARIANTS.has(variant)
      ? [holo, normal, reverse]
      : [normal, holo, reverse]
  for (const candidate of order) {
    if (candidate != null) return candidate
  }
  return 0
}

function cardmarketPrice(card, variant, priceField) {
  if (REVERSE_HOLO_VARIANTS.has(variant)) {
    const holoField = HOLO_FIELD_MAP[priceField]
    const candidates = [
      holoField ? card[holoField] : null,
      card[priceField],
      card.price_market_holo,
      card.price_market,
    ]
    for (const candidate of candidates) {
      const price = positivePrice(candidate)
      if (price != null) return price
    }
    return 0
  }

  for (const candidate of [card[priceField], card.price_market]) {
    const price = positivePrice(candidate)
    if (price != null) return price
  }
  return 0
}

export function getEffectiveCardPrice(
  card,
  variant,
  priceField = 'price_trend',
  priceSource = DEFAULT_SEARCH_PRICE_SOURCE,
  usdToEurRate = DEFAULT_USD_TO_EUR,
) {
  if (!card) return 0
  const source = normalizeSearchPriceSource(priceSource)
  if (source === 'pricecharting') {
    const usd = positivePrice(card.price_pc_ungraded) || getTcgPlayerMarketPrice(card, variant)
    return usd ? usdToEur(usd, usdToEurRate) : 0
  }
  if (source === 'tcgplayer') {
    const usd = getTcgPlayerMarketPrice(card, variant)
    return usd ? usdToEur(usd, usdToEurRate) : 0
  }
  return cardmarketPrice(card, variant, priceField)
}

export function getSearchDisplayPrice(card, source = DEFAULT_SEARCH_PRICE_SOURCE, priceField = 'price_trend') {
  const normalized = normalizeSearchPriceSource(source)
  if (normalized === 'pricecharting') {
    return { amount: positivePrice(card?.price_pc_ungraded) || 0, unit: 'USD' }
  }
  if (normalized === 'tcgplayer') {
    return { amount: getTcgPlayerMarketPrice(card), unit: 'USD' }
  }
  return { amount: getEffectiveCardPrice(card, null, priceField), unit: 'EUR' }
}

export function formatSearchDisplayPrice(card, source, priceField, formatPrice, formatUsdPrice) {
  const display = getSearchDisplayPrice(card, source, priceField)
  if (!(display.amount > 0)) return null
  return display.unit === 'USD' ? formatUsdPrice(display.amount) : formatPrice(display.amount)
}
