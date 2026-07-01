import { useState, useEffect, useMemo } from 'react';
import {
  useReactTable, getCoreRowModel, getSortedRowModel, getPaginationRowModel,
  flexRender, createColumnHelper,
  type SortingState, type VisibilityState,
} from '@tanstack/react-table';
import { Link } from 'react-router-dom';
import {
  ExternalLink, Trash2, Plus, Upload, Settings, Columns3, RefreshCw, Search,
  ChevronUp, ChevronDown, ChevronsUpDown, ArrowLeft, ArrowRight, Check, X as XIcon,
} from 'lucide-react';
import { api } from '../api';
import { useToast } from '../components/Toast';
import Modal from '../components/Modal';
import type { Domain } from '../types';
import { DOMAIN_STATUSES } from '../types';

const col = createColumnHelper<Domain>();

const statusColors: Record<string, string> = {
  new: 'bg-gray-600', analyzing: 'bg-pink-600', analyzed: 'bg-pink-700',
  contacted: 'bg-yellow-600', replied: 'bg-green-600', negotiating: 'bg-orange-600',
  deal_closed: 'bg-green-700', rejected: 'bg-red-600', blacklisted: 'bg-red-900',
};

export default function DomainsPage() {
  const { toast } = useToast();
  const [domains, setDomains] = useState<Domain[]>([]);
  const [loading, setLoading] = useState(true);
  const defaultColVis: VisibilityState = { backlink_anchor: false, backlink_count: false, tags: false, is_competitor: false, is_adult: false, created_at: false };
  const [sorting, setSorting] = useState<SortingState>(() => {
    try { return JSON.parse(localStorage.getItem('backvora_domains_sorting') || 'null') || [{ id: 'organic_traffic', desc: true }]; } catch { return [{ id: 'organic_traffic', desc: true }]; }
  });
  const [rowSelection, setRowSelection] = useState({});
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>(() => {
    try { return JSON.parse(localStorage.getItem('backvora_domains_colvis') || 'null') || defaultColVis; } catch { return defaultColVis; }
  });
  const [colMenuOpen, setColMenuOpen] = useState(false);

  // Filters (persisted to localStorage)
  const FILTERS_KEY = 'backvora_domains_filters';
  function loadFilters() {
    try { return JSON.parse(localStorage.getItem(FILTERS_KEY) || '{}'); } catch { return {}; }
  }
  const [search, setSearch] = useState(() => loadFilters().search || '');
  const [statusFilter, setStatusFilter] = useState(() => loadFilters().statusFilter || '');
  const [categoryFilter, setCategoryFilter] = useState(() => loadFilters().categoryFilter || '');
  const [targetFilter, setTargetFilter] = useState(() => loadFilters().targetFilter || '');
  const [hasBacklink, setHasBacklink] = useState(() => loadFilters().hasBacklink || '');
  const [competitorOnly, setCompetitorOnly] = useState(() => loadFilters().competitorOnly || false);
  const [minTraffic, setMinTraffic] = useState(() => loadFilters().minTraffic || '');
  const [maxTraffic, setMaxTraffic] = useState(() => loadFilters().maxTraffic || '');
  const [minDR, setMinDR] = useState(() => loadFilters().minDR || '');
  const [maxDR, setMaxDR] = useState(() => loadFilters().maxDR || '');
  const [hasContacts, setHasContacts] = useState(() => loadFilters().hasContacts || '');
  const [linkTypeFilter, setLinkTypeFilter] = useState(() => loadFilters().linkTypeFilter || '');

  useEffect(() => { localStorage.setItem('backvora_domains_sorting', JSON.stringify(sorting)); }, [sorting]);
  useEffect(() => { localStorage.setItem('backvora_domains_colvis', JSON.stringify(columnVisibility)); }, [columnVisibility]);

  // Persist filters to localStorage
  useEffect(() => {
    localStorage.setItem(FILTERS_KEY, JSON.stringify({
      search, statusFilter, categoryFilter, targetFilter, hasBacklink,
      competitorOnly, minTraffic, maxTraffic, minDR, maxDR, hasContacts, linkTypeFilter,
    }));
  }, [search, statusFilter, categoryFilter, targetFilter, hasBacklink, competitorOnly, minTraffic, maxTraffic, minDR, maxDR, hasContacts, linkTypeFilter]);

  const [categories, setCategories] = useState<string[]>([]);
  const [targets, setTargets] = useState<string[]>([]);

  // Delete confirm
  const [deleteConfirm, setDeleteConfirm] = useState<{ ids: string[]; label: string } | null>(null);
  const [analyzingIds, setAnalyzingIds] = useState<Set<string>>(new Set());

  // Modals
  const [importOpen, setImportOpen] = useState(false);
  const [importTab, setImportTab] = useState<'text' | 'csv' | 'ahrefs'>('text');
  const [importText, setImportText] = useState('');
  const [importComp, setImportComp] = useState(false);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvComp, setCsvComp] = useState('');
  const [importing, setImporting] = useState(false);
  const [importProgress, setImportProgress] = useState('');
  const [importResult, setImportResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [csvMinTraffic, setCsvMinTraffic] = useState('');
  const [csvMaxTraffic, setCsvMaxTraffic] = useState('');
  const [csvMinDr, setCsvMinDr] = useState('');
  const [csvMaxDr, setCsvMaxDr] = useState('');
  const [csvAdultOnly, setCsvAdultOnly] = useState(false);
  const [presetsOpen, setPresetsOpen] = useState(false);
  const [presetCats, setPresetCats] = useState('');
  const [presetTags, setPresetTags] = useState('');
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkCat, setBulkCat] = useState('');
  const [bulkTags, setBulkTags] = useState('');
  const [bulkGrabbing, setBulkGrabbing] = useState(false);
  const [bulkGrabProgress, setBulkGrabProgress] = useState<{ processed: number; total: number; contacts: number } | null>(null);
  const [bulkActionResult, setBulkActionResult] = useState<{ ok: boolean; message: string } | null>(null);

  useEffect(() => {
    loadDomains(); loadCategories();
    const p = new URLSearchParams(window.location.search);
    if (p.get('target')) setTargetFilter(p.get('target')!);
  }, []);

  async function loadDomains() {
    try {
      setLoading(true);
      const d = await api.getDomains(1, 10000);
      setDomains(d.items);
      const t = new Set<string>();
      d.items.forEach(i => { if (i.backlink_target) t.add(i.backlink_target); });
      setTargets(Array.from(t).sort());
    } catch (e: any) { toast(e.message, 'error'); }
    finally { setLoading(false); }
  }

  async function loadCategories() {
    try { const d = await api.getCategories(); setCategories(d.categories || []); } catch {}
  }

  const filtered = useMemo(() => domains.filter(d => {
    if (search) {
      const s = search.toLowerCase();
      const haystack = [d.domain, d.category, d.tags, d.niche_tags, d.notes, d.email, d.owner].filter(Boolean).join(' ').toLowerCase();
      if (!haystack.includes(s)) return false;
    }
    if (statusFilter && d.status !== statusFilter) return false;
    if (categoryFilter && d.category !== categoryFilter) return false;
    if (targetFilter && d.backlink_target !== targetFilter) return false;
    if (hasBacklink === 'yes' && !d.backlink_url) return false;
    if (hasBacklink === 'no' && d.backlink_url) return false;
    if (competitorOnly && !d.is_competitor) return false;
    if (minTraffic && (d.organic_traffic || 0) < +minTraffic) return false;
    if (maxTraffic && (d.organic_traffic || 0) > +maxTraffic) return false;
    if (minDR && (d.domain_rating || 0) < +minDR) return false;
    if (maxDR && (d.domain_rating || 0) > +maxDR) return false;
    if (hasContacts === 'yes' && !d.has_contact_info) return false;
    if (hasContacts === 'no' && d.has_contact_info) return false;
    if (linkTypeFilter && !(Array.isArray(d.link_types) ? d.link_types : []).includes(linkTypeFilter)) return false;
    return true;
  }), [domains, search, statusFilter, categoryFilter, targetFilter, hasBacklink, hasContacts, competitorOnly, minTraffic, maxTraffic, minDR, maxDR, linkTypeFilter]);

  const availableLinkTypes = useMemo(() => {
    const types = new Set<string>();
    domains.forEach(d => { (Array.isArray(d.link_types) ? d.link_types : []).forEach((t: string) => types.add(t)); });
    return [...types].sort();
  }, [domains]);

  const columns = useMemo(() => [
    col.display({ id: 'select', size: 40, enableResizing: false,
      header: ({ table }) => <input type="checkbox" checked={table.getIsAllPageRowsSelected()} onChange={table.getToggleAllPageRowsSelectedHandler()} />,
      cell: ({ row }) => <input type="checkbox" checked={row.getIsSelected()} onChange={row.getToggleSelectedHandler()} />,
    }),
    col.accessor('domain', { header: 'Domain', size: 200,
      cell: i => <div className="flex items-center gap-1"><Link to={`/domains/${i.row.original.id}`} className="text-pink-400 hover:underline truncate">{i.getValue()}</Link><a href={`https://${i.getValue()}`} target="_blank" rel="noopener" className="text-gray-500 hover:text-gray-300 shrink-0"><ExternalLink className="w-3 h-3" /></a></div>,
    }),
    col.accessor('organic_traffic', { header: 'Traffic', size: 100, cell: i => i.getValue()?.toLocaleString() ?? '-' }),
    col.accessor('domain_rating', { header: 'DR', size: 60, cell: i => i.getValue() ?? '-' }),
    col.display({ id: 'contacts', header: 'Contacts', size: 100,
      cell: ({ row }) => {
        const d = row.original;
        const count = d.contacts_count || 0;
        const hasPrimary = d.has_primary_contact;
        const hasEmail = d.has_email;
        const hasForm = d.has_form;
        const hasCaptcha = d.has_captcha;
        const hasInfo = d.has_contact_info;
        if (!hasInfo && count === 0 && !hasForm) return <span className="text-gray-500">—</span>;
        return (
          <div className="flex items-center gap-1.5 text-xs">
            {count > 0 ? (
              <span className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded ${hasPrimary ? 'bg-green-900/50 text-green-400 font-medium' : 'bg-yellow-900/40 text-yellow-400'}`}>
                {hasPrimary ? <Check className="w-3 h-3" /> : null}
                {count}
              </span>
            ) : hasInfo ? (
              <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-blue-900/40 text-blue-400" title="Has owner/email/telegram info">
                <Check className="w-3 h-3" />
              </span>
            ) : null}
            {hasEmail && <span title="Has email">📧</span>}
            {hasForm && <span title="Has contact form">📝</span>}
            {hasCaptcha && <span title="Has CAPTCHA">⚠️</span>}
          </div>
        );
      },
    }),
    col.accessor('backlink_target', { header: 'Links To', size: 120, cell: i => i.getValue() || '-' }),
    col.accessor('backlink_url', { header: 'Backlink', size: 150, enableSorting: false,
      cell: i => { const u = i.getValue(); if (!u) return '-'; let d = u; try { const p = new URL(u); d = p.pathname.length > 30 ? p.pathname.slice(0,30)+'...' : p.pathname || '/'; } catch { d = u.length > 40 ? u.slice(0,40)+'...' : u; } return <a href={u} target="_blank" rel="noopener" className="text-pink-400 hover:underline" title={u}>{d}</a>; },
    }),
    col.accessor('backlink_anchor', { header: 'Anchor', size: 120 }),
    col.accessor('backlink_count', { header: '#Links', size: 70, cell: i => i.getValue() || '-' }),
    col.accessor('category', { header: 'Category', size: 120, cell: i => i.getValue() || '-' }),
    col.accessor('tags', { header: 'Tags', size: 150,
      cell: i => { const v = i.getValue(); if (!v) return '-'; return <div className="flex flex-wrap gap-1">{v.split(',').filter(Boolean).map((t,j) => <span key={j} className="px-1.5 py-0.5 bg-gray-700 rounded text-xs">{t.trim()}</span>)}</div>; },
    }),
    col.accessor('link_types', { header: 'Link Types', size: 150, enableSorting: false,
      cell: i => { const v = i.getValue(); if (!v?.length) return '-'; return <div className="flex flex-wrap gap-1">{v.map((t,j) => <span key={j} className="px-1.5 py-0.5 bg-gray-700 rounded text-xs">{t}</span>)}</div>; },
    }),
    col.accessor('status', { header: 'Status', size: 100,
      cell: i => <span className={`px-2 py-0.5 rounded text-xs font-medium ${statusColors[i.getValue()] || 'bg-gray-700'}`}>{i.getValue()}</span>,
    }),
    col.accessor('is_competitor', { header: 'Competitor', size: 90, cell: i => i.getValue() ? <Check className="w-4 h-4 text-green-400" /> : <XIcon className="w-4 h-4 text-gray-500" /> }),
    col.accessor('is_adult', { header: 'Adult', size: 60, cell: i => i.getValue() ? <Check className="w-4 h-4 text-green-400" /> : <XIcon className="w-4 h-4 text-gray-500" /> }),
    col.accessor('created_at', { header: 'Added', size: 100, cell: i => i.getValue() ? new Date(i.getValue()!).toLocaleDateString() : '-' }),
  ], []);

  const table = useReactTable({
    data: filtered, columns, state: { sorting, rowSelection, columnVisibility },
    onSortingChange: setSorting, onRowSelectionChange: setRowSelection, onColumnVisibilityChange: setColumnVisibility,
    getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel(), getPaginationRowModel: getPaginationRowModel(),
    enableRowSelection: true, enableColumnResizing: true, columnResizeMode: 'onChange',
    initialState: { pagination: { pageSize: 50 } },
  });

  const selIds = Object.keys(rowSelection).filter(k => (rowSelection as Record<string, boolean>)[k]).map(k => filtered[+k]?.id).filter(Boolean);

  function bulkDelete() {
    if (!selIds.length) return;
    setDeleteConfirm({ ids: selIds, label: `${selIds.length} domain${selIds.length > 1 ? 's' : ''}` });
  }

  async function confirmDelete() {
    if (!deleteConfirm) return;
    const ids = deleteConfirm.ids;
    try {
      if (ids.length === 1) { await api.deleteDomain(ids[0]); } else { await api.bulkDeleteDomains(ids); }
      toast(`Deleted ${ids.length} domain${ids.length > 1 ? 's' : ''}`);
      setDomains(prev => prev.filter(d => !ids.includes(d.id)));
      setRowSelection({});
    } catch (e: any) { toast(e.message, 'error'); }
    setDeleteConfirm(null);
  }

  async function analyzeDomain(domainId: string) {
    setAnalyzingIds(prev => new Set(prev).add(domainId));
    try {
      const r = await api.analyzeDomain(domainId);
      if (r.success) {
        const m = r.domain || r.metrics || {};
        setDomains(prev => prev.map(d => d.id === domainId ? {
          ...d,
          domain_rating: (m.domain_rating as number) ?? d.domain_rating,
          organic_traffic: (m.organic_traffic as number) ?? d.organic_traffic,
          referring_domains: (m.referring_domains as number) ?? d.referring_domains,
          backlinks_count: (m.backlinks_count as number) ?? d.backlinks_count,
          status: 'analyzed',
        } : d));
        toast(`Updated: DR ${m.domain_rating ?? '-'}, Traffic ${(m.organic_traffic as number)?.toLocaleString() ?? '-'}`);
      }
    } catch (e: any) { toast(e.message || 'Analysis failed', 'error'); }
    setAnalyzingIds(prev => { const s = new Set(prev); s.delete(domainId); return s; });
  }

  async function bulkEdit(e: React.FormEvent) {
    e.preventDefault();
    let c: string | null = bulkCat || null;
    if (c === '__new__') { c = prompt('New category:'); if (!c) return; }
    try { const r = await api.bulkUpdateDomains(selIds, c, bulkTags || null); toast(`Updated ${r.updated}`); setBulkOpen(false); setRowSelection({}); loadDomains(); loadCategories(); } catch (e: any) { toast(e.message, 'error'); }
  }

  async function importText2(e: React.FormEvent) {
    e.preventDefault();
    const lines = importText.split('\n').map(l => l.trim()).filter(Boolean);
    if (!lines.length) { toast('Enter domains', 'error'); return; }
    try { const r = await api.bulkImportDomains(lines, importComp); toast(`Added ${r.added}${r.skipped ? `, skipped ${r.skipped}` : ''}`); setImportOpen(false); setImportText(''); loadDomains(); } catch (e: any) { toast(e.message, 'error'); }
  }

  async function importCsv2(e: React.FormEvent) {
    e.preventDefault();
    if (!csvFile || !csvComp) { toast('Fill all fields', 'error'); return; }
    setImporting(true);
    try { const r = await api.importAhrefsCsv(csvFile, csvComp); toast(`Imported ${r.domains_added} domains, ${r.backlinks_added} backlinks (${r.skipped} skipped)`); setImportOpen(false); loadDomains(); } catch (e: any) { toast(e.message, 'error'); } finally { setImporting(false); }
  }

  async function importDomainsCsv(e: React.FormEvent) {
    e.preventDefault();
    if (!csvFile) { toast('Select a CSV file', 'error'); return; }
    setImporting(true);
    setImportProgress('Uploading CSV...');
    setImportResult(null);
    try {
      const r = await api.importDomainsCsv(csvFile, {
        min_traffic: csvMinTraffic ? parseInt(csvMinTraffic) : undefined,
        max_traffic: csvMaxTraffic ? parseInt(csvMaxTraffic) : undefined,
        min_dr: csvMinDr ? parseInt(csvMinDr) : undefined,
        max_dr: csvMaxDr ? parseInt(csvMaxDr) : undefined,
        skip_non_adult: csvAdultOnly || undefined,
      });
      setImportProgress('');
      const parts = [`✅ Added ${r.added} domains`];
      if (r.skipped) parts.push(`${r.skipped} duplicates`);
      if (r.filtered_out) parts.push(`${r.filtered_out} filtered out`);
      parts.push(`${r.total_rows} total rows`);
      setImportResult({ ok: true, message: parts.join(', ') });
      setCsvFile(null); setCsvMinTraffic(''); setCsvMaxTraffic(''); setCsvMinDr(''); setCsvMaxDr('');
      loadDomains();
    } catch (e: any) { setImportProgress(''); setImportResult({ ok: false, message: `❌ ${e.message}` }); } finally { setImporting(false); }
  }

  async function openPresets() {
    try { const [c, t] = await Promise.all([api.getCategories(), api.getTags()]); setPresetCats((c.predefined || []).join('\n')); setPresetTags((t.predefined || []).join('\n')); } catch {}
    setPresetsOpen(true);
  }

  async function savePresets() {
    try {
      await api.savePresetCategories(presetCats.split('\n').map(s => s.trim()).filter(Boolean));
      await api.savePresetTags(presetTags.split('\n').map(s => s.trim()).filter(Boolean));
      toast('Presets saved'); setPresetsOpen(false); loadCategories();
    } catch (e: any) { toast(e.message, 'error'); }
  }

  function clearFilters() { setSearch(''); setStatusFilter(''); setCategoryFilter(''); setTargetFilter(''); setHasBacklink(''); setHasContacts(''); setLinkTypeFilter(''); setCompetitorOnly(false); setMinTraffic(''); setMaxTraffic(''); setMinDR(''); setMaxDR(''); }

  async function bulkGrabAllMissing() {
    if (!confirm('Grab contacts for all domains without any saved contacts? This may take a while.')) return;
    setBulkGrabbing(true);
    setBulkGrabProgress({ processed: 0, total: 0, contacts: 0 });
    try {
      const result = await api.bulkGrabContacts();
      setBulkGrabProgress({ processed: result.scanned, total: result.scanned, contacts: result.found });
      toast(`✓ Found ${result.found} contacts from ${result.scanned} domains scanned`);
      await loadDomains();
    } catch (e: any) {
      toast(e.message || 'Bulk grab failed', 'error');
    }
    setBulkGrabbing(false);
    setTimeout(() => setBulkGrabProgress(null), 3000);
  }

  const ic = "px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm";

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-3">
        <h1 className="text-2xl font-bold">Domains</h1>
        <div className="flex flex-wrap gap-2">
          <button onClick={openPresets} className="px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm flex items-center gap-1">
            <Settings className="w-4 h-4" /> <span className="hidden sm:inline">Presets</span>
          </button>
          <button onClick={bulkGrabAllMissing} disabled={bulkGrabbing} className="px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm flex items-center gap-1 disabled:opacity-50">
            <Search className={`w-4 h-4 ${bulkGrabbing ? 'animate-spin' : ''}`} /> 
            <span className="hidden sm:inline">{bulkGrabbing ? 'Grabbing...' : 'Grab All Missing'}</span>
            <span className="sm:hidden">{bulkGrabbing ? 'Grab...' : 'Grab'}</span>
          </button>
          <button onClick={() => setImportOpen(true)} className="px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm flex items-center gap-1">
            <Upload className="w-4 h-4" /> <span className="hidden sm:inline">Import</span>
          </button>
          <Link to="/domains/new" className="px-3 py-2 bg-pink-600 hover:bg-pink-700 rounded-lg text-sm font-medium flex items-center gap-1">
            <Plus className="w-4 h-4" /> <span className="hidden sm:inline">Add Domain</span><span className="sm:hidden">Add</span>
          </Link>
        </div>
      </div>

      {bulkGrabProgress && (
        <div className="p-3 bg-green-900/30 border border-green-700 rounded-lg flex items-center gap-3 text-sm">
          <span>✓ Processed {bulkGrabProgress.processed} domains, found {bulkGrabProgress.contacts} contacts</span>
        </div>
      )}

      <div className="flex gap-2 sm:gap-3 items-center flex-wrap">
        <input type="text" placeholder="Search domain, tags, notes..." value={search} onChange={e => setSearch(e.target.value)} className={`${ic} w-full sm:w-48 focus:outline-none focus:border-pink-500`} />
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className={`${ic} flex-1 sm:flex-none min-w-0`}><option value="">All Status</option>{DOMAIN_STATUSES.map(s => <option key={s}>{s}</option>)}</select>
        <select value={categoryFilter} onChange={e => setCategoryFilter(e.target.value)} className={`${ic} flex-1 sm:flex-none min-w-0`}><option value="">All Categories</option>{categories.map(c => <option key={c}>{c}</option>)}</select>
        <select value={targetFilter} onChange={e => setTargetFilter(e.target.value)} className={`${ic} flex-1 sm:flex-none min-w-0`}><option value="">All Targets</option>{targets.map(t => <option key={t}>{t}</option>)}</select>
        <select value={hasBacklink} onChange={e => setHasBacklink(e.target.value)} className={`${ic} flex-1 sm:flex-none min-w-0`}><option value="">Has Backlink?</option><option value="yes">Yes</option><option value="no">No</option></select>
        <select value={hasContacts} onChange={e => setHasContacts(e.target.value)} className={`${ic} flex-1 sm:flex-none min-w-0`}><option value="">Has Contacts?</option><option value="yes">Yes</option><option value="no">No</option></select>
        <select value={linkTypeFilter} onChange={e => setLinkTypeFilter(e.target.value)} className={`${ic} flex-1 sm:flex-none min-w-0`}><option value="">All Link Types</option>{availableLinkTypes.map(t => <option key={t} value={t}>{t}</option>)}</select>
        <button onClick={clearFilters} className="px-3 py-2 text-gray-400 hover:text-white text-sm shrink-0">Clear</button>
      </div>

      <div className="flex gap-3 sm:gap-4 items-center flex-wrap text-sm">
        <div className="flex items-center gap-2 w-full sm:w-auto"><span className="text-gray-400 shrink-0">Traffic:</span>
          <input type="number" placeholder="Min" value={minTraffic} onChange={e => setMinTraffic(e.target.value)} className="w-20 sm:w-24 px-2 py-1 bg-gray-800 border border-gray-700 rounded text-sm" />
          <span className="text-gray-500">-</span>
          <input type="number" placeholder="Max" value={maxTraffic} onChange={e => setMaxTraffic(e.target.value)} className="w-20 sm:w-24 px-2 py-1 bg-gray-800 border border-gray-700 rounded text-sm" />
        </div>
        <div className="flex items-center gap-2 w-full sm:w-auto"><span className="text-gray-400 shrink-0">DR:</span>
          <input type="number" placeholder="Min" value={minDR} onChange={e => setMinDR(e.target.value)} className="w-16 px-2 py-1 bg-gray-800 border border-gray-700 rounded text-sm" />
          <span className="text-gray-500">-</span>
          <input type="number" placeholder="Max" value={maxDR} onChange={e => setMaxDR(e.target.value)} className="w-16 px-2 py-1 bg-gray-800 border border-gray-700 rounded text-sm" />
        </div>
        <label className="flex items-center gap-2"><input type="checkbox" checked={competitorOnly} onChange={e => setCompetitorOnly(e.target.checked)} /><span className="text-gray-400">Competitor</span></label>
      </div>

      {selIds.length > 0 && (
        <div className="p-3 bg-pink-900/30 border border-pink-700 rounded-lg flex flex-wrap items-center gap-2 sm:gap-4">
          <span className="text-sm">{selIds.length} selected</span>
          <button onClick={bulkDelete} className="px-3 py-1 bg-red-600 hover:bg-red-700 rounded text-sm flex items-center gap-1"><Trash2 className="w-3 h-3" /> <span className="hidden sm:inline">Delete</span></button>
          <button onClick={() => setBulkOpen(true)} className="px-3 py-1 bg-pink-600 hover:bg-pink-700 rounded text-sm"><span className="hidden sm:inline">Category/Tags</span><span className="sm:hidden">Edit</span></button>
          <button
            disabled={bulkGrabbing}
            onClick={async () => {
              setBulkGrabbing(true);
              setBulkActionResult(null);
              try {
                const resp = await fetch('/api/v1/domains/selected-grab-contacts', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json', ...(() => { const t = localStorage.getItem('token'); return t ? { Authorization: `Bearer ${t}` } : {}; })() },
                  body: JSON.stringify({ domain_ids: selIds }),
                });
                const reader = resp.body?.getReader();
                const decoder = new TextDecoder();
                let foundCount = 0;
                let totalCount = 0;
                let lastPhase = '';
                
                if (reader) {
                  let buffer = '';
                  while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || '';
                    
                    for (const line of lines) {
                      if (!line.startsWith('data: ')) continue;
                      try {
                        const ev = JSON.parse(line.slice(6));
                        if (ev.type === 'start') {
                          totalCount = ev.total;
                          setBulkActionResult({ ok: true, message: `⏳ Processing ${ev.total} domains...` });
                        } else if (ev.type === 'phase') {
                          lastPhase = ev.phase;
                          setBulkActionResult({ ok: true, message: `⏳ ${ev.message}` });
                        } else if (ev.type === 'found') {
                          foundCount++;
                          setBulkActionResult({ ok: true, message: `⏳ [${ev.progress}/${totalCount}] Found ${ev.email} for ${ev.domain} (${ev.method})` });
                        } else if (ev.type === 'miss') {
                          setBulkActionResult({ ok: true, message: `⏳ [${ev.progress}/${totalCount}] No contact for ${ev.domain} (${lastPhase})` });
                        } else if (ev.type === 'done') {
                          const msg = `✅ Done! Found ${ev.found} contacts out of ${ev.total} domains (${ev.missed} without contact)`;
                          setBulkActionResult({ ok: true, message: msg });
                          toast(msg);
                          loadDomains();
                        }
                      } catch {}
                    }
                  }
                }
              } catch (e: any) { toast(e.message, 'error'); setBulkActionResult({ ok: false, message: `❌ ${e.message}` }); }
              finally { setBulkGrabbing(false); }
            }}
            className="px-3 py-1 bg-emerald-600 hover:bg-emerald-700 rounded text-sm flex items-center gap-1 disabled:opacity-50"
          >
            <Search className={`w-3 h-3 ${bulkGrabbing ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">{bulkGrabbing ? 'Grabbing...' : 'Grab Contacts'}</span>
            <span className="sm:hidden">{bulkGrabbing ? '...' : 'Grab'}</span>
          </button>
          <button
            disabled={bulkGrabbing}
            onClick={async (e) => {
              const btn = e.currentTarget;
              const origText = btn.innerText;
              btn.disabled = true;
              btn.innerText = 'Checking...';
              setBulkActionResult(null);
              try {
                const r = await api.classifyAdult(selIds);
                const msg = `✅ ${r.adult} adult, ${r.non_adult} non-adult, ${r.unclear} unclear (${r.scanned} checked)`;
                toast(msg);
                setBulkActionResult({ ok: true, message: msg });
                loadDomains();
              } catch (err: any) { toast(err.message, 'error'); setBulkActionResult({ ok: false, message: `❌ ${err.message}` }); }
              finally { btn.disabled = false; btn.innerText = origText; }
            }}
            className="px-3 py-1 bg-purple-600 hover:bg-purple-700 rounded text-sm disabled:opacity-50"
          >
            Check Adult
          </button>
          <button onClick={() => { setRowSelection({}); setBulkActionResult(null); }} className="px-3 py-1 bg-gray-600 hover:bg-gray-700 rounded text-sm ml-auto">Clear</button>
        </div>
      )}
      {bulkActionResult && (
        <div className={`p-3 rounded-lg flex items-center justify-between ${bulkActionResult.ok ? 'bg-emerald-900/30 border border-emerald-700' : 'bg-red-900/30 border border-red-700'}`}>
          <span className="text-sm">{bulkActionResult.message}</span>
          <button onClick={() => setBulkActionResult(null)} className="text-gray-400 hover:text-white ml-2"><XIcon className="w-4 h-4" /></button>
        </div>
      )}

      <div className="bg-gray-800 rounded-lg border border-gray-700 p-2 sm:p-4">
        <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-2 sm:gap-0 mb-3">
          <span className="text-sm text-gray-400">{filtered.length} rows</span>
          <div className="relative">
            <button onClick={() => setColMenuOpen(v => !v)} className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-sm flex items-center gap-1"><Columns3 className="w-4 h-4" /> <span className="hidden sm:inline">Columns</span></button>
            {colMenuOpen && (
              <div className="absolute right-0 mt-1 bg-gray-800 border border-gray-700 rounded shadow-lg z-10 py-1 min-w-[160px] max-h-[300px] overflow-y-auto">
                {table.getAllLeafColumns().filter(c => c.id !== 'select').map(c => (
                  <label key={c.id} className="flex items-center px-3 py-1 hover:bg-gray-700 cursor-pointer text-sm">
                    <input type="checkbox" checked={c.getIsVisible()} onChange={c.getToggleVisibilityHandler()} className="mr-2" />
                    {typeof c.columnDef.header === 'string' ? c.columnDef.header : c.id}
                  </label>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="overflow-x-auto -mx-2 sm:mx-0">
          <table className="w-full" style={{ minWidth: table.getTotalSize() }}>
            <thead className="bg-gray-700">
              {table.getHeaderGroups().map(hg => (
                <tr key={hg.id}>
                  {hg.headers.map(h => (
                    <th key={h.id} className="px-3 py-3 text-left text-sm font-medium relative select-none" style={{ width: h.getSize() }}>
                      <div className={`flex items-center gap-1 ${h.column.getCanSort() ? 'cursor-pointer' : ''}`} onClick={h.column.getToggleSortingHandler()}>
                        {h.isPlaceholder ? null : flexRender(h.column.columnDef.header, h.getContext())}
                        {h.column.getIsSorted() === 'asc' ? <ChevronUp className="w-3 h-3" /> : h.column.getIsSorted() === 'desc' ? <ChevronDown className="w-3 h-3" /> : h.column.getCanSort() ? <ChevronsUpDown className="w-3 h-3 text-gray-500" /> : null}
                      </div>
                      {h.column.getCanResize() && <div onMouseDown={h.getResizeHandler()} onTouchStart={h.getResizeHandler()} className="absolute right-0 top-0 bottom-0 w-1.5 cursor-col-resize hover:bg-pink-500/50" />}
                    </th>
                  ))}
                  <th className="px-3 py-3 w-20"></th>
                </tr>
              ))}
            </thead>
            <tbody>
              {loading ? <tr><td colSpan={99} className="px-4 py-8 text-center text-gray-500">Loading...</td></tr> :
               table.getRowModel().rows.length === 0 ? <tr><td colSpan={99} className="px-4 py-8 text-center text-gray-500">No domains</td></tr> :
               table.getRowModel().rows.map(r => (
                <tr key={r.id} className={`border-t border-gray-700 hover:bg-gray-700/50 ${r.getIsSelected() ? 'bg-pink-900/20' : ''}`}>
                  {r.getVisibleCells().map(c => <td key={c.id} className="px-3 py-2.5 text-sm" style={{ width: c.column.getSize() }}>{flexRender(c.column.columnDef.cell, c.getContext())}</td>)}
                  <td className="px-3 py-2.5 flex gap-2">
                    <button onClick={() => analyzeDomain(r.original.id)} disabled={analyzingIds.has(r.original.id)} title="Update metrics" className="text-gray-400 hover:text-pink-400 disabled:opacity-50"><RefreshCw className={`w-3.5 h-3.5 ${analyzingIds.has(r.original.id) ? 'animate-spin' : ''}`} /></button>
                    <button onClick={() => setDeleteConfirm({ ids: [r.original.id], label: r.original.domain })} className="text-red-400 hover:text-red-300"><Trash2 className="w-3.5 h-3.5" /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-3 mt-4 pt-4 border-t border-gray-700">
          <div className="flex items-center gap-2"><span className="text-sm text-gray-400 shrink-0">Per page:</span>
            <select value={table.getState().pagination.pageSize} onChange={e => table.setPageSize(+e.target.value)} className="px-2 py-1 bg-gray-700 border border-gray-600 rounded text-sm">
              {[50,100,250,500].map(n => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
          <div className="flex flex-col sm:flex-row items-center gap-2 sm:gap-4">
            <span className="text-sm text-gray-400">{table.getState().pagination.pageIndex * table.getState().pagination.pageSize + 1}-{Math.min((table.getState().pagination.pageIndex + 1) * table.getState().pagination.pageSize, filtered.length)} of {filtered.length}</span>
            <div className="flex gap-2">
              <button onClick={() => table.previousPage()} disabled={!table.getCanPreviousPage()} className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-sm disabled:opacity-50 flex items-center gap-1"><ArrowLeft className="w-3 h-3" /> <span className="hidden sm:inline">Prev</span></button>
              <button onClick={() => table.nextPage()} disabled={!table.getCanNextPage()} className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-sm disabled:opacity-50 flex items-center gap-1"><span className="hidden sm:inline">Next</span> <ArrowRight className="w-3 h-3" /></button>
            </div>
          </div>
        </div>
      </div>

      {/* Import Modal */}
      <Modal open={importOpen} onClose={() => setImportOpen(false)} title="Import Domains">
        <div className="flex border-b border-gray-700 mb-4">
          <button onClick={() => { setImportTab('text'); setImportResult(null); }} className={`px-4 py-2 text-sm border-b-2 ${importTab === 'text' ? 'border-pink-500 text-white' : 'border-transparent text-gray-400'}`}>Text</button>
          <button onClick={() => { setImportTab('csv'); setImportResult(null); }} className={`px-4 py-2 text-sm border-b-2 ${importTab === 'csv' ? 'border-pink-500 text-white' : 'border-transparent text-gray-400'}`}>Domains CSV</button>
          <button onClick={() => { setImportTab('ahrefs'); setImportResult(null); }} className={`px-4 py-2 text-sm border-b-2 ${importTab === 'ahrefs' ? 'border-pink-500 text-white' : 'border-transparent text-gray-400'}`}>Ahrefs Backlinks</button>
        </div>
        {importTab === 'text' ? (
          <form onSubmit={importText2}>
            <textarea value={importText} onChange={e => setImportText(e.target.value)} rows={8} placeholder="One domain per line..." className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-pink-500 font-mono text-sm" />
            <label className="flex items-center gap-2 mt-3"><input type="checkbox" checked={importComp} onChange={e => setImportComp(e.target.checked)} /><span className="text-sm">Mark as competitors</span></label>
            <div className="flex justify-end gap-3 mt-4">
              <button type="button" onClick={() => setImportOpen(false)} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm">Cancel</button>
              <button type="submit" className="px-4 py-2 bg-pink-600 hover:bg-pink-700 rounded-lg text-sm font-medium">Import</button>
            </div>
          </form>
        ) : importTab === 'csv' ? (
          <form onSubmit={importDomainsCsv}>
            <p className="text-xs text-gray-500 mb-3">CSV with a "domain" column. Optional: "dr", "traffic" columns for metrics. Supports Ahrefs exports.</p>
            <div className="mb-4"><label className="block text-sm text-gray-400 mb-2">CSV File</label>
              <input type="file" accept=".csv" onChange={e => setCsvFile(e.target.files?.[0] || null)} required className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-sm" /></div>
            <div className="grid grid-cols-2 gap-3 mb-4">
              <div>
                <label className="block text-xs text-gray-500 mb-1">Min Traffic</label>
                <input type="number" value={csvMinTraffic} onChange={e => setCsvMinTraffic(e.target.value)} placeholder="e.g. 1000" className="w-full px-3 py-1.5 bg-gray-700 border border-gray-600 rounded-lg text-sm focus:outline-none focus:border-pink-500" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Max Traffic</label>
                <input type="number" value={csvMaxTraffic} onChange={e => setCsvMaxTraffic(e.target.value)} placeholder="e.g. 500000" className="w-full px-3 py-1.5 bg-gray-700 border border-gray-600 rounded-lg text-sm focus:outline-none focus:border-pink-500" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Min DR</label>
                <input type="number" value={csvMinDr} onChange={e => setCsvMinDr(e.target.value)} placeholder="e.g. 20" className="w-full px-3 py-1.5 bg-gray-700 border border-gray-600 rounded-lg text-sm focus:outline-none focus:border-pink-500" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Max DR</label>
                <input type="number" value={csvMaxDr} onChange={e => setCsvMaxDr(e.target.value)} placeholder="e.g. 80" className="w-full px-3 py-1.5 bg-gray-700 border border-gray-600 rounded-lg text-sm focus:outline-none focus:border-pink-500" />
              </div>
            </div>
            <label className="flex items-center gap-2 mb-4">
              <input type="checkbox" checked={csvAdultOnly} onChange={e => setCsvAdultOnly(e.target.checked)} className="rounded" />
              <span className="text-sm text-gray-400">Adult domains only</span>
              <span className="text-xs text-gray-600">(filters by domain name keywords)</span>
            </label>
            {importProgress && <p className="text-xs text-pink-400 mb-3 animate-pulse">{importProgress}</p>}
            {importResult && <p className={`text-sm mb-3 p-2 rounded ${importResult.ok ? 'bg-emerald-900/40 text-emerald-300' : 'bg-red-900/40 text-red-300'}`}>{importResult.message}</p>}
            <div className="flex justify-end gap-3">
              <button type="button" onClick={() => setImportOpen(false)} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm">Cancel</button>
              <button type="submit" disabled={importing} className="px-4 py-2 bg-pink-600 hover:bg-pink-700 rounded-lg text-sm font-medium disabled:opacity-50">
                {importing ? 'Importing...' : 'Import'}
              </button>
            </div>
          </form>
        ) : (
          <form onSubmit={importCsv2}>
            <p className="text-xs text-gray-500 mb-3">Import backlinks from Ahrefs CSV export. Creates domains + backlink records.</p>
            <div className="mb-4"><label className="block text-sm text-gray-400 mb-2">Competitor Domain</label>
              <input type="text" value={csvComp} onChange={e => setCsvComp(e.target.value)} placeholder="competitor.com" required className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-pink-500" /></div>
            <div className="mb-4"><label className="block text-sm text-gray-400 mb-2">Ahrefs CSV File</label>
              <input type="file" accept=".csv" onChange={e => setCsvFile(e.target.files?.[0] || null)} required className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-sm" /></div>
            <div className="flex justify-end gap-3">
              <button type="button" onClick={() => setImportOpen(false)} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm">Cancel</button>
              <button type="submit" disabled={importing} className="px-4 py-2 bg-pink-600 hover:bg-pink-700 rounded-lg text-sm font-medium disabled:opacity-50">
                {importing ? 'Importing...' : 'Import'}
              </button>
            </div>
          </form>
        )}
      </Modal>

      <Modal open={presetsOpen} onClose={() => setPresetsOpen(false)} title="Manage Presets">
        <div className="mb-4"><label className="block text-sm text-gray-400 mb-2">Categories (one per line)</label>
          <textarea value={presetCats} onChange={e => setPresetCats(e.target.value)} rows={5} className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-pink-500 font-mono text-sm" /></div>
        <div className="mb-4"><label className="block text-sm text-gray-400 mb-2">Tags (one per line)</label>
          <textarea value={presetTags} onChange={e => setPresetTags(e.target.value)} rows={5} className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-pink-500 font-mono text-sm" /></div>
        <div className="flex justify-end gap-3">
          <button onClick={() => setPresetsOpen(false)} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm">Cancel</button>
          <button onClick={savePresets} className="px-4 py-2 bg-pink-600 hover:bg-pink-700 rounded-lg text-sm font-medium">Save</button>
        </div>
      </Modal>

      {/* Delete Confirm */}
      <Modal open={!!deleteConfirm} onClose={() => setDeleteConfirm(null)} title="Confirm Delete" maxWidth="max-w-md">
        <p className="text-sm text-gray-300 mb-6">Are you sure you want to delete <strong>{deleteConfirm?.label}</strong>? This cannot be undone.</p>
        <div className="flex justify-end gap-3">
          <button onClick={() => setDeleteConfirm(null)} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm">Cancel</button>
          <button onClick={confirmDelete} className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg text-sm font-medium">Delete</button>
        </div>
      </Modal>

      <Modal open={bulkOpen} onClose={() => setBulkOpen(false)} title={`Edit ${selIds.length} Domains`}>
        <form onSubmit={bulkEdit}>
          <div className="mb-4"><label className="block text-sm text-gray-400 mb-2">Category</label>
            <select value={bulkCat} onChange={e => setBulkCat(e.target.value)} className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-sm">
              <option value="">Don't change</option>{categories.map(c => <option key={c}>{c}</option>)}<option value="__new__">+ New</option>
            </select></div>
          <div className="mb-4"><label className="block text-sm text-gray-400 mb-2">Tags</label>
            <input type="text" value={bulkTags} onChange={e => setBulkTags(e.target.value)} placeholder="tag1, tag2" className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-pink-500" /></div>
          <div className="flex justify-end gap-3">
            <button type="button" onClick={() => setBulkOpen(false)} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm">Cancel</button>
            <button type="submit" className="px-4 py-2 bg-pink-600 hover:bg-pink-700 rounded-lg text-sm font-medium">Apply</button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
