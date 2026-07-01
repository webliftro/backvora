import { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { Globe, Plus, Trash2, Upload, ArrowLeft, Sparkles, Edit2, X } from 'lucide-react';
import { api } from '../api';
import { useToast } from '../components/Toast';
import Modal from '../components/Modal';

const ANCHOR_COLORS: Record<string, string> = {
  brand: 'bg-blue-600',
  topical: 'bg-purple-600',
  generic: 'bg-gray-600',
  exact: 'bg-green-600',
  url: 'bg-yellow-600',
};

// --- List Page ---
export function TargetSitesListPage() {
  const { toast } = useToast();
  const [sites, setSites] = useState<any[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ domain: '', name: '', brand_variations: '' });

  useEffect(() => { load(); }, []);
  async function load() {
    try { const d = await api.getTargetSites(); setSites(d.items); } catch (e: any) { toast(e.message, 'error'); }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api.createTargetSite(form);
      toast('Site created!');
      setShowCreate(false);
      setForm({ domain: '', name: '', brand_variations: '' });
      load();
    } catch (e: any) { toast(e.message, 'error'); }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Globe className="w-6 h-6 text-pink-500" /> Target Sites</h1>
        <button onClick={() => setShowCreate(true)} className="flex items-center gap-2 px-4 py-2 bg-pink-600 hover:bg-pink-700 rounded-lg text-sm font-medium self-start sm:self-auto">
          <Plus className="w-4 h-4" /> <span className="hidden sm:inline">Add Site</span><span className="sm:hidden">Add</span>
        </button>
      </div>

      <p className="text-gray-400 text-sm">Sites you're building links to. Define target URLs, anchor texts, and distribution strategy here.</p>

      {sites.length === 0 ? (
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-12 text-center">
          <Globe className="w-12 h-12 text-gray-600 mx-auto mb-4" />
          <p className="text-gray-400 mb-4">No target sites yet. Add your first site to start managing anchor text strategy.</p>
          <button onClick={() => setShowCreate(true)} className="px-4 py-2 bg-pink-600 rounded-lg text-sm">Add Your First Site</button>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {sites.map(s => (
            <Link key={s.id} to={`/target-sites/${s.id}`} className="bg-gray-800 rounded-lg border border-gray-700 p-4 sm:p-5 hover:border-pink-500 transition-colors block">
              <h3 className="text-lg font-semibold text-pink-400">{s.name}</h3>
              <p className="text-gray-400 text-sm">{s.domain}</p>
              <div className="flex gap-4 mt-3 text-sm text-gray-400">
                <span>{s.url_count} URLs</span>
                <span>{s.anchor_count} anchors</span>
                <span>{s.total_used} used</span>
              </div>
              <div className="flex gap-1 mt-3">
                {[
                  { label: 'B', pct: s.anchor_brand_pct, color: 'bg-blue-600' },
                  { label: 'T', pct: s.anchor_topical_pct, color: 'bg-purple-600' },
                  { label: 'G', pct: s.anchor_generic_pct, color: 'bg-gray-600' },
                  { label: 'E', pct: s.anchor_exact_pct, color: 'bg-green-600' },
                  { label: 'U', pct: s.anchor_url_pct, color: 'bg-yellow-600' },
                ].map(d => d.pct > 0 && (
                  <div key={d.label} className={`${d.color} rounded px-1.5 py-0.5 text-xs`} title={`${d.label}: ${d.pct}%`}>
                    {d.label} {d.pct}%
                  </div>
                ))}
              </div>
            </Link>
          ))}
        </div>
      )}

      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="Add Target Site">
        <form onSubmit={handleCreate} className="space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Domain</label>
            <input value={form.domain} onChange={e => setForm(f => ({ ...f, domain: e.target.value }))} placeholder="camhours.com" className="w-full px-3 py-2 bg-gray-900 border border-gray-600 rounded" required />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Brand Name</label>
            <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="CamHours" className="w-full px-3 py-2 bg-gray-900 border border-gray-600 rounded" required />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Brand Variations <span className="text-gray-600">(comma-separated)</span></label>
            <input value={form.brand_variations} onChange={e => setForm(f => ({ ...f, brand_variations: e.target.value }))} placeholder="Cam Hours, cam hours, CAMHOURS, CH" className="w-full px-3 py-2 bg-gray-900 border border-gray-600 rounded" />
          </div>
          <button type="submit" className="w-full px-4 py-2 bg-pink-600 hover:bg-pink-700 rounded font-medium">Create</button>
        </form>
      </Modal>
    </div>
  );
}

