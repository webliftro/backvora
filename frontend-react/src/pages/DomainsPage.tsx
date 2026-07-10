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
  Globe, Mail, FileText, ShieldAlert,
} from 'lucide-react';
import { api } from '../api';
import { useToast } from '../components/Toast';
import Modal from '../components/Modal';
import { PageHeader, Button, StatusPill, ResultBanner, LoadingState, EmptyState } from '../components/ui';
import { buttonClasses, statusTone, filterFieldClass } from '../components/styles';
import type { Domain } from '../types';
import { DOMAIN_STATUSES } from '../types';

const col = createColumnHelper<Domain>();

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
  // Backward-compat: older builds persisted a single `targetFilter: string`; migrate it to the array.
  function loadTargetFilters(): string[] {
    const f = loadFilters();
    if (Array.isArray(f.targetFilters)) return f.targetFilters.filter((t: unknown): t is string => typeof t === 'string');
    if (typeof f.targetFilter === 'string' && f.targetFilter) return [f.targetFilter];
    return [];
  }
  const [search, setSearch] = useState(() => loadFilters().search || '');
  const [statusFilter, setStatusFilter] = useState(() => loadFilters().statusFilter || '');
  const [categoryFilter, setCategoryFilter] = useState(() => loadFilters().categoryFilter || '');
  const [targetFilters, setTargetFilters] = useState<string[]>(loadTargetFilters);
  const [targetMenuOpen, setTargetMenuOpen] = useState(false);
  const [adultFilter, setAdultFilter] = useState(() => loadFilters().adultFilter || '');
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
      search, statusFilter, categoryFilter, targetFilters, adultFilter, hasBacklink,
      competitorOnly, minTraffic, maxTraffic, minDR, maxDR, hasContacts, linkTypeFilter,
    }));
  }, [search, statusFilter, categoryFilter, targetFilters, adultFilter, hasBacklink, competitorOnly, minTraffic, maxTraffic, minDR, maxDR, hasContacts, linkTypeFilter]);

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
  const [bulkActionResult, setBulkActionResult] = useState<{ ok: boolean; busy?: boolean; message: string } | null>(null);

  useEffect(() => {
    loadDomains(); loadCategories();
    const p = new URLSearchParams(window.location.search);
    if (p.get('target')) setTargetFilters([p.get('target')!]);
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
    if (targetFilters.length && !(d.backlink_target && targetFilters.includes(d.backlink_target))) return false;
    if (adultFilter === 'yes' && d.domain_niche !== 'adult') return false;
    if (adultFilter === 'no' && d.domain_niche !== 'non_adult') return false;
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
  }), [domains, search, statusFilter, categoryFilter, targetFilters, adultFilter, hasBacklink, hasContacts, competitorOnly, minTraffic, maxTraffic, minDR, maxDR, linkTypeFilter]);

  const availableLinkTypes = useMemo(() => {
    const types = new Set<string>();
    domains.forEach(d => { (Array.isArray(d.link_types) ? d.link_types : []).forEach((t: string) => types.add(t)); });
    return [...types].sort();
  }, [domains]);

  async function updateDomainCategory(domainId: string, nextCategory: string | null) {
    try {
      await api.updateDomain(domainId, { category: nextCategory || null });
      setDomains(prev => prev.map(d => d.id === domainId ? { ...d, category: nextCategory || null } : d));
      if (nextCategory && !categories.includes(nextCategory)) setCategories(prev => [...prev, nextCategory].sort());
      toast('Category updated');
    } catch (e: any) {
      toast(e.message, 'error');
    }
  }

  const columns = useMemo(() => [
    col.display({ id: 'select', size: 40, enableResizing: false,
      header: ({ table }) => <input type="checkbox" checked={table.getIsAllPageRowsSelected()} onChange={table.getToggleAllPageRowsSelectedHandler()} />,
      cell: ({ row }) => <input type="checkbox" checked={row.getIsSelected()} onChange={row.getToggleSelectedHandler()} />,
    }),
    col.accessor('domain', { header: 'Domain', size: 200,
      cell: i => <div className="flex items-center gap-1"><Link to={`/domains/${i.row.original.id}`} className="font-mono text-[13px] text-pink-400 hover:underline truncate">{i.getValue()}</Link><a href={`https://${i.getValue()}`} target="_blank" rel="noopener" className="text-gray-500 hover:text-gray-300 shrink-0" title={`Open ${i.getValue()}`}><ExternalLink className="w-3 h-3" /></a></div>,
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
                {hasPrimary ? <Check className="w-4 h-4" /> : null}
                {count}
              </span>
            ) : hasInfo ? (
              <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-blue-900/40 text-blue-400" title="Has owner/email/telegram info">
                <Check className="w-4 h-4" />
              </span>
            ) : null}
            {hasEmail && <span title="Has email" aria-label="Has email"><Mail className="w-4 h-4 text-gray-400" aria-hidden /></span>}
            {hasForm && <span title="Has contact form" aria-label="Has contact form"><FileText className="w-4 h-4 text-gray-400" aria-hidden /></span>}
            {hasCaptcha && <span title="Has CAPTCHA" aria-label="Has CAPTCHA"><ShieldAlert className="w-4 h-4 text-yellow-400" aria-hidden /></span>}
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
    col.accessor('category', {
      header: 'Category',
      size: 150,
      cell: i => {
        const domain = i.row.original;
        const current = i.getValue() || '';
        const options = current && !categories.includes(current) ? [...categories, current].sort() : categories;
        return (
          <select
            value={current}
            onChange={async e => {
              let next = e.target.value;
              if (next === '__new__') {
                const created = prompt('New category:')?.trim();
                if (!created) return;
                next = created;
              }
              await updateDomainCategory(domain.id, next || null);
            }}
            className="w-full rounded border border-gray-700 bg-gray-900 px-2 py-1 text-xs text-gray-200"
          >
            <option value="">None</option>
            {options.map(c => <option key={c} value={c}>{c}</option>)}
            <option value="__new__">New...</option>
          </select>
        );
      },
    }),
    col.accessor('tags', { header: 'Tags', size: 150,
      cell: i => { const v = i.getValue(); if (!v) return '-'; return <div className="flex flex-wrap gap-1">{v.split(',').filter(Boolean).map((t,j) => <span key={j} className="px-1.5 py-0.5 bg-gray-700 rounded text-xs">{t.trim()}</span>)}</div>; },
    }),
    col.accessor('link_types', { header: 'Link Types', size: 150, enableSorting: false,
      cell: i => { const v = i.getValue(); if (!v?.length) return '-'; return <div className="flex flex-wrap gap-1">{v.map((t,j) => <span key={j} className="px-1.5 py-0.5 bg-gray-700 rounded text-xs">{t}</span>)}</div>; },
    }),
    col.accessor('status', { header: 'Status', size: 100,
      cell: i => <StatusPill tone={statusTone(i.getValue())}>{i.getValue()}</StatusPill>,
    }),
    col.accessor('is_competitor', { header: 'Competitor', size: 90, cell: i => i.getValue() ? <Check className="w-4 h-4 text-green-400" /> : <XIcon className="w-4 h-4 text-gray-500" /> }),
    col.accessor('is_adult', { header: 'Adult', size: 60, cell: i => {
      const niche = i.row.original.domain_niche;
      const overridden = i.row.original.is_adult_overridden;
      const title = overridden ? 'manual override' : (niche || 'unclassified');
      if (niche === 'unknown' || (!niche && i.getValue())) return <span className="text-gray-500" title={title}>?</span>;
      return <span title={title}>{i.getValue() ? <Check className="w-4 h-4 text-green-400" /> : <XIcon className="w-4 h-4 text-gray-500" />}</span>;
    } }),
    col.accessor('created_at', { header: 'Added', size: 100, cell: i => i.getValue() ? new Date(i.getValue()!).toLocaleDateString() : '-' }),
  ], [categories]);

  const table = useReactTable({
    data: filtered, columns, state: { sorting, rowSelection, columnVisibility },
    onSortingChange: setSorting, onRowSelectionChange: setRowSelection, onColumnVisibilityChange: setColumnVisibility,
    getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel(), getPaginationRowModel: getPaginationRowModel(),
    enableRowSelection: true, enableColumnResizing: true, columnResizeMode: 'onChange',
    autoResetPageIndex: false,
    initialState: { pagination: { pageSize: 50 } },
  });

  useEffect(() => {
    table.setPageIndex(0);
  }, [
    search,
    statusFilter,
    categoryFilter,
    targetFilters,
    adultFilter,
    hasBacklink,
    competitorOnly,
    minTraffic,
    maxTraffic,
    minDR,
    maxDR,
    hasContacts,
    linkTypeFilter,
  ]);

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
      const parts = [`Added ${r.added} domains`];
      if (r.skipped) parts.push(`${r.skipped} duplicates`);
      if (r.filtered_out) parts.push(`${r.filtered_out} filtered out`);
      parts.push(`${r.total_rows} total rows`);
      if (r.adult_scan?.fetched) parts.push(`homepage-checked ${r.adult_scan.fetched} ambiguous (${r.adult_scan.resolved} resolved)`);
      if (r.adult_scan?.deferred) parts.push(`${r.adult_scan.deferred} deferred to a later import/scan`);
      setImportResult({ ok: true, message: parts.join(', ') });
      setCsvFile(null); setCsvMinTraffic(''); setCsvMaxTraffic(''); setCsvMinDr(''); setCsvMaxDr('');
      loadDomains();
    } catch (e: any) { setImportProgress(''); setImportResult({ ok: false, message: e.message }); } finally { setImporting(false); }
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

  function clearFilters() { setSearch(''); setStatusFilter(''); setCategoryFilter(''); setTargetFilters([]); setAdultFilter(''); setHasBacklink(''); setHasContacts(''); setLinkTypeFilter(''); setCompetitorOnly(false); setMinTraffic(''); setMaxTraffic(''); setMinDR(''); setMaxDR(''); }

  async function bulkGrabAllMissing() {
    if (!confirm('Grab contacts for all domains without any saved contacts? This may take a while.')) return;
    setBulkGrabbing(true);
    setBulkGrabProgress({ processed: 0, total: 0, contacts: 0 });
    try {
      const result = await api.bulkGrabContacts();
      setBulkGrabProgress({ processed: result.scanned, total: result.scanned, contacts: result.found });
      toast(`Found ${result.found} contacts from ${result.scanned} domains scanned`);
      await loadDomains();
    } catch (e: any) {
      toast(e.message || 'Bulk grab failed', 'error');
    }
    setBulkGrabbing(false);
    setTimeout(() => setBulkGrabProgress(null), 3000);
  }

  const ic = filterFieldClass;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Domains"
        actions={<>
          <Button onClick={openPresets} title="Presets" icon={Settings}>
            <span className="hidden sm:inline">Presets</span>
          </Button>
          <Button onClick={bulkGrabAllMissing} disabled={bulkGrabbing}>
            <Search className={`w-4 h-4 ${bulkGrabbing ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">{bulkGrabbing ? 'Grabbing...' : 'Grab All Missing'}</span>
            <span className="sm:hidden">{bulkGrabbing ? 'Grab...' : 'Grab'}</span>
          </Button>
          <Button onClick={() => setImportOpen(true)} title="Import" icon={Upload}>
            <span className="hidden sm:inline">Import</span>
          </Button>
          <Link to="/domains/new" className={buttonClasses('primary')}>
            <Plus className="w-4 h-4" /> <span className="hidden sm:inline">Add Domain</span><span className="sm:hidden">Add</span>
          </Link>
        </>}
      />

      {bulkGrabProgress && (
        <ResultBanner tone="success">
          Processed {bulkGrabProgress.processed} domains, found {bulkGrabProgress.contacts} contacts
        </ResultBanner>
      )}

      <div className="flex gap-2 sm:gap-3 items-center flex-wrap">
        <input type="text" placeholder="Search domain, tags, notes..." value={search} onChange={e => setSearch(e.target.value)} className={`${ic} w-full sm:w-48`} />
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className={`${ic} flex-1 sm:flex-none min-w-[42%] sm:min-w-0`}><option value="">All Status</option>{DOMAIN_STATUSES.map(s => <option key={s}>{s}</option>)}</select>
        <select value={categoryFilter} onChange={e => setCategoryFilter(e.target.value)} className={`${ic} flex-1 sm:flex-none min-w-[42%] sm:min-w-0`}><option value="">All Categories</option>{categories.map(c => <option key={c}>{c}</option>)}</select>
        <div className="relative flex-1 sm:flex-none min-w-[42%] sm:min-w-0">
          <button type="button" onClick={() => setTargetMenuOpen(v => !v)} className={`${ic} w-full flex items-center justify-between gap-2 text-left`}>
            <span className="truncate">{targetFilters.length === 0 ? 'All Targets' : targetFilters.length === 1 ? targetFilters[0] : `${targetFilters.length} targets`}</span>
            <ChevronDown className="w-4 h-4 shrink-0 text-gray-500" />
          </button>
          {targetMenuOpen && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setTargetMenuOpen(false)} />
              <div className="absolute left-0 mt-1 glass border border-gray-700 rounded-md z-20 py-1 min-w-[180px] max-h-[300px] overflow-y-auto">
                {targets.length === 0 ? (
                  <div className="px-3 py-1 text-sm text-gray-500">No targets</div>
                ) : (<>
                  {targetFilters.length > 0 && (
                    <button type="button" onClick={() => setTargetFilters([])} className="w-full text-left px-3 py-1 text-xs text-gray-400 hover:bg-gray-700">Clear selection</button>
                  )}
                  {targets.map(t => (
                    <label key={t} className="flex items-center px-3 py-1 hover:bg-gray-700 cursor-pointer text-sm">
                      <input type="checkbox" checked={targetFilters.includes(t)} onChange={() => setTargetFilters(prev => prev.includes(t) ? prev.filter(x => x !== t) : [...prev, t])} className="mr-2" />
                      <span className="truncate">{t}</span>
                    </label>
                  ))}
                </>)}
              </div>
            </>
          )}
        </div>
        <select value={adultFilter} onChange={e => setAdultFilter(e.target.value)} className={`${ic} flex-1 sm:flex-none min-w-[42%] sm:min-w-0`}><option value="">Adult?</option><option value="yes">Yes</option><option value="no">No</option></select>
        <select value={hasBacklink} onChange={e => setHasBacklink(e.target.value)} className={`${ic} flex-1 sm:flex-none min-w-[42%] sm:min-w-0`}><option value="">Has Backlink?</option><option value="yes">Yes</option><option value="no">No</option></select>
        <select value={hasContacts} onChange={e => setHasContacts(e.target.value)} className={`${ic} flex-1 sm:flex-none min-w-[42%] sm:min-w-0`}><option value="">Has Contacts?</option><option value="yes">Yes</option><option value="no">No</option></select>
        <select value={linkTypeFilter} onChange={e => setLinkTypeFilter(e.target.value)} className={`${ic} flex-1 sm:flex-none min-w-[42%] sm:min-w-0`}><option value="">All Link Types</option>{availableLinkTypes.map(t => <option key={t} value={t}>{t}</option>)}</select>
        <Button onClick={clearFilters} variant="ghost" className="shrink-0">Clear</Button>
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
        <div className="p-3 bg-pink-600/10 border border-pink-600/30 rounded-lg flex flex-wrap items-center gap-2 sm:gap-4">
          <span className="text-sm">{selIds.length} selected</span>
          <Button onClick={bulkDelete} aria-label="Delete selected domains" variant="danger" size="sm" icon={Trash2}><span className="hidden sm:inline">Delete</span></Button>
          <Button onClick={() => setBulkOpen(true)} variant="primary" size="sm"><span className="hidden sm:inline">Category/Tags</span><span className="sm:hidden">Edit</span></Button>
          <button
            disabled={bulkGrabbing}
            onClick={async () => {
              setBulkGrabbing(true);
              setBulkActionResult(null);
              try {
                const resp = await fetch('/api/v1/domains/selected-grab-contacts', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json', ...((): Record<string, string> => { const t = localStorage.getItem('token'); return t ? { Authorization: `Bearer ${t}` } : {}; })() },
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
                          setBulkActionResult({ ok: true, busy: true, message: `Processing ${ev.total} domains...` });
                        } else if (ev.type === 'phase') {
                          lastPhase = ev.phase;
                          setBulkActionResult({ ok: true, busy: true, message: ev.message });
                        } else if (ev.type === 'found') {
                          foundCount++;
                          setBulkActionResult({ ok: true, busy: true, message: `[${ev.progress}/${totalCount}] Found ${ev.email} for ${ev.domain} (${ev.method})` });
                        } else if (ev.type === 'miss') {
                          setBulkActionResult({ ok: true, busy: true, message: `[${ev.progress}/${totalCount}] No contact for ${ev.domain} (${lastPhase})` });
                        } else if (ev.type === 'done') {
                          const msg = `Done! Found ${ev.found} contacts out of ${ev.total} domains (${ev.missed} without contact)`;
                          setBulkActionResult({ ok: true, message: msg });
                          toast(msg);
                          loadDomains();
                        }
                      } catch {}
                    }
                  }
                }
              } catch (e: any) { toast(e.message, 'error'); setBulkActionResult({ ok: false, message: e.message }); }
              finally { setBulkGrabbing(false); }
            }}
            className="inline-flex items-center justify-center gap-1.5 px-3 py-1 text-sm rounded-md bg-emerald-600 hover:bg-emerald-700 transition-colors disabled:opacity-50 disabled:pointer-events-none"
          >
            <Search className={`w-4 h-4 ${bulkGrabbing ? 'animate-spin' : ''}`} />
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
                const msg = `${r.adult} adult, ${r.non_adult} non-adult, ${r.unclear} unclear (${r.scanned} checked)`;
                toast(msg);
                setBulkActionResult({ ok: true, message: msg });
                loadDomains();
              } catch (err: any) { toast(err.message, 'error'); setBulkActionResult({ ok: false, message: err.message }); }
              finally { btn.disabled = false; btn.innerText = origText; }
            }}
            className="inline-flex items-center justify-center px-3 py-1 text-sm rounded-md bg-gray-700 hover:bg-gray-600 transition-colors disabled:opacity-50 disabled:pointer-events-none"
          >
            Check Adult
          </button>
          <button
            disabled={bulkGrabbing}
            onClick={async (e) => {
              const btn = e.currentTarget;
              const origText = btn.innerText;
              btn.disabled = true;
              btn.innerText = 'Labeling...';
              setBulkActionResult(null);
              try {
                const r = await api.classifyDomainTypes(selIds);
                const msg = `Updated ${r.updated} domain type labels, ${r.unmatched} unmatched (${r.scanned} checked)`;
                toast(msg);
                setBulkActionResult({ ok: true, message: msg });
                loadDomains();
              } catch (err: any) { toast(err.message, 'error'); setBulkActionResult({ ok: false, message: err.message }); }
              finally { btn.disabled = false; btn.innerText = origText; }
            }}
            className="inline-flex items-center justify-center px-3 py-1 text-sm rounded-md bg-gray-700 hover:bg-gray-600 transition-colors disabled:opacity-50 disabled:pointer-events-none"
          >
            Label Type
          </button>
          <Button onClick={() => { setRowSelection({}); setBulkActionResult(null); }} size="sm" className="ml-auto">Clear</Button>
        </div>
      )}
      {bulkActionResult && (
        <ResultBanner
          tone={bulkActionResult.busy ? 'progress' : bulkActionResult.ok ? 'success' : 'error'}
          onDismiss={() => setBulkActionResult(null)}
        >
          {bulkActionResult.message}
        </ResultBanner>
      )}

      <div className="bg-gray-800 rounded-lg border border-gray-700 p-2 sm:p-4">
        <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-2 sm:gap-0 mb-3">
          <span className="text-sm text-gray-400">{filtered.length} rows</span>
          <div className="relative">
            <Button onClick={() => setColMenuOpen(v => !v)} aria-label="Manage columns" size="sm" icon={Columns3}><span className="hidden sm:inline">Columns</span></Button>
            {colMenuOpen && (
              <div className="absolute right-0 mt-1 glass border border-gray-700 rounded-md z-10 py-1 min-w-[160px] max-h-[300px] overflow-y-auto">
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
                    <th key={h.id} className="px-3 py-2.5 text-left text-xs font-medium uppercase tracking-wider text-gray-400 relative select-none" style={{ width: h.getSize() }}>
                      <div className={`flex items-center gap-1 ${h.column.getCanSort() ? 'cursor-pointer' : ''}`} onClick={h.column.getToggleSortingHandler()}>
                        {h.isPlaceholder ? null : flexRender(h.column.columnDef.header, h.getContext())}
                        {h.column.getIsSorted() === 'asc' ? <ChevronUp className="w-3 h-3" /> : h.column.getIsSorted() === 'desc' ? <ChevronDown className="w-3 h-3" /> : h.column.getCanSort() ? <ChevronsUpDown className="w-3 h-3 text-gray-500" /> : null}
                      </div>
                      {h.column.getCanResize() && <div onMouseDown={h.getResizeHandler()} onTouchStart={h.getResizeHandler()} className="absolute right-0 top-0 bottom-0 w-1.5 cursor-col-resize hover:bg-gray-500/40" />}
                    </th>
                  ))}
                  <th className="px-3 py-2.5 w-20"></th>
                </tr>
              ))}
            </thead>
            <tbody>
              {loading ? <tr><td colSpan={99}><LoadingState label="Loading domains..." /></td></tr> :
               table.getRowModel().rows.length === 0 ? <tr><td colSpan={99}><EmptyState icon={Globe} title="No domains" hint="Import domains or add one to get started" /></td></tr> :
               table.getRowModel().rows.map(r => (
                <tr key={r.id} className={`border-t border-gray-700 hover:bg-gray-700/50 ${r.getIsSelected() ? 'bg-pink-600/10' : ''}`}>
                  {r.getVisibleCells().map(c => <td key={c.id} className="px-3 py-2.5 text-sm" style={{ width: c.column.getSize() }}>{flexRender(c.column.columnDef.cell, c.getContext())}</td>)}
                  <td className="px-3 py-2.5 flex gap-2">
                    <button onClick={() => analyzeDomain(r.original.id)} disabled={analyzingIds.has(r.original.id)} title="Update metrics" className="text-gray-400 hover:text-pink-400 disabled:opacity-50"><RefreshCw className={`w-4 h-4 ${analyzingIds.has(r.original.id) ? 'animate-spin' : ''}`} /></button>
                    <button onClick={() => setDeleteConfirm({ ids: [r.original.id], label: r.original.domain })} title="Delete domain" className="text-red-400 hover:text-red-300"><Trash2 className="w-4 h-4" /></button>
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
              <Button onClick={() => table.previousPage()} disabled={!table.getCanPreviousPage()} aria-label="Previous page" size="sm" icon={ArrowLeft}><span className="hidden sm:inline">Prev</span></Button>
              <Button onClick={() => table.nextPage()} disabled={!table.getCanNextPage()} aria-label="Next page" size="sm"><span className="hidden sm:inline">Next</span> <ArrowRight className="w-4 h-4" /></Button>
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
              <Button onClick={() => setImportOpen(false)}>Cancel</Button>
              <Button type="submit" variant="primary">Import</Button>
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
              <span className="text-xs text-gray-600">(homepage-checks ambiguous domains; drops confirmed non-adult, keeps unclassified)</span>
            </label>
            {importProgress && <ResultBanner tone="progress" className="mb-3">{importProgress}</ResultBanner>}
            {importResult && <ResultBanner tone={importResult.ok ? 'success' : 'error'} className="mb-3">{importResult.message}</ResultBanner>}
            <div className="flex justify-end gap-3">
              <Button onClick={() => setImportOpen(false)}>Cancel</Button>
              <Button type="submit" variant="primary" disabled={importing}>
                {importing ? 'Importing...' : 'Import'}
              </Button>
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
              <Button onClick={() => setImportOpen(false)}>Cancel</Button>
              <Button type="submit" variant="primary" disabled={importing}>
                {importing ? 'Importing...' : 'Import'}
              </Button>
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
          <Button onClick={() => setPresetsOpen(false)}>Cancel</Button>
          <Button onClick={savePresets} variant="primary">Save</Button>
        </div>
      </Modal>

      {/* Delete Confirm */}
      <Modal open={!!deleteConfirm} onClose={() => setDeleteConfirm(null)} title="Confirm Delete" maxWidth="max-w-md">
        <p className="text-sm text-gray-300 mb-6">Are you sure you want to delete <strong>{deleteConfirm?.label}</strong>? This cannot be undone.</p>
        <div className="flex justify-end gap-3">
          <Button onClick={() => setDeleteConfirm(null)}>Cancel</Button>
          <Button onClick={confirmDelete} variant="danger">Delete</Button>
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
            <Button onClick={() => setBulkOpen(false)}>Cancel</Button>
            <Button type="submit" variant="primary">Apply</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
