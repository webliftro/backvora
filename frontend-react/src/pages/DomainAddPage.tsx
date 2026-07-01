import { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { api } from '../api';
import { useToast } from '../components/Toast';
import { DOMAIN_STATUSES } from '../types';

export default function DomainAddPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { toast } = useToast();
  const [categories, setCategories] = useState<string[]>([]);
  const [allDomainNames, setAllDomainNames] = useState<{ id: string; domain: string }[]>([]);
  const [dupeMatch, setDupeMatch] = useState<{ id: string; domain: string } | null>(null);
  const passedState = location.state as { domain?: string; metrics?: Record<string, unknown> } | null;
  const [form, setForm] = useState({
    domain: passedState?.domain || '', owner: '', email: '', telegram: '', status: 'new',
    category: '', tags: '', is_competitor: false, is_adult: true, notes: '',
  });

  // Owner autocomplete
  const [ownerSuggestions, setOwnerSuggestions] = useState<{ owner: string; email: string | null; telegram: string | null; payment_methods?: any[] }[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [pendingPayments, setPendingPayments] = useState<{ method: string; details: Record<string, string>; is_preferred: boolean }[]>([]);

  useEffect(() => {
    api.getCategories().then(d => setCategories(d.categories || [])).catch(() => {});
    api.getDomains(1, 10000).then(d => {
      const names = d.items.map(i => ({ id: i.id, domain: i.domain }));
      setAllDomainNames(names);
      // Check for duplicate if domain was pre-filled from Check Metrics
      if (passedState?.domain) {
        const clean = passedState.domain.trim().toLowerCase().replace(/^https?:\/\//, '').replace(/\/.*$/, '');
        setDupeMatch(clean ? names.find(n => n.domain === clean) || null : null);
      }
    }).catch(() => {});
  }, []);

  function checkDupe(value: string) {
    const clean = value.trim().toLowerCase().replace(/^https?:\/\//, '').replace(/\/.*$/, '');
    setDupeMatch(clean ? allDomainNames.find(d => d.domain === clean) || null : null);
  }

  let ownerTimer: ReturnType<typeof setTimeout>;
  function onOwnerSearch(field: 'owner' | 'email', val: string) {
    setForm(prev => ({ ...prev, [field]: val }));
    clearTimeout(ownerTimer);
    if (val.length >= 2) {
      ownerTimer = setTimeout(async () => {
        try { const r = await api.searchOwners(val); setOwnerSuggestions(r.items); setShowSuggestions(r.items.length > 0); } catch { setShowSuggestions(false); }
      }, 200);
    } else { setShowSuggestions(false); }
  }

  function pickOwner(s: { owner: string; email: string | null; telegram: string | null; payment_methods?: any[] }) {
    setForm(prev => ({ ...prev, owner: s.owner || '', email: s.email || '', telegram: s.telegram || '' }));
    setShowSuggestions(false);
    if (s.payment_methods?.length) {
      setPendingPayments(s.payment_methods);
      toast(`${s.payment_methods.length} payment method(s) will be added on save`);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const domain = form.domain.trim().toLowerCase().replace(/^https?:\/\//, '').replace(/\/.*$/, '');
    if (!domain) { toast('Enter a domain', 'error'); return; }
    let category: string | null = form.category;
    if (category === '__new__') { category = prompt('Enter new category:'); if (!category) return; }
    try {
      const nd = await api.createDomain({ domain, is_competitor: form.is_competitor, is_adult: form.is_adult, category: category || null, tags: form.tags || null, notes: form.notes || null });
      if (form.owner || form.email || form.telegram || form.status !== 'new')
        await api.updateDomain(nd.id, { owner: form.owner || null, email: form.email || null, telegram: form.telegram || null, status: form.status });
      // Copy pending payment methods
      for (const pm of pendingPayments) {
        try { await api.addPaymentMethod(nd.id, { method: pm.method, details: pm.details }); } catch {}
      }
      if (pendingPayments.length) {
        // Set preferred
        const preferred = pendingPayments.find(p => p.is_preferred);
        if (preferred) {
          const methods = await api.getPaymentMethods(nd.id);
          const match = methods.items.find(m => m.method === preferred.method);
          if (match) { try { await api.setPreferredPayment(nd.id, match.id); } catch {} }
        }
      }
      // Save pre-fetched metrics if coming from Check Metrics
      if (passedState?.metrics) {
        try { await api.saveMetrics(nd.id, passedState.metrics); } catch {}
      }
      toast(`Added ${domain}`);
      navigate(`/domains/${nd.id}`);
    } catch (e: any) { toast(e.message, 'error'); }
  }

  const ic = "w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-pink-500 text-sm";

  const suggestionDropdown = (
    showSuggestions ? (
      <div className="absolute z-50 left-0 right-0 mt-1 bg-gray-800 border border-gray-600 rounded-lg shadow-lg max-h-64 overflow-y-auto">
        {ownerSuggestions.map((s, i) => (
          <button key={i} type="button" onMouseDown={() => pickOwner(s)} className="w-full text-left px-3 py-2 hover:bg-gray-700 text-sm">
            <div className="font-medium">{s.owner}</div>
            {s.email && <div className="text-xs text-gray-400">{s.email}</div>}
            {s.payment_methods?.length ? <div className="text-xs text-pink-400">{s.payment_methods.length} payment method(s)</div> : null}
          </button>
        ))}
      </div>
    ) : null
  );

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="flex items-center gap-4">
        <Link to="/domains" className="text-gray-400 hover:text-white flex items-center gap-1"><ArrowLeft className="w-4 h-4" /> Domains</Link>
        <h1 className="text-2xl font-bold">Add Domain</h1>
      </div>
      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <label className="block text-sm text-gray-400 mb-1">Domain *</label>
          <input type="text" value={form.domain} onChange={e => { setForm({ ...form, domain: e.target.value }); checkDupe(e.target.value); }}
            placeholder="example.com" required autoFocus className={`${ic} !text-lg`} />
          {dupeMatch && (
            <div className="mt-2 p-3 bg-yellow-900/30 border border-yellow-700 rounded-lg text-sm text-yellow-400">
              ⚠️ Already exists! <Link to={`/domains/${dupeMatch.id}`} className="underline text-pink-400">View →</Link>
            </div>
          )}
        </div>
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h2 className="text-lg font-semibold mb-4">Contact Info</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="relative"><label className="block text-xs text-gray-400 mb-1">Owner</label>
              <input type="text" value={form.owner} onChange={e => onOwnerSearch('owner', e.target.value)}
                onFocus={() => { if (ownerSuggestions.length) setShowSuggestions(true); }}
                onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
                autoComplete="off" className={ic} />
              {suggestionDropdown}
            </div>
            <div className="relative"><label className="block text-xs text-gray-400 mb-1">Email</label>
              <input type="text" value={form.email} onChange={e => onOwnerSearch('email', e.target.value)}
                onFocus={() => { if (ownerSuggestions.length) setShowSuggestions(true); }}
                onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
                autoComplete="off" className={ic} />
              {suggestionDropdown}
            </div>
            <div><label className="block text-xs text-gray-400 mb-1">Telegram</label>
              <input type="text" value={form.telegram} onChange={e => setForm({ ...form, telegram: e.target.value })} className={ic} /></div>
          </div>
          {pendingPayments.length > 0 && (
            <div className="mt-3 p-3 bg-pink-900/20 border border-pink-700 rounded-lg text-sm">
              <span className="text-pink-400">💳 {pendingPayments.length} payment method(s)</span> will be copied: {pendingPayments.map(p => p.method).join(', ')}
              <button type="button" onClick={() => setPendingPayments([])} className="ml-2 text-gray-400 hover:text-white text-xs">(clear)</button>
            </div>
          )}
        </div>
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h2 className="text-lg font-semibold mb-4">Classification</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div><label className="block text-xs text-gray-400 mb-1">Status</label>
              <select value={form.status} onChange={e => setForm({ ...form, status: e.target.value })} className={ic}>
                {DOMAIN_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
              </select></div>
            <div><label className="block text-xs text-gray-400 mb-1">Category</label>
              <select value={form.category} onChange={e => setForm({ ...form, category: e.target.value })} className={ic}>
                <option value="">None</option>{categories.map(c => <option key={c} value={c}>{c}</option>)}<option value="__new__">+ New Category</option>
              </select></div>
          </div>
          <div className="mb-4"><label className="block text-xs text-gray-400 mb-1">Tags</label>
            <input type="text" value={form.tags} onChange={e => setForm({ ...form, tags: e.target.value })} placeholder="tag1, tag2, ..." className={ic} /></div>
          <div className="flex gap-6">
            <label className="flex items-center gap-2"><input type="checkbox" checked={form.is_competitor} onChange={e => setForm({ ...form, is_competitor: e.target.checked })} /><span className="text-sm">Is Competitor</span></label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={form.is_adult} onChange={e => setForm({ ...form, is_adult: e.target.checked })} /><span className="text-sm">Adult</span></label>
          </div>
        </div>
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h2 className="text-lg font-semibold mb-4">Notes</h2>
          <textarea value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} rows={4} className={ic} placeholder="Any notes..." />
        </div>
        <div className="flex justify-between items-center">
          <Link to="/domains" className="px-4 py-2 text-gray-400 hover:text-white text-sm">Cancel</Link>
          <button type="submit" disabled={!!dupeMatch} className="px-6 py-3 bg-pink-600 hover:bg-pink-700 rounded-lg font-medium disabled:opacity-50">Add Domain</button>
        </div>
      </form>
    </div>
  );
}
