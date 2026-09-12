import { useEffect, useId, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Check, Plus, Search, Trash2, X } from 'lucide-react'
import clsx from 'clsx'
import { searchCards } from '../api/client'
import { useSettings } from '../contexts/SettingsContext'
import { CARD_VARIANTS, getAvailableVariants, getDefaultVariant } from '../utils/cardVariants'
import { resolveCardImageUrl } from '../utils/imageUrl'
import { isValidMoneyInputValue, parseMoneyInputValue } from '../utils/moneyInput'
import { getEffectiveCardPrice } from '../utils/prices'
import {
  PRODUCT_BOOK_CONDITIONS,
  PRODUCT_BOOK_SELECTION_LIMIT,
  productBookPreview,
  productBookCounts,
  removeProductBookLine,
  toProductBookCards,
  updateProductBookLine,
  updateProductBookLineQuantity,
  upsertProductBookLine,
} from '../utils/productPurchaseBook'
import { normalizeTcgdexLanguage, tcgdexLanguageLabel } from '../utils/tcgdexLanguages'
import MoneyInput from './MoneyInput'
import TcgdexLanguageSelect from './TcgdexLanguageSelect'
import Modal from './ui/Modal'

const PRODUCT_TYPES = ['Booster Pack', 'Booster Box', 'Elite Trainer Box', 'Tin', 'Bundle', 'Collection Box', 'Blister', 'Other']

function cardLang(card, fallback) {
  return normalizeTcgdexLanguage(card?.lang || card?._lang || fallback)
}

function SearchResultRow({ card, defaultLang, formatPrice, priceField, t, onAdd, disabled }) {
  const [quantity, setQuantity] = useState(1)
  const [condition, setCondition] = useState('NM')
  const availableVariants = getAvailableVariants(card)
  const variants = availableVariants.length ? availableVariants : CARD_VARIANTS
  const [variant, setVariant] = useState(() => getDefaultVariant(card))
  const [lang, setLang] = useState(() => cardLang(card, defaultLang))
  const unitPrice = getEffectiveCardPrice(card, variant, priceField)

  return (
    <div className="flex items-start gap-3 p-3">
      <div className="h-14 w-10 flex-shrink-0 overflow-hidden rounded bg-bg-card">
        <img src={resolveCardImageUrl(card) || '/cardback.jpg'} alt="" className="h-full w-full object-cover" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-text-primary">{card.name}</p>
        <p className="truncate text-xs text-text-muted">
          {card.set_ref?.name || card.set_id || '-'} #{card.number || '?'}
          {unitPrice > 0 ? ` · ${formatPrice(unitPrice)}` : ''}
        </p>
        <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <input
            type="number"
            min="1"
            max="999"
            step="1"
            className="input px-2 py-1.5 text-sm"
            value={quantity}
            onChange={(event) => setQuantity(event.target.value)}
            aria-label={t('common.quantity')}
          />
          <select className="select py-1.5 text-sm" value={condition} onChange={(event) => setCondition(event.target.value)} aria-label={t('card.condition')}>
            {PRODUCT_BOOK_CONDITIONS.map(option => <option key={option} value={option}>{option}</option>)}
          </select>
          <select className="select py-1.5 text-sm" value={variant} onChange={(event) => setVariant(event.target.value)} aria-label={t('card.variant')}>
            {variants.map(option => <option key={option} value={option}>{option}</option>)}
          </select>
          <TcgdexLanguageSelect value={lang} onChange={setLang} compact className="select py-1.5 text-sm" />
        </div>
      </div>
      <button
        type="button"
        className="btn-primary shrink-0 px-3 py-1.5 text-xs"
        disabled={disabled}
        onClick={() => onAdd({
          card_id: card.id,
          quantity: Number(quantity) || 1,
          condition,
          variant,
          lang,
          card,
        })}
      >
        <Plus size={14} /> {t('products.addToBook')}
      </button>
    </div>
  )
}

