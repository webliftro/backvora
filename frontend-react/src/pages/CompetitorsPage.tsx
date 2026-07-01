import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Plus, ExternalLink, Trash2 } from 'lucide-react';
import { api } from '../api';
import { useToast } from '../components/Toast';
import Modal from '../components/Modal';
import type { Competitor } from '../types';

export default function CompetitorsPage() {
  const { toast } = useToast();
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [domain, setDomain] = useState('');
  const [limit, setLimit] = useState(100);
  const [fetching, setFetching] = useState(false);
  const [fetchResult, setFetchResult] = useState('');
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
    setFetchResult('⏳ Fetching backlinks from Ahrefs...');
    try {
      const data = await api.fetchBacklinks(domain.trim(), limit);
      if (data.success) {
        setFetchResult(`✅ Fetched ${data.total_fetched} backlinks → ${data.domains_added} new domains, ${data.backlinks_added} backlinks recorded.`);
        loadCompetitors();
      } else setFetchResult('Error fetching backlinks');
    } catch (e: any) { setFetchResult(`Error: ${e.message}`); }
    finally { setFetching(false); }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-3">
        <h1 className="text-2xl font-bold">Competitors</h1>
        <button onClick={() => { setModalOpen(true); setFetchResult(''); }} className="px-4 py-2 bg-pink-600 hover:bg-pink-700 rounded-lg text-sm font-medium flex items-center gap-1 self-start sm:self-auto">
          <Plus className="w-4 h-4" /> <span className="hidden sm:inline">Fetch Competitor Backlinks</span><span className="sm:hidden">Fetch</span>
        </button>
      </div>
      {loading ? <div className="text-gray-500">Loading...</div> : competitors.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-gray-400 text-lg mb-2">No competitors yet</p>
          <p className="text-gray-500 text-sm mb-4">Fetch competitor backlinks to get started</p>
        </div>
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
                  <h3 className="text-lg font-semibold">{c.domain}</h3>
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
          {fetchResult && <div className={`mb-4 text-sm ${fetchResult.startsWith('✅') ? 'text-green-400' : fetchResult.startsWith('⏳') ? 'text-pink-400' : 'text-red-400'}`}>{fetchResult}</div>}
          <div className="flex justify-end gap-3">
            <button type="button" onClick={() => setModalOpen(false)} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm">Cancel</button>
            <button type="submit" disabled={fetching} className="px-4 py-2 bg-pink-600 hover:bg-pink-700 rounded-lg text-sm font-medium disabled:opacity-50">{fetching ? 'Fetching...' : 'Fetch'}</button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
