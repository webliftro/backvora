import { useState } from 'react'
import { Search, TrendingUp, Link2, Globe, BarChart3, ArrowRight } from 'lucide-react'
import { api } from '../api'
import { useNavigate } from 'react-router-dom'

interface Metrics {
  domain: string
  domain_rating: number | null
  ahrefs_rank: number | null
  organic_traffic: number | null
  organic_keywords: number | null
  referring_domains: number | null
  backlinks_count: number | null
}

function fmt(n: number | null | undefined): string {
  if (n == null) return '-'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return n.toLocaleString()
}

export default function CheckMetricsPage() {
  const [domain, setDomain] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [history, setHistory] = useState<Metrics[]>([])
  const navigate = useNavigate()

  async function check() {
    const d = domain.trim().toLowerCase().replace(/^https?:\/\//, '').replace(/\/.*$/, '')
    if (!d) return
    setLoading(true)
    setError('')
    try {
      const res = await api.checkMetrics(d)
      setMetrics(res.metrics)
      setHistory(prev => {
        const filtered = prev.filter(m => m.domain !== res.metrics.domain)
        return [res.metrics, ...filtered].slice(0, 20)
      })
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to fetch metrics')
      setMetrics(null)
    } finally {
      setLoading(false)
    }
  }

  function ratingColor(dr: number | null): string {
    if (dr == null) return 'text-gray-400'
    if (dr >= 70) return 'text-green-400'
    if (dr >= 40) return 'text-yellow-400'
    if (dr >= 20) return 'text-orange-400'
    return 'text-red-400'
  }

  const ic = 'w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-3 text-white placeholder-gray-400 focus:outline-none focus:border-pink-500 focus:ring-1 focus:ring-pink-500'

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-6 sm:mb-8">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2 sm:gap-3">
            <BarChart3 className="w-6 sm:w-7 h-6 sm:h-7 text-pink-500" />
            Check Metrics
          </h1>
          <p className="text-gray-400 mt-1 text-sm">Look up Ahrefs metrics for any domain before adding it</p>
        </div>
      </div>

      {/* Search */}
      <div className="bg-gray-800 rounded-xl p-4 sm:p-6 mb-6 border border-gray-700">
        <form onSubmit={e => { e.preventDefault(); check() }} className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
            <input
              type="text"
              value={domain}
              onChange={e => setDomain(e.target.value)}
              placeholder="Enter domain (e.g. example.com)"
              className={`${ic} pl-11`}
              autoFocus
            />
          </div>
          <button
            type="submit"
            disabled={loading || !domain.trim()}
            className="px-6 py-3 bg-pink-600 hover:bg-pink-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg font-medium transition-colors flex items-center gap-2"
          >
            {loading ? (
              <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <Search className="w-4 h-4" />
            )}
            Check
          </button>
        </form>
        {error && <p className="mt-3 text-red-400 text-sm">{error}</p>}
      </div>

      {/* Results */}
      {metrics && (
        <div className="bg-gray-800 rounded-xl p-4 sm:p-6 mb-6 border border-gray-700">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
            <h2 className="text-lg font-semibold flex items-center gap-2 truncate">
              <Globe className="w-5 h-5 text-gray-400 shrink-0" />
              <span className="truncate">{metrics.domain}</span>
            </h2>
            <button
              onClick={() => navigate('/domains/new', { state: { domain: metrics.domain, metrics } })}
              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm font-medium flex items-center gap-2 transition-colors self-start sm:self-auto shrink-0"
            >
              <span className="hidden sm:inline">Add to Domains</span><span className="sm:hidden">Add</span> <ArrowRight className="w-4 h-4" />
            </button>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 sm:gap-4">
            <div className="bg-gray-900 rounded-lg p-4">
              <div className="text-xs text-gray-400 mb-1">Domain Rating</div>
              <div className={`text-2xl font-bold ${ratingColor(metrics.domain_rating)}`}>
                {metrics.domain_rating ?? '-'}
              </div>
            </div>
            <div className="bg-gray-900 rounded-lg p-4">
              <div className="text-xs text-gray-400 mb-1">Ahrefs Rank</div>
              <div className="text-2xl font-bold text-white">{fmt(metrics.ahrefs_rank)}</div>
            </div>
            <div className="bg-gray-900 rounded-lg p-4">
              <div className="text-xs text-gray-400 mb-1 flex items-center gap-1"><TrendingUp className="w-3 h-3" /> Traffic</div>
              <div className="text-2xl font-bold text-white">{fmt(metrics.organic_traffic)}</div>
            </div>
            <div className="bg-gray-900 rounded-lg p-4">
              <div className="text-xs text-gray-400 mb-1">Keywords</div>
              <div className="text-2xl font-bold text-white">{fmt(metrics.organic_keywords)}</div>
            </div>
            <div className="bg-gray-900 rounded-lg p-4">
              <div className="text-xs text-gray-400 mb-1 flex items-center gap-1"><Link2 className="w-3 h-3" /> Ref. Domains</div>
              <div className="text-2xl font-bold text-white">{fmt(metrics.referring_domains)}</div>
            </div>
            <div className="bg-gray-900 rounded-lg p-4">
              <div className="text-xs text-gray-400 mb-1">Backlinks</div>
              <div className="text-2xl font-bold text-white">{fmt(metrics.backlinks_count)}</div>
            </div>
          </div>
        </div>
      )}

      {/* History */}
      {history.length > 1 && (
        <div className="bg-gray-800 rounded-xl p-4 sm:p-6 border border-gray-700">
          <h2 className="text-lg font-semibold mb-4">Recent Checks</h2>
          <div className="overflow-x-auto -mx-4 sm:mx-0">
          <table className="w-full min-w-[600px]">
            <thead>
              <tr className="text-xs text-gray-400 border-b border-gray-700">
                <th className="py-2 text-left">Domain</th>
                <th className="py-2 text-right">DR</th>
                <th className="py-2 text-right">Traffic</th>
                <th className="py-2 text-right">Keywords</th>
                <th className="py-2 text-right">Ref. Domains</th>
                <th className="py-2 text-right">Backlinks</th>
              </tr>
            </thead>
            <tbody>
              {history.slice(1).map(m => (
                <tr
                  key={m.domain}
                  className="border-b border-gray-700/50 text-sm cursor-pointer hover:bg-gray-700/30 transition-colors"
                  onClick={() => { setDomain(m.domain); setMetrics(m) }}
                >
                  <td className="py-2 font-medium">{m.domain}</td>
                  <td className={`py-2 text-right ${ratingColor(m.domain_rating)}`}>{m.domain_rating ?? '-'}</td>
                  <td className="py-2 text-right">{fmt(m.organic_traffic)}</td>
                  <td className="py-2 text-right">{fmt(m.organic_keywords)}</td>
                  <td className="py-2 text-right">{fmt(m.referring_domains)}</td>
                  <td className="py-2 text-right">{fmt(m.backlinks_count)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      )}
    </div>
  )
}