export function PurchaseBookCardPicker({
  lines,
  onLinesChange,
  notice,
  onNoticeChange,
  formatPrice,
  priceField,
  t,
}) {
  const { settings } = useSettings()
  const defaultLang = normalizeTcgdexLanguage(settings.language)
  const [search, setSearch] = useState('')
  const [submittedSearch, setSubmittedSearch] = useState('')
  const searchQuery = submittedSearch.trim()

  useEffect(() => {
    const handle = setTimeout(() => setSubmittedSearch(search), 300)
    return () => clearTimeout(handle)
  }, [search])
  const { data, isFetching } = useQuery({
    queryKey: ['purchase-book-search', searchQuery],
    queryFn: () => searchCards({ name: searchQuery, page: 1, page_size: 20 }).then(response => response.data),
    enabled: searchQuery.length >= 2,
  })
  const results = data?.data || []
  const counts = useMemo(() => productBookCounts(lines), [lines])

  const addLine = (line) => {
    if (lines.length >= PRODUCT_BOOK_SELECTION_LIMIT && !lines.some(entry => (
      entry.card_id === line.card_id
      && entry.condition === line.condition
      && entry.variant === line.variant
      && entry.lang === line.lang
    ))) {
      onNoticeChange(t('products.bookSelectionMaximum').replace('{limit}', PRODUCT_BOOK_SELECTION_LIMIT))
      return
    }
    onLinesChange(upsertProductBookLine(lines, line))
    onNoticeChange(t('products.addedToBook').replace('{card}', line.card?.name || line.card_id))
  }

  return (
    <div className="space-y-4">
      <form
        className="relative"
        onSubmit={(event) => {
          event.preventDefault()
          setSubmittedSearch(search)
        }}
      >
        <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
        <input
          type="search"
          className="input pl-9 pr-20"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder={t('products.searchCatalogueCards')}
          autoFocus
        />
        <button type="submit" className="btn-ghost absolute right-1 top-1/2 -translate-y-1/2 px-3 py-1.5 text-xs">
          {t('common.search')}
        </button>
      </form>

      <div className="max-h-[28vh] divide-y divide-border overflow-y-auto rounded-xl border border-border bg-bg-elevated/30">
        {searchQuery.length < 2 ? (
          <p className="p-6 text-center text-sm text-text-muted">{t('products.searchCatalogueHint')}</p>
        ) : isFetching ? (
          <div className="skeleton m-3 h-24 rounded-lg" />
        ) : results.length ? results.map(card => (
          <SearchResultRow
            key={card.id}
            card={card}
            defaultLang={defaultLang}
            formatPrice={formatPrice}
            priceField={priceField}
            t={t}
            onAdd={addLine}
            disabled={false}
          />
        )) : (
          <p className="p-6 text-center text-sm text-text-muted">{t('products.noCatalogueResults')}</p>
        )}
      </div>

      {notice && (
        <p className="text-xs text-text-secondary" role="status" aria-live="polite">{notice}</p>
      )}

      <div>
        <div className="mb-2 flex items-center justify-between gap-3">
          <p className="text-sm font-medium text-text-primary">{t('products.bookTitle')}</p>
          <p className="text-xs text-text-muted">
            {t('products.selectedBookSummary')
              .replace('{rows}', counts.rows)
              .replace('{cards}', counts.cards)}
          </p>
        </div>
        <div className="max-h-[28vh] divide-y divide-border overflow-y-auto rounded-xl border border-border bg-bg-elevated/30">
          {lines.length ? lines.map(line => (
            <div key={`${line.card_id}|${line.condition}|${line.variant}|${line.lang}`} className="flex items-center gap-3 p-3">
              <div className="h-12 w-9 flex-shrink-0 overflow-hidden rounded bg-bg-card">
                <img src={resolveCardImageUrl(line.card) || '/cardback.jpg'} alt="" className="h-full w-full object-cover" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-text-primary">{line.card?.name || line.card_id}</p>
                <p className="truncate text-xs text-text-muted">
                  {line.card?.set_ref?.name || line.card?.set_id || '-'} #{line.card?.number || '?'} · {line.variant} · {line.condition} · {tcgdexLanguageLabel(line.lang)}
                </p>
              </div>
              <select
                className="select w-20 py-1.5 text-sm"
                value={line.condition}
                onChange={(event) => onLinesChange(updateProductBookLine(lines, line, { condition: event.target.value }))}
                aria-label={t('card.condition')}
              >
                {PRODUCT_BOOK_CONDITIONS.map(option => <option key={option} value={option}>{option}</option>)}
              </select>
              <input
                type="number"
                min="1"
                max="999"
                step="1"
                className="input w-16 px-2 py-1.5 text-sm"
                value={line.quantity}
                onChange={(event) => onLinesChange(updateProductBookLineQuantity(lines, line, event.target.value))}
                aria-label={t('common.quantity')}
              />
              <button
                type="button"
                className="btn-ghost h-10 w-10 px-0"
                onClick={() => onLinesChange(removeProductBookLine(lines, line))}
                aria-label={t('products.removeFromBook').replace('{card}', line.card?.name || line.card_id)}
              >
                <Trash2 size={14} />
              </button>
            </div>
          )) : (
            <p className="p-6 text-center text-sm text-text-muted">{t('products.emptyBook')}</p>
          )}
        </div>
      </div>
    </div>
  )
}

