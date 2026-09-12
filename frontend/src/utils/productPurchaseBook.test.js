import { describe, expect, it } from 'vitest'
import {
  PRODUCT_BOOK_SELECTION_LIMIT,
  bookLineKey,
  productBookPreview,
  productBookCounts,
  removeProductBookLine,
  toProductBookCards,
  updateProductBookLineQuantity,
  upsertProductBookLine,
} from './productPurchaseBook'

const line = (overrides = {}) => ({
  card_id: 'sv1-1_en',
  quantity: 1,
  condition: 'NM',
  variant: 'Normal',
  lang: 'en',
  card: { name: 'Sprigatito', price_trend: 10 },
  ...overrides,
})

describe('productPurchaseBook', () => {
  it('merges identical catalogue lines by increasing quantity', () => {
    const merged = upsertProductBookLine([line()], line({ quantity: 2 }))
    expect(merged).toHaveLength(1)
    expect(merged[0].quantity).toBe(3)
  })

  it('keeps different condition or variant lines separate', () => {
    const merged = upsertProductBookLine([line()], line({ condition: 'LP', quantity: 1 }))
    expect(merged.map(entry => bookLineKey(entry))).toEqual([
      'sv1-1_en|NM|Normal|en',
      'sv1-1_en|LP|Normal|en',
    ])
  })

  it('does not exceed the book line limit', () => {
    const existing = Array.from({ length: PRODUCT_BOOK_SELECTION_LIMIT }, (_, index) => (
      line({ card_id: `card-${index}_en` })
    ))
    expect(upsertProductBookLine(existing, line({ card_id: 'overflow_en' }))).toHaveLength(
      PRODUCT_BOOK_SELECTION_LIMIT,
    )
  })

  it('updates quantity, removes lines, and serializes API cards', () => {
    const updated = updateProductBookLineQuantity([line()], line(), 4)
    expect(updated[0].quantity).toBe(4)
    expect(removeProductBookLine(updated, line())).toEqual([])
    expect(toProductBookCards(updated)).toEqual([{
      card_id: 'sv1-1_en',
      quantity: 4,
      condition: 'NM',
      variant: 'Normal',
      lang: 'en',
    }])
  })

  it('previews product P&L from live card prices minus purchase cost', () => {
    const preview = productBookPreview([
      line({ quantity: 2 }),
      line({ card_id: 'sv1-2_en', quantity: 1, card: { price_trend: 5 } }),
    ], 12)
    expect(preview).toEqual({ market: 25, cost: 12, pnl: 13, count: 3, rows: 2 })
  })

  it('counts distinct book lines separately from total copies', () => {
    expect(productBookCounts([
      line({ quantity: 2 }),
      line({ card_id: 'sv1-2_en', quantity: 3 }),
    ])).toEqual({ rows: 2, cards: 5 })
  })
})