// --- Detail Page ---
export function TargetSiteDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [site, setSite] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [bulkModal, setBulkModal] = useState(false);
  const [bulkText, setBulkText] = useState('');
  const [editDist, setEditDist] = useState(false);
  const [distForm, setDistForm] = useState({ brand: 60, topical: 20, generic: 10, exact: 5, url: 5 });
  const [addAnchorModal, setAddAnchorModal] = useState<string | null>(null); // url_id
  const [anchorForm, setAnchorForm] = useState({ text: '', anchor_type: 'topical' });
  const [editAnchor, setEditAnchor] = useState<any>(null);
  const [suggestion, setSuggestion] = useState<any>(null);
  const [editingVariations, setEditingVariations] = useState(false);
  const [variationsText, setVariationsText] = useState('');

  useEffect(() => { if (id) load(); }, [id]);

  async function load() {
    try {
      setLoading(true);
      const d = await api.getTargetSite(id!);
      setSite(d);
      setVariationsText(d.brand_variations || '');
      setDistForm({
        brand: d.anchor_brand_pct,
        topical: d.anchor_topical_pct,
        generic: d.anchor_generic_pct,
        exact: d.anchor_exact_pct,
        url: d.anchor_url_pct,
      });
    } catch (e: any) { toast(e.message, 'error'); }
    setLoading(false);
  }

  async function handleBulkImport() {
    const autoBrand = (document.getElementById('bulk-auto-brand') as HTMLInputElement)?.checked ?? true;
    const variations = (site?.brand_variations || '').split(',').map((v: string) => v.trim()).filter(Boolean);
    const brandKeywords = [site?.name, ...variations].filter(Boolean);
    
    let entries = bulkText.split('\n').filter(l => l.trim()).map(line =>
      line.replace(/\{brand\}/gi, site?.name || '').replace(/\{domain\}/gi, site?.domain || '')
    );
    
    // Auto-add brand keywords to each entry
    if (autoBrand && brandKeywords.length > 0) {
      entries = entries.map(line => {
        const parts = line.split('|', 2);
        const url = parts[0].trim();
        const existingKws = parts.length > 1 ? parts[1].split(',').map(k => k.trim()).filter(Boolean) : [];
        const existingLower = new Set(existingKws.map(k => k.toLowerCase()));
        const newKws = brandKeywords.filter(k => !existingLower.has(k.toLowerCase()));
        const allKws = [...existingKws, ...newKws];
        return allKws.length > 0 ? `${url} | ${allKws.join(', ')}` : url;
      });
    }
    
    if (!entries.length) return;
    try {
      const res = await api.bulkImportURLs(id!, entries, site?.name);
      toast(`Added ${res.urls_created} URLs, ${res.anchors_created} anchors`);
      setBulkModal(false);
      setBulkText('');
      load();
    } catch (e: any) { toast(e.message, 'error'); }
  }

  async function handleSaveDist() {
    try {
      await api.updateTargetSite(id!, {
        anchor_brand_pct: distForm.brand,
        anchor_topical_pct: distForm.topical,
        anchor_generic_pct: distForm.generic,
        anchor_exact_pct: distForm.exact,
        anchor_url_pct: distForm.url,
      });
      toast('Distribution updated');
      setEditDist(false);
      load();
    } catch (e: any) { toast(e.message, 'error'); }
  }

  async function handleAddAnchor(e: React.FormEvent) {
    e.preventDefault();
    if (!addAnchorModal) return;
    try {
      await api.addAnchor(addAnchorModal, anchorForm);
      toast('Anchor added');
      setAddAnchorModal(null);
      setAnchorForm({ text: '', anchor_type: 'topical' });
      load();
    } catch (e: any) { toast(e.message, 'error'); }
  }

  async function handleUpdateAnchor() {
    if (!editAnchor) return;
    try {
      await api.updateAnchor(editAnchor.id, { text: editAnchor.text, anchor_type: editAnchor.anchor_type });
      toast('Anchor updated');
      setEditAnchor(null);
      load();
    } catch (e: any) { toast(e.message, 'error'); }
  }

  async function handleSuggest() {
    try {
      const res = await api.suggestAnchor(id!);
      setSuggestion(res);
    } catch (e: any) { toast(e.message, 'error'); }
  }

  if (loading) return <div className="text-center py-12 text-gray-400">Loading...</div>;
  if (!site) return <div className="text-center py-12 text-gray-400">Site not found</div>;

  const distTotal = distForm.brand + distForm.topical + distForm.generic + distForm.exact + distForm.url;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3">
        <div className="flex items-start gap-3">
          <button onClick={() => navigate('/target-sites')} className="p-2 hover:bg-gray-700 rounded shrink-0"><ArrowLeft className="w-5 h-5" /></button>
          <div className="flex-1 min-w-0">
            <h1 className="text-2xl font-bold truncate">{site.name}</h1>
            <p className="text-gray-400 text-sm truncate">{site.domain}</p>
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              {editingVariations ? (
                <>
                  <input value={variationsText} onChange={e => setVariationsText(e.target.value)} placeholder="Cam Hours, cam hours, CH" className="px-2 py-0.5 bg-gray-900 border border-gray-600 rounded text-xs w-full sm:w-64" />
                  <button onClick={async () => {
                    await api.updateTargetSite(id!, { brand_variations: variationsText });
                    toast('Variations saved');
                    setEditingVariations(false);
                    load();
                  }} className="text-xs text-green-400 hover:text-green-300">Save</button>
                  <button onClick={() => setEditingVariations(false)} className="text-xs text-gray-500 hover:text-white">Cancel</button>
                </>
              ) : (
                <>
                  <span className="text-xs text-gray-500 truncate">Variations: {site.brand_variations || 'none'}</span>
                  <button onClick={() => setEditingVariations(true)} className="text-gray-500 hover:text-pink-400 shrink-0"><Edit2 className="w-3 h-3" /></button>
                </>
              )}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={handleSuggest} className="flex items-center gap-2 px-3 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg text-sm">
            <Sparkles className="w-4 h-4" /> <span className="hidden sm:inline">Suggest Next Anchor</span><span className="sm:hidden">Suggest</span>
          </button>
          <button onClick={() => setBulkModal(true)} className="flex items-center gap-2 px-3 py-2 bg-pink-600 hover:bg-pink-700 rounded-lg text-sm">
            <Upload className="w-4 h-4" /> <span className="hidden sm:inline">Bulk Import</span><span className="sm:hidden">Import</span>
          </button>
        </div>
      </div>

      {/* Suggestion */}
      {suggestion?.suggestion && (
        <div className="bg-purple-900/30 border border-purple-700 rounded-lg p-4">
          <div className="flex items-center justify-between">
            <div>
              <span className="text-sm text-gray-400">Suggested next anchor:</span>
              <div className="flex items-center gap-2 mt-1">
                <span className="font-medium text-lg">"{suggestion.suggestion.text}"</span>
                <span className={`px-2 py-0.5 rounded text-xs ${ANCHOR_COLORS[suggestion.suggestion.anchor_type] || 'bg-gray-600'}`}>
                  {suggestion.suggestion.anchor_type}
                </span>
                <span className="text-gray-400 text-sm">→ {suggestion.suggestion.target_url}</span>
                <span className="text-gray-500 text-xs">(used {suggestion.suggestion.times_used}x)</span>
              </div>
            </div>
            <button onClick={() => setSuggestion(null)} className="text-gray-500 hover:text-white"><X className="w-4 h-4" /></button>
          </div>
          {suggestion.distribution && (
            <div className="flex gap-4 mt-2 text-xs text-gray-400">
              {Object.entries(suggestion.distribution.gaps as Record<string, number>).map(([k, v]) => (
                <span key={k} className={v > 0 ? 'text-green-400' : v < 0 ? 'text-red-400' : ''}>
                  {k}: {v > 0 ? '+' : ''}{v}%
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Distribution */}
      <div className="bg-gray-800 rounded-lg border border-gray-700 p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold">Anchor Text Distribution</h2>
          <button onClick={() => setEditDist(!editDist)} className="text-sm text-pink-400 hover:text-pink-300 flex items-center gap-1">
            <Edit2 className="w-3 h-3" /> {editDist ? 'Cancel' : 'Edit'}
          </button>
        </div>

        {/* Bar visualization */}
        <div className="flex h-6 rounded overflow-hidden mb-3">
          {[
            { key: 'brand', label: 'Brand', color: 'bg-blue-600' },
            { key: 'topical', label: 'Topical', color: 'bg-purple-600' },
            { key: 'generic', label: 'Generic', color: 'bg-gray-600' },
            { key: 'exact', label: 'Exact', color: 'bg-green-600' },
            { key: 'url', label: 'URL', color: 'bg-yellow-600' },
          ].map(d => {
            const pct = (distForm as any)[d.key];
            return pct > 0 ? (
              <div key={d.key} className={`${d.color} flex items-center justify-center text-xs font-medium`} style={{ width: `${pct}%` }} title={`${d.label}: ${pct}%`}>
                {pct >= 10 && `${d.label} ${pct}%`}
              </div>
            ) : null;
          })}
        </div>

        {/* Actual vs Target */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 sm:gap-3 text-sm">
          {[
            { key: 'brand', label: 'Brand' },
            { key: 'topical', label: 'Topical' },
            { key: 'generic', label: 'Generic' },
            { key: 'exact', label: 'Exact' },
            { key: 'url', label: 'URL' },
          ].map(d => (
            <div key={d.key} className="text-center">
              <div className="text-gray-400 text-xs mb-1">{d.label}</div>
              {editDist ? (
                <input
                  type="number"
                  value={(distForm as any)[d.key]}
                  onChange={e => setDistForm(f => ({ ...f, [d.key]: +e.target.value }))}
                  className="w-full px-2 py-1 bg-gray-900 border border-gray-600 rounded text-center text-sm"
                  min={0} max={100}
                />
              ) : (
                <div>
                  <span className="font-medium">{(distForm as any)[d.key]}%</span>
                  <div className="text-xs text-gray-500">actual: {site.actual_distribution?.[d.key] || 0}%</div>
                </div>
              )}
            </div>
          ))}
        </div>

        {editDist && (
          <div className="flex items-center justify-between mt-3">
            <span className={`text-sm ${distTotal === 100 ? 'text-green-400' : 'text-red-400'}`}>
              Total: {distTotal}% {distTotal !== 100 && '(should be 100%)'}
            </span>
            <button onClick={handleSaveDist} disabled={distTotal !== 100} className="px-4 py-1.5 bg-pink-600 hover:bg-pink-700 rounded text-sm disabled:opacity-50">Save</button>
          </div>
        )}
      </div>

      {/* URLs & Anchors */}
      <div className="space-y-4">
        <h2 className="font-semibold text-lg">Target URLs ({site.urls?.length || 0})</h2>

        {site.urls?.length === 0 ? (
          <div className="bg-gray-800 rounded-lg border border-gray-700 p-8 text-center">
            <p className="text-gray-500 mb-3">No target URLs yet. Use bulk import to add URLs and keywords.</p>
            <button onClick={() => setBulkModal(true)} className="px-4 py-2 bg-pink-600 rounded text-sm">Bulk Import</button>
          </div>
        ) : (
          site.urls?.map((u: any) => (
            <div key={u.id} className="bg-gray-800 rounded-lg border border-gray-700 p-4">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <a href={u.url} target="_blank" rel="noopener" className="text-pink-400 hover:underline text-sm font-medium">{u.url}</a>
                  {u.description && <span className="text-gray-500 text-xs">({u.description})</span>}
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={() => { setAddAnchorModal(u.id); setAnchorForm({ text: '', anchor_type: 'topical' }); }} className="text-gray-400 hover:text-pink-400" title="Add anchor">
                    <Plus className="w-4 h-4" />
                  </button>
                  <button onClick={async () => {
                    if (!confirm('Remove this URL and its anchors?')) return;
                    await api.deleteTargetURL(u.id);
                    toast('URL removed');
                    load();
                  }} className="text-gray-500 hover:text-red-400" title="Remove URL">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {/* Anchors */}
              <div className="flex flex-wrap gap-1.5 sm:gap-2">
                {u.anchors?.map((a: any) => (
                  <button
                    key={a.id}
                    onClick={() => setEditAnchor({ ...a })}
                    className={`px-2 py-1 rounded text-xs flex items-center gap-1 hover:ring-1 ring-white/30 transition-all ${ANCHOR_COLORS[a.anchor_type] || 'bg-gray-600'}`}
                    title={`${a.anchor_type} · used ${a.times_used}x · click to edit`}
                  >
                    <span className="truncate max-w-[150px] sm:max-w-none">{a.text}</span>
                    {a.times_used > 0 && <span className="opacity-60 shrink-0">({a.times_used})</span>}
                  </button>
                ))}
                {(!u.anchors || u.anchors.length === 0) && (
                  <span className="text-gray-500 text-xs">No anchors yet</span>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Bulk Import Modal */}
      <Modal open={bulkModal} onClose={() => setBulkModal(false)} title="Bulk Import URLs & Keywords">
        <div className="space-y-4">
          <p className="text-sm text-gray-400">
            One entry per line. Format: <code className="text-pink-400">url | keyword1, keyword2</code><br />
            Use variables: <code className="text-pink-400">{'{brand}'}</code>, <code className="text-pink-400">{'{domain}'}</code>. Click buttons below to insert.
          </p>

          {/* Quick insert buttons */}
          <div className="flex flex-wrap gap-2">
            <span className="text-xs text-gray-500 py-1">Insert:</span>
            {[
              { label: `{brand}`, value: '{brand}', title: `→ ${site.name}` },
              { label: `{domain}`, value: '{domain}', title: `→ ${site.domain}` },
              ...(site.brand_variations ? site.brand_variations.split(',').map((v: string) => v.trim()).filter(Boolean).map((v: string) => ({ label: v, value: v, title: 'Brand variation' })) : []),
            ].map((btn, i) => (
              <button
                key={i}
                type="button"
                onClick={() => {
                  const ta = document.getElementById('bulk-import-ta') as HTMLTextAreaElement;
                  if (ta) {
                    const start = ta.selectionStart;
                    const end = ta.selectionEnd;
                    const before = bulkText.substring(0, start);
                    const after = bulkText.substring(end);
                    const insert = (before.length > 0 && !before.endsWith(',') && !before.endsWith('|') && !before.endsWith(' ') && !before.endsWith('\n')) ? ', ' + btn.value : btn.value;
                    setBulkText(before + insert + after);
                    setTimeout(() => { ta.focus(); ta.selectionStart = ta.selectionEnd = start + insert.length; }, 0);
                  } else {
                    setBulkText(t => t + (t && !t.endsWith('\n') && !t.endsWith(', ') ? ', ' : '') + btn.value);
                  }
                }}
                className="px-2 py-1 bg-gray-700 hover:bg-pink-600 rounded text-xs transition-colors"
                title={btn.title}
              >
                {btn.label}
              </button>
            ))}
          </div>

          {/* Auto-add brand option */}
          <label className="flex items-center gap-2 text-sm text-gray-400">
            <input
              type="checkbox"
              id="bulk-auto-brand"
              defaultChecked={true}
              className="rounded bg-gray-700 border-gray-600"
            />
            Auto-add <span className="text-pink-400">{site.name}</span> + variations as brand keywords to every URL
          </label>

          <textarea
            id="bulk-import-ta"
            value={bulkText}
            onChange={e => setBulkText(e.target.value)}
            rows={10}
            placeholder={`https://${site.domain} | Best {brand}, {domain}\nhttps://${site.domain}/girls | cam girls, live {brand} girls\nhttps://${site.domain}/couples`}
            className="w-full px-3 py-2 bg-gray-900 border border-gray-600 rounded text-sm font-mono"
          />

          {/* Preview */}
          {bulkText.trim() && (
            <details className="text-xs">
              <summary className="text-gray-500 cursor-pointer hover:text-gray-300">Preview resolved keywords</summary>
              <div className="mt-2 bg-gray-900 rounded p-2 max-h-40 overflow-auto font-mono">
                {bulkText.split('\n').filter(l => l.trim()).map((line, i) => {
                  const resolved = line.replace(/\{brand\}/gi, site.name).replace(/\{domain\}/gi, site.domain);
                  return <div key={i} className="text-gray-400">{resolved}</div>;
                })}
              </div>
            </details>
          )}

          <div className="flex justify-between items-center">
            <span className="text-sm text-gray-500">{bulkText.split('\n').filter(l => l.trim()).length} entries</span>
            <button onClick={handleBulkImport} className="px-4 py-2 bg-pink-600 hover:bg-pink-700 rounded font-medium">Import</button>
          </div>
        </div>
      </Modal>

      {/* Add Anchor Modal */}
      <Modal open={!!addAnchorModal} onClose={() => setAddAnchorModal(null)} title="Add Anchor Text">
        <form onSubmit={handleAddAnchor} className="space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Anchor Text</label>
            <input value={anchorForm.text} onChange={e => setAnchorForm(f => ({ ...f, text: e.target.value }))} className="w-full px-3 py-2 bg-gray-900 border border-gray-600 rounded" required />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Type</label>
            <select value={anchorForm.anchor_type} onChange={e => setAnchorForm(f => ({ ...f, anchor_type: e.target.value }))} className="w-full px-3 py-2 bg-gray-900 border border-gray-600 rounded">
              <option value="brand">Brand</option>
              <option value="topical">Topical</option>
              <option value="generic">Generic</option>
              <option value="exact">Exact Match</option>
              <option value="url">URL</option>
            </select>
          </div>
          <button type="submit" className="w-full px-4 py-2 bg-pink-600 hover:bg-pink-700 rounded font-medium">Add</button>
        </form>
      </Modal>

      {/* Edit Anchor Modal */}
      <Modal open={!!editAnchor} onClose={() => setEditAnchor(null)} title="Edit Anchor">
        {editAnchor && (
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Anchor Text</label>
              <input value={editAnchor.text} onChange={e => setEditAnchor((a: any) => ({ ...a, text: e.target.value }))} className="w-full px-3 py-2 bg-gray-900 border border-gray-600 rounded" />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Type</label>
              <select value={editAnchor.anchor_type} onChange={e => setEditAnchor((a: any) => ({ ...a, anchor_type: e.target.value }))} className="w-full px-3 py-2 bg-gray-900 border border-gray-600 rounded">
                <option value="brand">Brand</option>
                <option value="topical">Topical</option>
                <option value="generic">Generic</option>
                <option value="exact">Exact Match</option>
                <option value="url">URL</option>
              </select>
            </div>
            <div className="flex gap-2">
              <button onClick={handleUpdateAnchor} className="flex-1 px-4 py-2 bg-pink-600 hover:bg-pink-700 rounded font-medium">Save</button>
              <button onClick={async () => {
                if (!confirm('Delete this anchor?')) return;
                await api.deleteAnchor(editAnchor.id);
                toast('Anchor deleted');
                setEditAnchor(null);
                load();
              }} className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded font-medium">Delete</button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