export default function PurchaseBookWizard({ isOpen, onClose, onSubmit, loading }) {
  const { t, formatPrice, exchangeRate, exchangeRateReady, pricePrimaryField } = useSettings()
  const today = new Date().toISOString().split('T')[0]
  const formId = useId()
  const fieldId = (name) => `${formId}-${name}`
  const [step, setStep] = useState(1)
  const [form, setForm] = useState({
    product_name: '',
    product_type: 'Booster Pack',
    purchase_price: '',
    purchase_date: today,
    notes: '',
  })
  const [lines, setLines] = useState([])
  const [notice, setNotice] = useState('')

  useEffect(() => {
    if (isOpen) return
    setStep(1)
    setForm({
      product_name: '',
      product_type: 'Booster Pack',
      purchase_price: '',
      purchase_date: today,
      notes: '',
    })
    setLines([])
    setNotice('')
  }, [isOpen, today])

  const purchasePriceValid = isValidMoneyInputValue(form.purchase_price)
  const canContinue = form.product_name.trim() && form.purchase_price !== '' && purchasePriceValid && exchangeRateReady
  const purchasePrice = purchasePriceValid ? parseMoneyInputValue(form.purchase_price, exchangeRate) : 0
  const preview = useMemo(
    () => productBookPreview(lines, purchasePrice, pricePrimaryField),
    [lines, purchasePrice, pricePrimaryField],
  )

  const finalize = () => {
    if (!canContinue || loading) return
    onSubmit({
      product: {
        product_name: form.product_name.trim(),
        product_type: form.product_type,
        purchase_price: purchasePrice,
        purchase_date: form.purchase_date || today,
        notes: form.notes.trim() || null,
        lifecycle_status: lines.length ? 'opened' : 'sealed',
      },
      cards: toProductBookCards(lines),
    })
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={() => {
        if (!loading) onClose()
      }}
      title={step === 1 ? t('products.addPurchase') : t('products.bookTitle')}
      size="xl"
    >
      <div className="space-y-4 p-4 sm:p-5">
        <p className="text-xs text-text-muted">
          {t('products.bookStep').replace('{step}', step).replace('{total}', 2)}
        </p>

        {step === 1 ? (
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <label htmlFor={fieldId('name')} className="mb-1 block text-xs text-text-muted">{t('products.productName')}</label>
              <input
                id={fieldId('name')}
                type="text"
                className="input"
                placeholder={t('products.productNamePlaceholder')}
                value={form.product_name}
                onChange={(event) => setForm(current => ({ ...current, product_name: event.target.value }))}
              />
            </div>
            <div>
              <label htmlFor={fieldId('type')} className="mb-1 block text-xs text-text-muted">{t('products.productType')}</label>
              <select
                id={fieldId('type')}
                className="select"
                value={form.product_type}
                onChange={(event) => setForm(current => ({ ...current, product_type: event.target.value }))}
              >
                {PRODUCT_TYPES.map(type => <option key={type} value={type}>{type}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor={fieldId('date')} className="mb-1 block text-xs text-text-muted">{t('products.purchaseDate')}</label>
              <input
                id={fieldId('date')}
                type="date"
                className="input"
                value={form.purchase_date}
                onChange={(event) => setForm(current => ({ ...current, purchase_date: event.target.value }))}
              />
            </div>
            <div className="col-span-2">
              <label htmlFor={fieldId('price')} className="mb-1 block text-xs text-text-muted">{t('products.purchasePrice')}</label>
              <MoneyInput
                id={fieldId('price')}
                value={form.purchase_price}
                onChange={(event) => setForm(current => ({ ...current, purchase_price: event.target.value }))}
              />
            </div>
            <div className="col-span-2">
              <label htmlFor={fieldId('notes')} className="mb-1 block text-xs text-text-muted">{t('products.notes')}</label>
              <input
                id={fieldId('notes')}
                type="text"
                className="input"
                placeholder={t('products.notesHint')}
                value={form.notes}
                onChange={(event) => setForm(current => ({ ...current, notes: event.target.value }))}
              />
            </div>
          </div>
        ) : (
          <>
            <PurchaseBookCardPicker
              lines={lines}
              onLinesChange={setLines}
              notice={notice}
              onNoticeChange={setNotice}
              formatPrice={formatPrice}
              priceField={pricePrimaryField}
              t={t}
            />
            {lines.length > 0 && (
              <div className="rounded-lg border border-border bg-bg-elevated/50 px-3 py-2 text-sm text-text-secondary">
                <p>{t('products.bookPreviewValue').replace('{value}', formatPrice(preview.market))}</p>
                <p className={clsx('font-semibold', preview.pnl >= 0 ? 'text-green' : 'text-brand-red')}>
                  {t('products.bookPreviewPnl').replace('{pnl}', `${preview.pnl >= 0 ? '+' : ''}${formatPrice(preview.pnl)}`)}
                </p>
              </div>
            )}
          </>
        )}

        <div className="sticky bottom-0 z-10 -mx-4 flex flex-col gap-2 border-t border-border bg-bg-surface px-4 pb-2 pt-3 sm:-mx-5 sm:flex-row sm:px-5">
          {step === 1 ? (
            <>
              <button type="button" className="btn-primary flex-1" disabled={!canContinue || loading} onClick={() => setStep(2)}>
                {t('products.continueToBook')}
              </button>
              <button type="button" className="btn-ghost flex-1" disabled={!canContinue || loading} onClick={finalize}>
                <Check size={14} /> {loading ? t('common.saving') : t('products.saveSealed')}
              </button>
              <button type="button" className="btn-ghost" disabled={loading} onClick={onClose}>
                <X size={14} /> {t('common.cancel')}
              </button>
            </>
          ) : (
            <>
              <button type="button" className="btn-ghost flex-1" disabled={loading} onClick={() => setStep(1)}>
                {t('common.back')}
              </button>
              <button type="button" className="btn-primary flex-1" disabled={!canContinue || loading} onClick={finalize}>
                <Check size={14} /> {loading ? t('common.saving') : t('products.finalizeBook')}
              </button>
              <button type="button" className="btn-ghost" disabled={loading} onClick={onClose}>
                <X size={14} /> {t('common.cancel')}
              </button>
            </>
          )}
        </div>
      </div>
    </Modal>
  )
}

export function ExistingPurchaseBookModal({ isOpen, onClose, product, onSubmit, loading }) {
  const { t, formatPrice, pricePrimaryField } = useSettings()
  const [lines, setLines] = useState([])
  const [notice, setNotice] = useState('')

  useEffect(() => {
    if (isOpen) return
    setLines([])
    setNotice('')
  }, [isOpen])

  return (
    <Modal
      isOpen={isOpen}
      onClose={() => {
        if (!loading) onClose()
      }}
      title={t('products.addCatalogueCardsTitle').replace('{product}', product?.product_name || '')}
      size="xl"
    >
      <div className="space-y-4 p-4 sm:p-5">
        <PurchaseBookCardPicker
          lines={lines}
          onLinesChange={setLines}
          notice={notice}
          onNoticeChange={setNotice}
          formatPrice={formatPrice}
          priceField={pricePrimaryField}
          t={t}
        />
        <div className="sticky bottom-0 z-10 flex gap-2 border-t border-border bg-bg-surface pt-3">
          <button
            type="button"
            className="btn-primary flex-1"
            disabled={!lines.length || loading}
            onClick={() => onSubmit(toProductBookCards(lines))}
          >
            <Check size={14} /> {loading ? t('common.saving') : t('products.finalizeBook')}
          </button>
          <button type="button" className="btn-ghost" disabled={loading} onClick={onClose}>
            <X size={14} /> {t('common.cancel')}
          </button>
        </div>
      </div>
    </Modal>
  )
}
