import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import DeveloperApiSettingsCard from './DeveloperApiSettingsCard'

let mockKeyData = {
  has_key: false,
  api_key: null,
  created_at: null,
}

vi.mock('@tanstack/react-query', () => ({
  useQuery: () => ({
    data: mockKeyData,
    isLoading: false,
  }),
  useMutation: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
  useQueryClient: () => ({
    setQueryData: vi.fn(),
  }),
}))

vi.mock('../contexts/ConfirmDialogContext', () => ({
  useConfirmDialog: () => vi.fn().mockResolvedValue(true),
}))

vi.mock('../api/client', () => ({
  getDeveloperKey: vi.fn(),
  generateDeveloperKey: vi.fn(),
  revokeDeveloperKey: vi.fn(),
}))

describe('DeveloperApiSettingsCard', () => {
  const t = (key) => key

  it('renders unconfigured state when no API key exists', () => {
    mockKeyData = { has_key: false, api_key: null, created_at: null }
    const markup = renderToStaticMarkup(createElement(DeveloperApiSettingsCard, { t }))

    expect(markup).toContain('settings.apiKey')
    expect(markup).toContain('settings.noApiKey')
    expect(markup).toContain('settings.generateApiKey')
    expect(markup).not.toContain('settings.regenerateApiKey')
  })

  it('renders active key and endpoints when API key exists', () => {
    mockKeyData = {
      has_key: true,
      api_key: 'pk_live_0123456789abcdef0123456789abcdef',
      created_at: '2026-09-09T22:00:00Z',
    }
    const markup = renderToStaticMarkup(createElement(DeveloperApiSettingsCard, { t }))

    expect(markup).toContain('settings.apiKey')
    expect(markup).toContain('settings.activeKey')
    expect(markup).toContain('settings.regenerateApiKey')
    expect(markup).toContain('settings.revokeApiKey')
    expect(markup).toContain('settings.copyApiKey')
    expect(markup).toContain('/api/v1/summary')
    expect(markup).toContain('/api/v1/cards')
    expect(markup).toContain('/api/v1/binders')
  })
})
