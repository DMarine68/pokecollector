import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import CardPricesTab from './CardPricesTab'

vi.mock('../contexts/SettingsContext', () => ({
  useSettings: () => ({
    t: (key, params) => {
      if (key === 'prices.multiplier') return '{mult}x vs raw'
      if (key === 'prices.salesVolumeYear') return `${params.count} sold in the last year`
      if (params?.lang) return `Price fallback from ${params.lang}`
      return key
    },
    formatPrice: val => val != null ? `€${Number(val).toFixed(2)}` : '-',
    formatUsdPrice: val => val != null ? `$${Number(val).toFixed(2)}` : '-',
    pricePrimary: 'trend',
    pricePrimaryField: 'price_trend',
    currency: 'EUR',
  }),
}))

vi.mock('@tanstack/react-query', () => ({
  useQuery: ({ queryKey }) => {
    if (queryKey[0] === 'pricecharting') {
      const cardId = queryKey[1]
      const liveData = {
        card_id: 'me04-111_en',
        search_url: 'https://www.pricecharting.com/search-products?type=prices&q=Misty%27s+Vitality+111',
        direct_url: "https://www.pricecharting.com/game/pokemon-pitch-black/misty's-vitality-111",
        has_live_data: true,
        sales_volume_year: 47,
        grades: [
          { id: 'ungraded', name: 'Ungraded', label: 'Raw / NM', price: 18.47, multiplier: 1.0 },
          { id: 'grade_7', name: 'Grade 7', label: 'Near Mint', price: 19.39, multiplier: 1.05 },
          { id: 'grade_8', name: 'Grade 8', label: 'NM-Mint', price: 24.93, multiplier: 1.35 },
          { id: 'grade_9', name: 'Grade 9', label: 'Mint', price: 62.50, multiplier: 3.38 },
          { id: 'grade_9_5', name: 'Grade 9.5', label: 'Gem Mint', price: 69.00, multiplier: 3.74 },
          { id: 'psa_10', name: 'PSA 10', label: 'Gem Mint / Pristine', price: 184.34, multiplier: 9.98, is_psa10: true },
        ],
      }
      if (cardId !== 'me04-111_en') {
        return { data: liveData, isFetching: true, isPending: false }
      }
      return { data: liveData, isFetching: false, isPending: false }
    }
    return { data: [], isLoading: false, isFetching: false, isPending: false }
  },
}))

vi.mock('../utils/cardmarket', () => ({
  cardmarketLinks: () => [
    { url: 'https://www.cardmarket.com/en/Pokemon/Products/Singles/Pitch-Black/Mistys-Vitality-V1-PBL111', label: 'Cardmarket Product' },
  ],
}))

describe('CardPricesTab', () => {
  it('renders custom card notice when card is custom', () => {
    const markup = renderToStaticMarkup(createElement(CardPricesTab, {
      card: { is_custom: true, name: 'Custom Charizard' },
    }))

    expect(markup).toContain('prices.customCardNoPrices')
  })

  it('renders price source attribution and PriceCharting graded cross-comparison', () => {
    const card = {
      id: 'me04-111_en',
      name: "Misty's Vitality",
      number: '111',
      price_trend: 18.47,
      price_market: 18.00,
      price_tcg_normal_market: 18.50,
      price_source_lang: 'en',
    }

    const markup = renderToStaticMarkup(createElement(CardPricesTab, {
      card,
      variant: 'Normal',
    }))

    // Price source attribution
    expect(markup).toContain('prices.sourceCardmarket')
    expect(markup).toContain('prices.sourceTcgplayer')
    expect(markup).toContain('prices.provider')
    expect(markup).toContain('Price fallback from EN')

    // PriceCharting section
    expect(markup).toContain('prices.pricechartingTitle')
    expect(markup).toContain('Ungraded')
    expect(markup).toContain('Grade 7')
    expect(markup).toContain('Grade 8')
    expect(markup).toContain('Grade 9')
    expect(markup).toContain('Grade 9.5')
    expect(markup).toContain('PSA 10')
    expect(markup).toContain('$184.34')
    expect(markup).toContain('47 sold in the last year')
    expect(markup).toContain('9.98x vs raw')
    expect(markup).toContain('prices.rawBaseline')
    expect(markup).not.toContain('{mult}')
    expect(markup).toContain("https://www.pricecharting.com/game/pokemon-pitch-black/misty&#x27;s-vitality-111")
  })

  it('renders collection position metrics when collectionItem is provided', () => {
    const card = {
      id: 'me04-111_en',
      name: "Misty's Vitality",
      number: '111',
      price_trend: 25.00,
      price_market: 25.00,
    }

    const collectionItem = {
      id: 1,
      quantity: 2,
      purchase_price: 20.00,
      variant: 'Normal',
    }

    const markup = renderToStaticMarkup(createElement(CardPricesTab, {
      card,
      variant: 'Normal',
      collectionItem,
    }))

    expect(markup).toContain('prices.collectionPosition')
    expect(markup).toContain('prices.buyPrice')
    expect(markup).toContain('prices.totalVal')
    expect(markup).toContain('€20.00')
    expect(markup).toContain('€50.00')
  })

  it('shows a loading state instead of another card\'s PriceCharting prices', () => {
    const markup = renderToStaticMarkup(createElement(CardPricesTab, {
      card: {
        id: 'sv1-1_en',
        name: 'Pikachu',
        number: '1',
        price_trend: 4.00,
      },
      variant: 'Normal',
    }))

    expect(markup).toContain('prices.pricechartingLoading')
    expect(markup).not.toContain('$184.34')
    expect(markup).not.toContain('47 sold in the last year')
  })
})
