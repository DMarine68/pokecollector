import { getEffectiveCardPrice } from './prices'

export const PRODUCT_BOOK_SELECTION_LIMIT = 200
export const PRODUCT_BOOK_CONDITIONS = ['Mint', 'NM', 'LP', 'MP', 'HP']

export function bookLineKey({ card_id, condition = 'NM', variant = 'Normal', lang = 'en' }) {
  return [card_id, condition || 'NM', variant || 'Normal', lang || 'en'].join('|')
}

function normalizedQuantity(value) {
  const quantity = Number(value)
  if (!Number.isInteger(quantity)) return 1
  return Math.max(1, Math.min(999, quantity))
}

export function upsertProductBookLine(lines, line) {
  const quantity = normalizedQuantity(line.quantity)
  const nextLine = {
    card_id: line.card_id,
    quantity,
    condition: line.condition || 'NM',
    variant: line.variant || 'Normal',
    lang: line.lang || 'en',
    card: line.card || null,
  }
  const key = bookLineKey(nextLine)
  const existingIndex = lines.findIndex(entry => bookLineKey(entry) === key)
  if (existingIndex === -1) {
    if (lines.length >= PRODUCT_BOOK_SELECTION_LIMIT) return lines
    return [...lines, nextLine]
  }

  const next = [...lines]
  next[existingIndex] = {
    ...next[existingIndex],
    ...nextLine,
    quantity: Math.min(999, next[existingIndex].quantity + quantity),
    card: nextLine.card || next[existingIndex].card,
  }
  return next
}

export function updateProductBookLineQuantity(lines, line, quantity) {
  const key = bookLineKey(line)
  return lines.map(entry => (
    bookLineKey(entry) === key
      ? { ...entry, quantity: normalizedQuantity(quantity) }
      : entry
  ))
}

export function updateProductBookLine(lines, line, patch) {
  const key = bookLineKey(line)
  return lines.map(entry => {
    if (bookLineKey(entry) !== key) return entry
    return { ...entry, ...patch }
  })
}

export function removeProductBookLine(lines, line) {
  const key = bookLineKey(line)
  return lines.filter(entry => bookLineKey(entry) !== key)
}

export function productBookCounts(lines) {
  return {
    rows: lines.length,
    cards: lines.reduce((sum, line) => sum + (Number(line.quantity) || 0), 0),
  }
}

export function productBookMarketValue(lines, priceField = 'price_trend') {
  return lines.reduce((sum, line) => (
    sum + (getEffectiveCardPrice(line.card, line.variant, priceField) * (line.quantity || 0))
  ), 0)
}

export function productBookPreview(lines, purchasePrice, priceField = 'price_trend') {
  const market = productBookMarketValue(lines, priceField)
  const cost = Number(purchasePrice) || 0
  const counts = productBookCounts(lines)
  return {
    market,
    cost,
    pnl: market - cost,
    count: counts.cards,
    rows: counts.rows,
  }
}

export function toProductBookCards(lines) {
  return lines.map(line => ({
    card_id: line.card_id,
    quantity: line.quantity,
    condition: line.condition,
    variant: line.variant,
    lang: line.lang,
  }))
}
