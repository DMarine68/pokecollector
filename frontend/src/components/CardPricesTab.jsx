import React from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import {
  ExternalLink,
  TrendingUp,
  TrendingDown,
  Sparkles,
  Info,
  ShieldCheck,
  CheckCircle2,
  RefreshCw,
} from 'lucide-react'
import clsx from 'clsx'

import { useSettings } from '../contexts/SettingsContext'
import { getPriceHistory, getPriceCharting } from '../api/client'
import { getEffectiveCardPrice } from '../utils/prices'
import { cardmarketLinks } from '../utils/cardmarket'

const ALL_PRICE_KEYS = ['trend', 'avg', 'avg1', 'avg7', 'avg30', 'low']
const ALL_HOLO_PRICE_KEYS = ['trend-holo', 'avg-holo', 'avg1-holo', 'avg7-holo', 'avg30-holo', 'low-holo']

const PRICE_FIELD_MAP = {
  avg: 'price_market',
  market: 'price_market',
  low: 'price_low',
  trend: 'price_trend',
  avg1: 'price_avg1',
  avg7: 'price_avg7',
  avg30: 'price_avg30',
}

const HOLO_PRICE_FIELD_MAP = {
  'trend-holo': 'price_trend_holo',
  'avg-holo': 'price_market_holo',
  'avg1-holo': 'price_avg1_holo',
  'avg7-holo': 'price_avg7_holo',
  'avg30-holo': 'price_avg30_holo',
  'low-holo': 'price_low_holo',
}

function getPriceValue(card, priceKey) {
  const field = PRICE_FIELD_MAP[priceKey] || priceKey
  return (
    card?.[field]
    ?? card?.cardmarket?.prices?.[priceKey]
    ?? card?.pricing?.cardmarket?.[priceKey]
  )
}

