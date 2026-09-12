import { describe, expect, it } from 'vitest'

import { productImageUrl, resolveCardImageUrl } from './imageUrl'

describe('productImageUrl', () => {
  it('uses the opaque product image proxy for configured images', () => {
    expect(productImageUrl({
      image_url: 'https://images.example.test/box.webp',
      image_proxy_url: '/api/images/product/42?token=signed',
    })).toBe('/api/images/product/42?token=signed')
  })

    it('uses the existing card back without a configured image', () => {
    expect(productImageUrl({ id: 42, image_url: null, image_proxy_url: null })).toBe('/cardback.jpg')
    expect(productImageUrl(null)).toBe('/cardback.jpg')
  })
})

describe('resolveCardImageUrl', () => {
  it('uses the same-origin proxy when a card id is present', () => {
    expect(resolveCardImageUrl({
      id: 'sv1-1_en',
      images: { small: 'https://assets.tcgdex.net/en/sv/sv1/1/low.webp' },
    })).toBe('/api/images/card/sv1-1_en/small')
    expect(resolveCardImageUrl({
      card_id: 'sv1-1_en',
      id: 99,
      images_large: 'https://assets.tcgdex.net/en/sv/sv1/1/high.webp',
    }, 'large')).toBe('/api/images/card/sv1-1_en/large')
  })
})
