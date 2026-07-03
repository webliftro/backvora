import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Plus, ExternalLink, Trash2 } from 'lucide-react';
import { api } from '../api';
import { useToast } from '../components/Toast';
import Modal from '../components/Modal';
import { PageHeader, EmptyState, Button, ResultBanner, LoadingState } from '../components/ui';
import type { BannerTone } from '../components/styles';
import type { Competitor } from '../types';

export default function CompetitorsPage() {
  const { toast } = useToast();
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [domain, setDomain] = useState('');
  const [limit, setLimit] = useState(100);
  const [fetching, setFetching] = useState(false);
  const [fetchResult, setFetchResult] = useState<{ tone: BannerTone; message: string } | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  useEffect(() => { loadCompetitors(); }, []);

  async function loadCompetitors() {
    try { const d = await api.getCompetitors(); setCompetitors(d.items || []); }
    catch { toast('Failed to load competitors', 'error'); }
    finally { setLoading(false); }
  }

  async function handleRemove(competitorDomain: string) {
    if (!confirm(`Remove ${competitorDomain} and all its backlink data?`)) return;
    setDeleting(competitorDomain);
    try {
      const data = await api.removeCompetitor(competitorDomain, true, false);
      toast(`Removed ${competitorDomain}: ${data.backlinks_deleted} backlinks deleted`, 'success');
      loadCompetitors();
    } catch (e: any) { toast(`Failed to remove: ${e.message}`, 'error'); }
    finally { setDeleting(null); }
  }

  async function handleFetch(e: React.FormEvent) {
    e.preventDefault();
    if (!domain.trim()) return;
    setFetching(true);
    setFetchResult({ tone: 'progress', message: 'Fetching backlinks from Ahrefs...' });
    try {
      const data = await api.fetchBacklinks(domain.trim(), limit);
      if (data.success) {
        setFetchResult({ tone: 'success', message: `Fetched ${data.total_fetched} backlinks → ${data.domains_added} new domains, ${data.backlinks_added} backlinks recorded.` });
        loadCompetitors();
      } else setFetchResult({ tone: 'error', message: 'Error fetching backlinks' });
    } catch (e: any) { setFetchResult({ tone: 'error', message: `Error: ${e.message}` }); }
    finally { setFetching(false); }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Competitors"
        actions={
          <Button onClick={() => { setModalOpen(true); setFetchResult(null); }} variant="primary" icon={Plus}>
            <span className="hidden sm:inline">Fetch Competitor Backlinks</span><span className="sm:hidden">Fetch</span>
          </Button>
        }
      />
      {loading ? <LoadingState label="Loading competitors..." /> : competitors.length === 0 ? (
        <EmptyState title="No competitors yet" hint="Fetch competitor backlinks to get started" />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {competitors.map(c => (
            <div key={c.domain} className="bg-gray-800 rounded-lg p-4 sm:p-6 border border-gray-700 hover:border-pink-500 transition-colors relative">
              <button
                onClick={() => handleRemove(c.domain)}
                disabled={deleting === c.domain}
                className="absolute top-3 right-3 p-1.5 text-gray-500 hover:text-red-400 hover:bg-gray-700 rounded transition-colors disabled:opacity-50"
                title="Remove competitor"
              >
                <Trash2 className="w-4 h-4" />
              </button>
              <Link to={`/domains?target=${encodeURIComponent(c.domain)}`} className="block">
              <div className="flex justify-between items-start mb-3">
                <div>
                  <h3 className="font-mono text-base font-semibold">{c.domain}</h3>
                  <a href={`https://${c.domain}`} target="_blank" rel="noopener" onClick={e => e.stopPropagation()}
                    className="text-gray-500 hover:text-gray-300 text-xs flex items-center gap-1"><ExternalLink className="w-3 h-3" /> visit</a>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3 mt-4">
                <div><div className="text-xs text-gray-400">Referring Domains</div><div className="text-xl font-bold text-pink-500">{(c.referring_domains || 0).toLocaleString()}</div></div>
                <div><div className="text-xs text-gray-400">Total Backlinks</div><div className="text-xl font-bold">{(c.backlink_count || 0).toLocaleString()}</div></div>
                <div><div className="text-xs text-gray-400">Avg. DR</div><div className="text-lg font-semibold">{c.avg_dr ?? '-'}</div></div>
                <div><div className="text-xs text-gray-400">Avg. Traffic</div><div className="text-lg font-semibold">{c.avg_traffic?.toLocaleString() ?? '-'}</div></div>
              </div>
              </Link>
            </div>
          ))}
        </div>
      )}
      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="Fetch Competitor Backlinks">
        <form onSubmit={handleFetch}>
          <div className="mb-4">
            <label className="block text-sm text-gray-400 mb-2">Competitor Domain</label>
            <input type="text" value={domain} onChange={e => setDomain(e.target.value)} placeholder="e.g., competitor.com" required
              className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-pink-500" />
          </div>
          <div className="mb-4">
            <label className="block text-sm text-gray-400 mb-2">Max backlinks</label>
            <input type="number" value={limit} onChange={e => setLimit(Number(e.target.value))} min={1} max={1000}
              className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-pink-500" />
          </div>
          {fetchResult && <ResultBanner tone={fetchResult.tone} className="mb-4">{fetchResult.message}</ResultBanner>}
          <div className="flex justify-end gap-3">
            <Button onClick={() => setModalOpen(false)}>Cancel</Button>
            <Button type="submit" variant="primary" disabled={fetching}>{fetching ? 'Fetching...' : 'Fetch'}</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