export default function CardPricesTab({ card, variant = 'Normal', collectionItem = null }) {
  const {
    t,
    formatPrice,
    formatUsdPrice,
    pricePrimary,
    pricePrimaryField,
    currency,
  } = useSettings()

  const cardId = card?.id
  const isReverseHolo = variant === 'Reverse Holo'

  // 1. Price History Query
  const { data: priceHistory = [] } = useQuery({
    queryKey: ['price-history', cardId],
    queryFn: () => getPriceHistory(cardId).then(r => r.data),
    enabled: !!cardId && !card?.is_custom,
    staleTime: 1000 * 60 * 60,
  })

  // 2. PriceCharting Query
  const {
    data: pricechartingData,
    isFetching: isFetchingPricecharting,
    isPending: isPendingPricecharting,
  } = useQuery({
    queryKey: ['pricecharting', cardId],
    queryFn: () => getPriceCharting(cardId),
    enabled: !!cardId && !card?.is_custom,
    staleTime: 1000 * 60 * 30, // 30 minutes
    placeholderData: undefined,
  })
  const pricechartingForCard = pricechartingData?.card_id === cardId ? pricechartingData : null
  const isLoadingPricecharting = Boolean(
    cardId
    && !card?.is_custom
    && (isPendingPricecharting || isFetchingPricecharting)
    && !pricechartingForCard
  )

  if (!card) return null

  if (card.is_custom) {
    return (
      <div className="rounded-xl border border-border bg-bg-card p-6 text-center">
        <Info className="mx-auto mb-2 text-text-muted" size={28} />
        <p className="text-sm font-medium text-text-secondary">
          {t('prices.customCardNoPrices')}
        </p>
      </div>
    )
  }

  // --- Cardmarket breakdown ---
  const displayedPrices = ALL_PRICE_KEYS
    .map(key => {
      const val = getPriceValue(card, key)
      return val != null ? { key, val } : null
    })
    .filter(Boolean)

  const displayedHoloPrices = ALL_HOLO_PRICE_KEYS
    .map(key => {
      const field = HOLO_PRICE_FIELD_MAP[key]
      const val = card[field]
      const displayKey = key.replace('-holo', '')
      return val != null ? { key, displayKey, val } : null
    })
    .filter(Boolean)

  const selectedPriceBreakdown = isReverseHolo && displayedHoloPrices.length > 0
    ? displayedHoloPrices
    : displayedPrices.map(({ key, val }) => ({ key, displayKey: key, val }))

  const marketLinks = cardmarketLinks(card, variant)

  // --- TCGPlayer breakdown ---
  const tcgPrices = [
    card.price_tcg_normal_market != null
      ? { key: 'tcg-normal-market', val: card.price_tcg_normal_market, label: `${t('prices.normalVariant')} (${t('prices.tcgMarket')})` }
      : null,
    card.price_tcg_normal_low != null
      ? { key: 'tcg-normal-low', val: card.price_tcg_normal_low, label: `${t('prices.normalVariant')} (${t('prices.tcgLow')})` }
      : null,
    card.price_tcg_normal_mid != null
      ? { key: 'tcg-normal-mid', val: card.price_tcg_normal_mid, label: `${t('prices.normalVariant')} (${t('prices.tcgMid')})` }
      : null,
    card.price_tcg_reverse_market != null
      ? { key: 'tcg-reverse-market', val: card.price_tcg_reverse_market, label: `${t('prices.reverseVariant')} (${t('prices.tcgMarket')})` }
      : null,
    card.price_tcg_holo_market != null
      ? { key: 'tcg-holo-market', val: card.price_tcg_holo_market, label: `${t('prices.holoVariant')} (${t('prices.tcgMarket')})` }
      : null,
  ].filter(Boolean)

  // Primary effective price
  const effectivePrimaryPrice = getEffectiveCardPrice(card, variant, pricePrimaryField)
  const selectedPrimaryPrice = effectivePrimaryPrice > 0 ? effectivePrimaryPrice : getPriceValue(card, pricePrimary)

  // TCGPlayer search query URL
  const tcgplayerSearchUrl = `https://www.tcgplayer.com/search/all/product?q=${encodeURIComponent(`${card.name} ${card.number || ''}`.trim())}`

  // History settings
  const historyPriceField = ['price_market', 'price_trend', 'price_low'].includes(pricePrimaryField)
    ? pricePrimaryField
    : 'price_market'
  const historyDataKey = historyPriceField
  const historyPriceLabel = pricePrimaryField === historyPriceField ? t(`prices.${pricePrimary}`) : t('prices.avg')
  const safePriceHistory = Array.isArray(priceHistory) ? priceHistory : []

  // Collection position calculation
  const hasCollectionItem = collectionItem != null
  const marketPrice = effectivePrimaryPrice > 0 ? effectivePrimaryPrice : (card.price_market || 0)
  const buyPrice = collectionItem?.purchase_price
  const totalValue = marketPrice * (collectionItem?.quantity || 1)
  const hasGainLoss = buyPrice != null && buyPrice > 0 && marketPrice > 0
  const gainLossAmount = hasGainLoss ? marketPrice - buyPrice : 0
  const gainLossPercent = hasGainLoss ? ((marketPrice - buyPrice) / buyPrice) * 100 : 0

  return (
    <div className="space-y-4">
      {/* ── 1. COLLECTION POSITION (If inside Collection view) ── */}
      {hasCollectionItem && (
        <div className="rounded-xl border border-border bg-bg-card p-4">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wide text-text-muted">
              {t('prices.collectionPosition')}
            </span>
            <span className="text-xs font-semibold text-text-secondary">
              ×{collectionItem.quantity || 1} {variant || 'Normal'}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-lg border border-border/60 bg-bg-surface p-2.5">
              <p className="text-[11px] text-text-muted">{t('prices.marketPrice')}</p>
              <p className="mt-0.5 text-lg font-black text-green">
                {marketPrice > 0 ? formatPrice(marketPrice) : '—'}
              </p>
            </div>
            <div className="rounded-lg border border-border/60 bg-bg-surface p-2.5">
              <p className="text-[11px] text-text-muted">{t('prices.buyPrice')}</p>
              <p className="mt-0.5 text-lg font-black text-text-primary">
                {buyPrice ? formatPrice(buyPrice) : '—'}
              </p>
            </div>
            <div className="rounded-lg border border-border/60 bg-bg-surface p-2.5">
              <p className="text-[11px] text-text-muted">{t('prices.totalVal')}</p>
              <p className="mt-0.5 text-lg font-black text-text-primary">
                {marketPrice > 0 ? formatPrice(totalValue) : '—'}
              </p>
            </div>
            <div className="rounded-lg border border-border/60 bg-bg-surface p-2.5">
              <p className="text-[11px] text-text-muted">{t('prices.return')}</p>
              {hasGainLoss ? (
                <div className="mt-0.5 flex items-baseline gap-1">
                  <span className={clsx('text-lg font-black', gainLossAmount >= 0 ? 'text-green' : 'text-brand-red')}>
                    {gainLossAmount >= 0 ? '+' : ''}{formatPrice(gainLossAmount)}
                  </span>
                  <span className={clsx('text-xs font-bold', gainLossPercent >= 0 ? 'text-green' : 'text-brand-red')}>
                    ({gainLossPercent >= 0 ? '+' : ''}{gainLossPercent.toFixed(1)}%)
                  </span>
                </div>
              ) : (
                <p className="mt-0.5 text-lg font-black text-text-muted">—</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── 2. PRICE SOURCE ATTRIBUTION BANNER ── */}
      <div className="rounded-xl border border-border bg-bg-card p-4 space-y-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <span className="text-[11px] font-bold uppercase tracking-wider text-text-muted block">
              {t('prices.primaryPrice')} · {variant}
            </span>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="text-2xl font-black text-green">
                {selectedPrimaryPrice != null ? formatPrice(selectedPrimaryPrice) : '—'}
              </span>
              <span className="rounded-md border border-white/10 bg-white/5 px-2 py-0.5 text-xs font-medium text-text-secondary">
                {t(`prices.${pricePrimary}`)}
              </span>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            <span className="inline-flex items-center gap-1 rounded-full border border-border bg-bg-elevated px-2.5 py-1 font-semibold text-text-secondary">
              <ShieldCheck size={13} className="text-green" />
              <span>{t('prices.sourceCardmarket')}</span>
            </span>
            {tcgPrices.length > 0 && (
              <span className="inline-flex items-center gap-1 rounded-full border border-border bg-bg-elevated px-2.5 py-1 font-semibold text-blue-400">
                <span>{t('prices.sourceTcgplayer')}</span>
              </span>
            )}
            <span className="inline-flex items-center rounded-full border border-border bg-bg-elevated px-2.5 py-1 text-text-muted">
              {t('prices.provider')}: {t('prices.tcgdexProvider')}
            </span>
          </div>
        </div>

        {/* Fallback Notice */}
        {card.price_source_lang && (
          <div className="flex items-center gap-2 rounded-lg border border-yellow/30 bg-yellow/10 px-3 py-1.5 text-xs text-yellow">
            <Info size={14} className="shrink-0" />
            <span>{t('prices.priceFallbackNotice', { lang: card.price_source_lang.toUpperCase() }).replace('{lang}', card.price_source_lang.toUpperCase())}</span>
          </div>
        )}
      </div>

      {/* ── 3. PRICECHARTING: UNGRADED VS PSA GRADES CROSS-COMPARISON ── */}
      <div className="rounded-xl border border-border bg-bg-card p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-black text-text-primary">
                {t('prices.pricechartingTitle')}
              </h3>
              {isLoadingPricecharting ? (
                <span className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] font-bold text-text-muted">
                  <RefreshCw size={11} className="animate-spin" />
                  {t('prices.pricechartingLoading')}
                </span>
              ) : pricechartingForCard?.has_live_data ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-green/15 px-2 py-0.5 text-[10px] font-bold text-green">
                  <CheckCircle2 size={11} />
                  {t('prices.liveData')}
                </span>
              ) : (
                <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] font-medium text-text-muted">
                  {t('prices.marketEstimate')}
                </span>
              )}
            </div>
            <p className="text-xs text-text-muted mt-0.5">
              {t('prices.pricechartingSubtitle')}
            </p>
          </div>

          {pricechartingForCard?.search_url && (
            <a
              href={pricechartingForCard.search_url}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-ghost inline-flex items-center gap-1.5 text-xs font-bold text-brand-red hover:text-brand-red-light"
            >
              <ExternalLink size={13} />
              <span>{t('prices.comparePricecharting')}</span>
            </a>
          )}
        </div>

        {/* Grades Comparison Grid */}
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          {(isLoadingPricecharting
            ? [
              { id: 'ungraded', name: t('prices.ungraded'), label: t('prices.ungradedDesc'), loading: true },
              { id: 'grade_7', name: t('prices.grade7'), label: t('prices.grade7Desc'), loading: true },
              { id: 'grade_8', name: t('prices.grade8'), label: t('prices.grade8Desc'), loading: true },
              { id: 'grade_9', name: t('prices.grade9'), label: t('prices.grade9Desc'), loading: true },
              { id: 'grade_9_5', name: t('prices.grade95'), label: t('prices.grade95Desc'), loading: true },
              { id: 'psa_10', name: t('prices.psa10'), label: t('prices.psa10Desc'), loading: true, is_psa10: true },
            ]
            : (pricechartingForCard?.grades || [])
          ).map(grade => {
            const isPsa10 = grade.is_psa10 || grade.id === 'psa_10'
            return (
              <div
                key={grade.id}
                className={clsx(
                  'relative rounded-xl border p-2.5 transition-colors',
                  isPsa10
                    ? 'border-yellow/40 bg-yellow/10 shadow-[0_0_12px_rgba(234,179,8,0.1)]'
                    : 'border-border/70 bg-bg-surface'
                )}
              >
                {isPsa10 && (
                  <span className="absolute -top-2 right-2 inline-flex items-center gap-0.5 rounded-full bg-yellow px-1.5 py-0.2 text-[9px] font-black uppercase text-black">
                    <Sparkles size={10} />
                    Top Grade
                  </span>
                )}
                <p className={clsx('text-xs font-black', isPsa10 ? 'text-yellow' : 'text-text-primary')}>
                  {grade.name}
                </p>
                <p className="text-[10px] text-text-muted truncate">
                  {grade.label}
                </p>
                <p className="mt-2 text-sm font-black text-text-primary">
                  {grade.loading ? (
                    <span className="inline-flex items-center gap-1 text-text-muted">
                      <RefreshCw size={12} className="animate-spin" />
                      {t('prices.pricechartingLoading')}
                    </span>
                  ) : grade.price != null ? formatUsdPrice(grade.price) : '—'}
                </p>
                {grade.loading ? null : grade.id === 'ungraded' ? (
                  <span className="mt-1 inline-block text-[10px] font-bold text-text-muted">
                    {t('prices.rawBaseline')}
                  </span>
                ) : grade.multiplier != null ? (
                  <span className="mt-1 inline-block text-[10px] font-bold text-text-muted">
                    {t('prices.multiplier', { mult: grade.multiplier }).replace('{mult}', grade.multiplier)}
                  </span>
                ) : null}
              </div>
            )
          })}
        </div>
        {!isLoadingPricecharting && Number.isFinite(pricechartingForCard?.sales_volume_year) ? (
          <p className="text-[11px] font-semibold text-text-secondary">
            {t('prices.salesVolumeYear', { count: pricechartingForCard.sales_volume_year })}
          </p>
        ) : null}
      </div>

      {/* ── 4. CARDMARKET PRICES BREAKDOWN ── */}
      {selectedPriceBreakdown.length > 0 && (
        <div className="rounded-xl border border-border bg-bg-card p-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs font-bold uppercase tracking-wide text-text-muted">
              {t('prices.cardmarketTitle')} · {variant}
            </span>
            {marketLinks.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {marketLinks.map(link => (
                  <a
                    key={link.productId || link.url}
                    href={link.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-ghost inline-flex items-center gap-1.5 text-xs font-semibold"
                  >
                    <ExternalLink size={13} />
                    <span>{link.fallback ? t('cardmarket.search') : link.label || t('cardmarket.openProduct')}</span>
                  </a>
                ))}
              </div>
            )}
          </div>
          <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 text-xs border-t border-border pt-2.5">
            {selectedPriceBreakdown.map(({ key, displayKey, val }) => (
              <div key={key} className="rounded-lg bg-bg-surface p-2 border border-border/50">
                <span className="text-text-muted text-[11px] block">{t(`prices.${displayKey}`)}</span>
                <p className={displayKey === 'trend' ? 'text-green font-bold text-sm mt-0.5' : 'text-text-primary font-bold text-sm mt-0.5'}>
                  {formatPrice(val)}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── 5. TCGPLAYER PRICES BREAKDOWN ── */}
      {tcgPrices.length > 0 && (
        <div className="rounded-xl border border-border bg-bg-card p-4 space-y-3">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <span className="text-xs font-bold uppercase tracking-wide text-text-muted">
              {t('prices.tcgplayerTitle')} (USD)
            </span>
            <a
              href={tcgplayerSearchUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-ghost inline-flex items-center gap-1.5 text-xs font-semibold text-blue-400"
            >
              <ExternalLink size={13} />
              <span>{t('prices.searchTcgplayer')}</span>
            </a>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
            {tcgPrices.map(({ key, val, label }) => (
              <div key={key} className="rounded-lg bg-bg-surface p-2.5 border border-border/50">
                <span className="text-text-muted text-[11px] block">{label}</span>
                <span className="font-bold text-blue-400 text-sm mt-0.5 block">{formatUsdPrice(val)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── 6. PRICE HISTORY CHART ── */}
      {safePriceHistory.length > 0 && (
        <div className="rounded-xl border border-border bg-bg-card p-4 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wide text-text-muted">
              {t('prices.history')}
            </span>
            {(() => {
              const first = safePriceHistory[0]?.[historyDataKey]
              const last = safePriceHistory[safePriceHistory.length - 1]?.[historyDataKey]
              if (first && last && first > 0) {
                const change = ((last - first) / first) * 100
                return (
                  <span className={clsx('text-xs font-bold flex items-center gap-1', change >= 0 ? 'text-green' : 'text-brand-red')}>
                    {change >= 0 ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
                    <span>{change >= 0 ? '+' : ''}{change.toFixed(1)}% {t('prices.sinceTracking')}</span>
                  </span>
                )
              }
              return null
            })()}
          </div>
          <div className="h-[140px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={safePriceHistory} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#22c55e" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="#22c55e" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 10, fill: '#606078' }}
                  tickFormatter={(d) => {
                    try {
                      return new Date(d).toLocaleDateString('en-US', { day: '2-digit', month: '2-digit' })
                    } catch {
                      return ''
                    }
                  }}
                  axisLine={false}
                  tickLine={false}
                  minTickGap={30}
                />
                <YAxis
                  tick={{ fontSize: 10, fill: '#606078' }}
                  tickFormatter={(v) => {
                    try {
                      return formatPrice(Number(v))
                    } catch {
                      return ''
                    }
                  }}
                  axisLine={false}
                  tickLine={false}
                  width={45}
                  domain={['auto', 'auto']}
                />
                <Tooltip
                  contentStyle={{
                    background: 'rgba(20,20,34,0.95)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: '0.75rem',
                    fontSize: '0.75rem',
                  }}
                  labelFormatter={(d) => {
                    try {
                      return new Date(d).toLocaleDateString('en-US', { day: '2-digit', month: 'short', year: 'numeric' })
                    } catch {
                      return ''
                    }
                  }}
                  formatter={(val) => {
                    try {
                      return [formatPrice(Number(val)), historyPriceLabel]
                    } catch {
                      return ['', '']
                    }
                  }}
                />
                <Area
                  type="monotone"
                  dataKey={historyDataKey}
                  stroke="#22c55e"
                  fill="url(#priceGrad)"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 3, fill: '#22c55e', stroke: 'none' }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  )
}
