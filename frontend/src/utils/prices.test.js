import { describe, it, expect } from 'vitest'
import {
  formatSearchDisplayPrice,
  getEffectiveCardPrice,
  getSearchDisplayPrice,
  getTcgPlayerMarketPrice,
  normalizeSearchPriceSource,
} from './prices'

const card = {
  price_market: 10,
  price_trend: 12,
  price_tcg_normal_market: 8.5,
  price_tcg_holo_market: 9.25,
  price_pc_ungraded: 7.4,
}

describe('normalizeSearchPriceSource', () => {
  it('keeps supported sources and defaults anything else to cardmarket', () => {
    expect(normalizeSearchPriceSource('pricecharting')).toBe('pricecharting')
    expect(normalizeSearchPriceSource('tcgplayer')).toBe('tcgplayer')
    expect(normalizeSearchPriceSource('nope')).toBe('cardmarket')
    expect(normalizeSearchPriceSource(undefined)).toBe('cardmarket')
  })
})

describe('getTcgPlayerMarketPrice', () => {
  it('prefers normal, then holo, then reverse market', () => {
    expect(getTcgPlayerMarketPrice(card)).toBe(8.5)
    expect(getTcgPlayerMarketPrice({ price_tcg_holo_market: 3, price_tcg_reverse_market: 1 })).toBe(3)
    expect(getTcgPlayerMarketPrice({})).toBe(0)
  })

  it('prefers reverse then holo for Reverse Holo variants', () => {
    expect(getTcgPlayerMarketPrice(card, 'Reverse Holo')).toBe(9.25)
    expect(getTcgPlayerMarketPrice({
      price_tcg_normal_market: 8.5,
      price_tcg_reverse_market: 4.1,
    }, 'Reverse Holo')).toBe(4.1)
  })
})

describe('getEffectiveCardPrice', () => {
  it('converts TCGPlayer and PriceCharting USD to EUR for collection value', () => {
    expect(getEffectiveCardPrice(card, null, 'price_trend', 'tcgplayer', 0.91)).toBeCloseTo(7.735)
    expect(getEffectiveCardPrice(card, null, 'price_trend', 'pricecharting', 0.91)).toBeCloseTo(6.734)
  })

  it('falls back from missing PriceCharting cache to TCGPlayer', () => {
    expect(getEffectiveCardPrice(
      { ...card, price_pc_ungraded: null },
      null,
      'price_trend',
      'pricecharting',
      1,
    )).toBe(8.5)
  })

  it('keeps Cardmarket values in EUR', () => {
    expect(getEffectiveCardPrice(card, null, 'price_trend', 'cardmarket')).toBe(12)
  })
})

describe('getSearchDisplayPrice', () => {
  it('uses the Cardmarket primary field as EUR', () => {
    expect(getSearchDisplayPrice(card, 'cardmarket', 'price_trend')).toEqual({ amount: 12, unit: 'EUR' })
    expect(getEffectiveCardPrice(card, null, 'price_trend')).toBe(12)
  })

  it('uses TCGPlayer USD market when selected', () => {
    expect(getSearchDisplayPrice(card, 'tcgplayer')).toEqual({ amount: 8.5, unit: 'USD' })
  })

  it('uses cached PriceCharting ungraded USD when selected', () => {
    expect(getSearchDisplayPrice(card, 'pricecharting')).toEqual({ amount: 7.4, unit: 'USD' })
    expect(getSearchDisplayPrice({ ...card, price_pc_ungraded: null }, 'pricecharting')).toEqual({
      amount: 0,
      unit: 'USD',
    })
  })
})

describe('formatSearchDisplayPrice', () => {
  it('formats with the matching currency helper and hides empty prices', () => {
    const formatPrice = (amount) => `EUR:${amount}`
    const formatUsdPrice = (amount) => `USD:${amount}`
    expect(formatSearchDisplayPrice(card, 'cardmarket', 'price_trend', formatPrice, formatUsdPrice)).toBe('EUR:12')
    expect(formatSearchDisplayPrice(card, 'pricecharting', 'price_trend', formatPrice, formatUsdPrice)).toBe('USD:7.4')
    expect(formatSearchDisplayPrice({}, 'pricecharting', 'price_trend', formatPrice, formatUsdPrice)).toBeNull()
  })
})
