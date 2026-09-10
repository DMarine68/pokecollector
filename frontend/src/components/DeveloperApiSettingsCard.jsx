import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Key, Eye, EyeOff, Copy, Check, RefreshCw, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { getDeveloperKey, generateDeveloperKey, revokeDeveloperKey } from '../api/client'
import { useConfirmDialog } from '../contexts/ConfirmDialogContext'

export default function DeveloperApiSettingsCard({ t }) {
  const queryClient = useQueryClient()
  const confirmDialog = useConfirmDialog()
  const [showKey, setShowKey] = useState(false)
  const [copiedKey, setCopiedKey] = useState(false)
  const [copiedUrl, setCopiedUrl] = useState(null)

  const { data: keyInfo, isLoading } = useQuery({
    queryKey: ['developer-key'],
    queryFn: getDeveloperKey,
  })

  const generateMut = useMutation({
    mutationFn: generateDeveloperKey,
    onSuccess: (data) => {
      queryClient.setQueryData(['developer-key'], data)
      toast.success(t('settings.apiKeyGenerated'))
      setShowKey(true)
    },
    onError: () => toast.error(t('settings.saveFailed')),
  })

  const revokeMut = useMutation({
    mutationFn: revokeDeveloperKey,
    onSuccess: () => {
      queryClient.setQueryData(['developer-key'], { has_key: false, api_key: null, created_at: null })
      toast.success(t('settings.apiKeyRevoked'))
      setShowKey(false)
    },
    onError: () => toast.error(t('settings.saveFailed')),
  })

  const handleCopyKey = () => {
    if (!keyInfo?.api_key) return
    navigator.clipboard.writeText(keyInfo.api_key)
    setCopiedKey(true)
    toast.success(t('settings.apiKeyCopied'))
    setTimeout(() => setCopiedKey(false), 2000)
  }

  const handleCopyUrl = (path) => {
    if (!keyInfo?.api_key) return
    const fullUrl = `${window.location.origin}${path}?api_key=${keyInfo.api_key}`
    navigator.clipboard.writeText(fullUrl)
    setCopiedUrl(path)
    toast.success(t('settings.urlCopied'))
    setTimeout(() => setCopiedUrl(null), 2000)
  }

  const handleRevoke = async () => {
    const confirmed = await confirmDialog({
      title: t('settings.revokeApiKey'),
      message: t('settings.revokeApiKeyConfirm'),
      confirmLabel: t('settings.revokeApiKey'),
      destructive: true,
    })
    if (confirmed) {
      revokeMut.mutate()
    }
  }

  return (
    <div
      className="rounded-2xl overflow-hidden p-4 space-y-4"
      style={{
        background: 'rgba(255,255,255,0.04)',
        border: '1px solid rgba(255,255,255,0.07)',
      }}
    >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Key size={16} className="text-brand-red" />
            <h4 className="text-sm font-semibold text-text-primary">
              {t('settings.apiKey')}
            </h4>
            {keyInfo?.has_key ? (
              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-green/15 text-green border border-green/30">
                {t('settings.activeKey')}
              </span>
            ) : (
              <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-white/5 text-text-muted border border-white/10">
                {t('settings.noApiKey')}
              </span>
            )}
          </div>
          <p className="text-xs text-text-muted mt-1 leading-relaxed">
            {t('settings.apiKeyDesc')}
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {keyInfo?.has_key ? (
            <>
              <button
                type="button"
                onClick={() => generateMut.mutate()}
                disabled={generateMut.isPending}
                className="btn-ghost text-xs px-2.5 py-1.5 flex items-center gap-1.5"
                title={t('settings.regenerateApiKey')}
              >
                <RefreshCw size={13} className={generateMut.isPending ? 'animate-spin' : ''} />
                {t('settings.regenerateApiKey')}
              </button>
              <button
                type="button"
                onClick={handleRevoke}
                disabled={revokeMut.isPending}
                className="btn-ghost text-xs px-2.5 py-1.5 text-brand-red hover:bg-brand-red/10 flex items-center gap-1.5"
                title={t('settings.revokeApiKey')}
              >
                <Trash2 size={13} />
                {t('settings.revokeApiKey')}
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={() => generateMut.mutate()}
              disabled={generateMut.isPending || isLoading}
              className="btn-primary text-xs px-3 py-1.5 flex items-center gap-1.5"
            >
              <Key size={13} />
              {t('settings.generateApiKey')}
            </button>
          )}
        </div>
      </div>

      {keyInfo?.has_key && (
        <div className="space-y-3 pt-2 border-t border-white/5">
          {/* Key display and copy */}
          <div className="flex items-center gap-2">
            <div className="flex-1 min-w-0 bg-bg-surface border border-border/80 rounded-xl px-3 py-2 flex items-center justify-between">
              <span className="font-mono text-xs text-text-primary select-all truncate">
                {showKey ? keyInfo.api_key : '••••••••••••••••••••••••••••••••••••••••••••'}
              </span>
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                className="text-text-muted hover:text-text-primary p-1 ml-2 flex-shrink-0"
                title={showKey ? t('settings.hideKey') : t('settings.showKey')}
              >
                {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
            <button
              type="button"
              onClick={handleCopyKey}
              className="btn-secondary text-xs px-3 py-2 flex items-center gap-1.5 flex-shrink-0"
            >
              {copiedKey ? <Check size={14} className="text-green" /> : <Copy size={14} />}
              {t('settings.copyApiKey')}
            </button>
          </div>

          {/* Endpoints listing */}
          <div className="mt-3 space-y-2">
            <p className="text-[11px] font-bold uppercase tracking-wider text-text-muted">
              {t('settings.apiEndpoints')}
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
              {[
                { label: t('settings.summaryEndpoint'), path: '/api/v1/summary', desc: 'M5 Paper / E-Ink' },
                { label: t('settings.cardsEndpoint'), path: '/api/v1/cards', desc: 'All Cards & Images' },
                { label: t('settings.bindersEndpoint'), path: '/api/v1/binders', desc: 'Binders & Lists' },
              ].map((ep) => (
                <div
                  key={ep.path}
                  className="rounded-xl border border-white/5 bg-bg-surface/50 p-2.5 flex flex-col justify-between"
                >
                  <div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-text-primary">{ep.label}</span>
                      <span className="text-[9px] font-semibold text-text-muted uppercase">{ep.desc}</span>
                    </div>
                    <code className="text-[11px] font-mono text-text-muted block mt-1 truncate">
                      {ep.path}
                    </code>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleCopyUrl(ep.path)}
                    className="mt-2.5 btn-ghost text-[11px] py-1 px-2 flex items-center justify-center gap-1.5 text-text-secondary hover:text-text-primary w-full border border-white/5"
                  >
                    {copiedUrl === ep.path ? <Check size={12} className="text-green" /> : <Copy size={12} />}
                    {t('settings.copyUrl')}
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
