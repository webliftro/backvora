import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, ExternalLink, Pencil, Plus, Settings, Trash2, Star, RefreshCw, Search, Send, Eye, X, Sparkles, ShieldAlert } from 'lucide-react';
import { api } from '../api';
import { useToast } from '../components/Toast';
import Modal from '../components/Modal';
import { Button, StatusPill } from '../components/ui';
import { statusTone } from '../components/styles';
import type { Domain, LinkPrice } from '../types';
import { DOMAIN_STATUSES } from '../types';

export default function DomainDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { toast } = useToast();
  const [domain, setDomain] = useState<Domain | null>(null);
  const [categories, setCategories] = useState<string[]>([]);
  const [linkTypes, setLinkTypes] = useState<string[]>([]);
  const [analyzing, setAnalyzing] = useState(false);
  const [editDomain, setEditDomain] = useState(false);
  const [editDomainVal, setEditDomainVal] = useState('');
  const [editContact, setEditContact] = useState(false);
  const [editNotes, setEditNotes] = useState(false);
  const [contact, setContact] = useState({ owner: '', email: '', telegram: '', language: '' });
  const [ownerSuggestions, setOwnerSuggestions] = useState<{ owner: string; email: string | null; telegram: string | null }[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [notes, setNotes] = useState('');
  const [typesModal, setTypesModal] = useState(false);
  const [newType, setNewType] = useState('');
  const [priceOpen, setPriceOpen] = useState(false);
  const [editPriceId, setEditPriceId] = useState<string | null>(null);
  const [pf, setPf] = useState({ link_type: '', custom: '', price: '', currency: 'USD', duration: '12', permanent: false, notes: '' });

  // Contacts Grabber
  const [grabbing, setGrabbing] = useState(false);
  const [grabResult, setGrabResult] = useState<any>(null);
  const [dismissedEmails, setDismissedEmails] = useState<Set<string>>(new Set());
  const [forms, setForms] = useState<any[]>([]);
  const [previewData, setPreviewData] = useState<any>(null);
  const [submitting, setSubmitting] = useState<string | null>(null);
  const [solvingStatus, setSolvingStatus] = useState<string>('');
  const [savedContacts, setSavedContacts] = useState<any[]>([]);
  const [savingEmails, setSavingEmails] = useState<Set<string>>(new Set());

  // Send email from template
  const [sendEmailOpen, setSendEmailOpen] = useState(false);
  const [sendEmailTo, setSendEmailTo] = useState('');
  const [sendEmailSubject, setSendEmailSubject] = useState('');
  const [sendEmailBody, setSendEmailBody] = useState('');
  const [sendEmailTemplates, setSendEmailTemplates] = useState<any[]>([]);
  const [sendingEmail, setSendingEmail] = useState(false);

  // Payment methods
  const [payMethods, setPayMethods] = useState<{ id: string; method: string; details: Record<string, string>; is_preferred: boolean }[]>([]);
  const [availablePay, setAvailablePay] = useState<string[]>([]);
  const [payFields, setPayFields] = useState<Record<string, { key: string; label: string; required: boolean }[]>>({});
  const [payOpen, setPayOpen] = useState(false);
  const [payEditId, setPayEditId] = useState<string | null>(null);
  const [payMethod, setPayMethod] = useState('');
  const [payDetailsMap, setPayDetailsMap] = useState<Record<string, string>>({});

  // Publisher Rules
  const [publisherRules, setPublisherRules] = useState<any>(null);
  const [editRules, setEditRules] = useState(false);
  const [rulesForm, setRulesForm] = useState({
    max_urls: '',
    cross_domain: null as boolean | null,
    we_write: null as boolean | null,
    min_words: '',
    max_words: '',
    link_attribute: '' as string,
    max_images: '',
    image_count: '',
    resource_links_count: '',
    skip_resource_links: null as boolean | null,
    brand_mentions_scope: '' as string,
    brand_mentions_brands: '',
    brand_mentions_in_title: null as boolean | null,
    brand_mentions_body_count: '',
    content_guidelines: '',
    placement_notes: '',
  });

  useEffect(() => { if (id) { load(); loadCats(); loadTypes(); loadPayments(); loadForms(); loadContacts(); loadPublisherRules(); } }, [id]);

  async function load() {
    try { const d = await api.getDomain(id!); setDomain(d); setContact({ owner: d.owner || '', email: d.email || '', telegram: d.telegram || '', language: d.language || '' }); setNotes(d.notes || ''); }
    catch { toast('Failed to load', 'error'); }
  }
  async function analyzeDomain() {
    setAnalyzing(true);
    try { const r = await api.analyzeDomain(id!); if (r.success) { toast(`Updated: DR ${r.metrics?.domain_rating ?? '-'}, Traffic ${(r.metrics?.organic_traffic as number)?.toLocaleString() ?? '-'}`); load(); } }
    catch (e: any) { toast(e.message || 'Analysis failed', 'error'); }
    setAnalyzing(false);
  }
  async function loadCats() { try { const d = await api.getCategories(); setCategories(d.categories || []); } catch {} }
  async function loadTypes() { try { const d = await api.getLinkTypes(); setLinkTypes(d.types || []); } catch {} }
  let ownerTimer: ReturnType<typeof setTimeout>;
  function onOwnerInput(val: string) {
    setContact(prev => ({ ...prev, owner: val }));
    clearTimeout(ownerTimer);
    if (val.length >= 2) {
      ownerTimer = setTimeout(async () => {
        try { const r = await api.searchOwners(val); setOwnerSuggestions(r.items); setShowSuggestions(r.items.length > 0); } catch { setShowSuggestions(false); }
      }, 200);
    } else { setShowSuggestions(false); }
  }
  function onEmailInput(val: string) {
    setContact(prev => ({ ...prev, email: val }));
    clearTimeout(ownerTimer);
    if (val.length >= 2) {
      ownerTimer = setTimeout(async () => {
        try { const r = await api.searchOwners(val); setOwnerSuggestions(r.items); setShowSuggestions(r.items.length > 0); } catch { setShowSuggestions(false); }
      }, 200);
    } else { setShowSuggestions(false); }
  }
  async function pickOwner(s: { owner: string; email: string | null; telegram: string | null; payment_methods?: { method: string; details: Record<string, string>; is_preferred: boolean }[] }) {
    setContact({ owner: s.owner || '', email: s.email || '', telegram: s.telegram || '', language: contact.language });
    setShowSuggestions(false);
    // Copy payment methods from owner's other domains
    if (s.payment_methods?.length && id) {
      for (const pm of s.payment_methods) {
        try { await api.addPaymentMethod(id, { method: pm.method, details: pm.details }); } catch {}
      }
      // Set preferred to match source
      await loadPayments();
      const preferred = s.payment_methods.find(p => p.is_preferred);
      if (preferred) {
        const match = payMethods.find(p => p.method === preferred.method);
        if (match) { try { await api.setPreferredPayment(id, match.id); } catch {} }
      }
      await loadPayments();
      toast('Payment methods copied from owner');
    }
  }

  async function loadPayments() { try { const d = await api.getPaymentMethods(id!); setPayMethods(d.items); setAvailablePay(d.available); setPayFields(d.fields || {}); } catch {} }
  async function loadForms() { try { const d = await api.getForms(id!); setForms(d.items || []); } catch {} }
  async function loadContacts() { try { const d = await api.getDomainContacts(id!); setSavedContacts(d.items || []); } catch {} }
  async function loadPublisherRules() {
    try {
      const rules = await api.getPublisherRules(id!);
      if (rules.exists) {
        setPublisherRules(rules);
        setRulesForm({
          max_urls: rules.max_urls?.toString() || '',
          cross_domain: rules.cross_domain,
          we_write: rules.we_write,
          min_words: rules.min_words?.toString() || '',
          max_words: rules.max_words?.toString() || '',
          link_attribute: rules.link_attribute || '',
          max_images: rules.max_images?.toString() || '',
          image_count: rules.image_count?.toString() || '',
          resource_links_count: rules.resource_links_count?.toString() || '',
          skip_resource_links: rules.skip_resource_links,
          brand_mentions_scope: rules.brand_mentions_scope || '',
          brand_mentions_brands: rules.brand_mentions_brands || '',
          brand_mentions_in_title: rules.brand_mentions_in_title,
          brand_mentions_body_count: rules.brand_mentions_body_count?.toString() || '',
          content_guidelines: rules.content_guidelines || '',
          placement_notes: rules.placement_notes || '',
        });
      }
    } catch {}
  }
  async function savePublisherRules(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api.savePublisherRules(id!, {
        max_urls: rulesForm.max_urls ? parseInt(rulesForm.max_urls) : null,
        cross_domain: rulesForm.cross_domain,
        we_write: rulesForm.we_write,
        min_words: rulesForm.min_words ? parseInt(rulesForm.min_words) : null,
        max_words: rulesForm.max_words ? parseInt(rulesForm.max_words) : null,
        link_attribute: rulesForm.link_attribute || null,
        max_images: rulesForm.max_images ? parseInt(rulesForm.max_images) : null,
        image_count: rulesForm.image_count ? parseInt(rulesForm.image_count) : null,
        resource_links_count: rulesForm.resource_links_count ? parseInt(rulesForm.resource_links_count) : null,
        skip_resource_links: rulesForm.skip_resource_links,
        brand_mentions_scope: rulesForm.brand_mentions_scope || null,
        brand_mentions_brands: rulesForm.brand_mentions_brands || null,
        brand_mentions_in_title: rulesForm.brand_mentions_in_title,
        brand_mentions_body_count: rulesForm.brand_mentions_body_count ? parseInt(rulesForm.brand_mentions_body_count) : null,
        content_guidelines: rulesForm.content_guidelines || null,
        placement_notes: rulesForm.placement_notes || null,
      });
      toast('Publisher rules saved!');
      setEditRules(false);
      await loadPublisherRules();
    } catch (e: any) {
      toast(e.message || 'Failed to save', 'error');
    }
  }
  const savedEmails = new Set(savedContacts.map((c: any) => c.email?.toLowerCase()));
  async function saveGrabbedEmail(email: any) {
    setSavingEmails(prev => new Set(prev).add(email.email));
    try {
      await api.createContact({ domain_id: id!, email: email.email, source_page: email.source_url || null, source_type: email.source_type || null });
      toast(`Saved ${email.email}`);
      await loadContacts();
    } catch (e: any) { toast(e.message || 'Failed to save', 'error'); }
    setSavingEmails(prev => { const n = new Set(prev); n.delete(email.email); return n; });
  }
  async function saveAllGrabbedEmails() {
    const unsaved = (grabResult?.emails || []).filter((e: any) => !savedEmails.has(e.email?.toLowerCase()) && !e.already_saved && !dismissedEmails.has(e.email?.toLowerCase()));
    if (!unsaved.length) { toast('All emails already saved'); return; }
    for (const email of unsaved) { await saveGrabbedEmail(email); }
  }
  async function togglePrimary(contactId: string) {
    try { await api.setPrimaryContact(contactId); toast('Primary contact updated'); await loadContacts(); }
    catch (e: any) { toast(e.message || 'Failed', 'error'); }
  }
  async function deleteContact(contactId: string) {
    try { await api.deleteContact(contactId); toast('Contact removed'); await loadContacts(); }
    catch (e: any) { toast(e.message || 'Failed to delete', 'error'); }
  }
  async function openSendEmail(emailAddr: string) {
    setSendEmailTo(emailAddr);
    setSendEmailSubject('');
    setSendEmailBody('');
    try {
      const t = await api.getTemplates();
      setSendEmailTemplates(t.items || []);
    } catch {}
    setSendEmailOpen(true);
  }

  function applyTemplate(template: any) {
    const domainName = domain?.domain || '';
    const sub = (template.subject_template || '').replace(/\$domain/g, domainName);
    const body = (template.body_template || '').replace(/\$domain/g, domainName);
    setSendEmailSubject(sub);
    setSendEmailBody(body);
  }

  async function handleSendEmail() {
    if (!sendEmailTo || !sendEmailSubject.trim() || !sendEmailBody.trim()) {
      toast('Fill in all fields', 'error'); return;
    }
    setSendingEmail(true);
    try {
      await api.composeEmail(sendEmailTo, sendEmailSubject, sendEmailBody, id);
      toast(`Email sent to ${sendEmailTo}`);
      setSendEmailOpen(false);
      // Update domain status to contacted if it's still new/analyzed
      if (domain && ['new', 'analyzed'].includes(domain.status || '')) {
        await api.updateDomain(id!, { status: 'contacted' });
        load();
      }
    } catch (e: any) { toast(e.message || 'Send failed', 'error'); }
    setSendingEmail(false);
  }

  async function grabContacts(useBrowser = false) {
    setGrabbing(true); setGrabResult(null);
    try { 
      const r = await api.grabContacts(id!, useBrowser); 
      setGrabResult(r); 
      const methodLabel = r.method === 'browser' ? ' (Browser mode)' : '';
      toast(`Found ${r.emails?.length || 0} emails, ${r.forms?.length || 0} forms${methodLabel}`); 
      if (r._browser_error) {
        toast(`Browser warning: ${r._browser_error}`, 'error');
      }
      loadForms(); loadContacts(); load(); 
    }
    catch (e: any) { toast(e.message || 'Grab failed', 'error'); }
    setGrabbing(false);
  }
  async function previewSubmit(formId: string) {
    try { const r = await api.previewFormSubmission(id!, formId); setPreviewData(r); }
    catch (e: any) { toast(e.message, 'error'); }
  }
  async function doSubmitForm(formId: string, templateId?: string, hasCaptcha = false) {
    setSubmitting(formId);
    setSolvingStatus('');
    
    try {
      if (hasCaptcha) {
        setSolvingStatus('Detecting CAPTCHA...');
        await new Promise(resolve => setTimeout(resolve, 500));
        setSolvingStatus('Solving CAPTCHA...');
      }
      
      const r = await api.submitForm(id!, formId, templateId);
      
      if (hasCaptcha && r.captcha_solved) {
        setSolvingStatus('Submitting form...');
        await new Promise(resolve => setTimeout(resolve, 500));
      }
      
      if (r.success) {
        setSolvingStatus('Done!');
        toast(hasCaptcha ? 'Form submitted with CAPTCHA solved!' : 'Form submitted!');
      } else {
        toast(`Submit failed: ${r.error || 'Unknown error'}`, 'error');
      }
      
      setPreviewData(null);
      loadForms();
    } catch (e: any) {
      toast(e.message, 'error');
    }
    
    setSubmitting(null);
    setTimeout(() => setSolvingStatus(''), 2000);
  }
  function openPayEdit(pm: { id: string; method: string; details: Record<string, string> }) {
    setPayEditId(pm.id); setPayMethod(pm.method); setPayDetailsMap(pm.details || {}); setPayOpen(true);
  }
  async function savePayment(e: React.FormEvent) {
    e.preventDefault();
    if (!payMethod) { toast('Select method', 'error'); return; }
    const fields = payFields[payMethod] || [];
    for (const f of fields) { if (f.required && !payDetailsMap[f.key]?.trim()) { toast(`${f.label} is required`, 'error'); return; } }
    try {
      if (payEditId) { await api.updatePaymentMethod(id!, payEditId, { method: payMethod, details: payDetailsMap }); toast('Updated'); }
      else { await api.addPaymentMethod(id!, { method: payMethod, details: payDetailsMap }); toast('Added'); }
      setPayOpen(false); setPayEditId(null); setPayMethod(''); setPayDetailsMap({}); loadPayments();
    } catch (e: any) { toast(e.message, 'error'); }
  }
  async function setPreferred(pmId: string) { try { await api.setPreferredPayment(id!, pmId); toast('Updated'); loadPayments(); } catch (e: any) { toast(e.message, 'error'); } }
  async function delPayment(pmId: string) { try { await api.deletePaymentMethod(id!, pmId); toast('Deleted'); loadPayments(); } catch (e: any) { toast(e.message, 'error'); } }

  async function saveField(f: string, v: unknown) {
    try { await api.updateDomain(id!, { [f]: v }); toast(`Updated`); load(); } catch (e: any) { toast(e.message, 'error'); }
  }
  async function saveContact2() {
    try { await api.updateDomain(id!, { owner: contact.owner || null, email: contact.email || null, telegram: contact.telegram || null, language: contact.language || null }); toast('Saved'); setEditContact(false); load(); }
    catch (e: any) { toast(e.message, 'error'); }
  }
  async function saveNotes2() { await saveField('notes', notes || null); setEditNotes(false); }

  function catChange(v: string) { if (v === '__new__') { const n = prompt('New category:'); if (n) saveField('category', n); } else saveField('category', v || null); }

  function openPrice(p?: LinkPrice) {
    if (p) { setEditPriceId(p.id); setPf({ link_type: linkTypes.includes(p.link_type) ? p.link_type : '__new__', custom: linkTypes.includes(p.link_type) ? '' : p.link_type, price: p.price != null ? String(p.price) : '', currency: p.currency || 'USD', duration: String(p.duration_months || 12), permanent: p.is_permanent, notes: p.notes || '' }); }
    else { setEditPriceId(null); setPf({ link_type: '', custom: '', price: '', currency: 'USD', duration: '12', permanent: false, notes: '' }); }
    setPriceOpen(true);
  }

  async function savePrice(e: React.FormEvent) {
    e.preventDefault();
    const lt = pf.link_type === '__new__' ? pf.custom : pf.link_type;
    if (!lt) { toast('Select type', 'error'); return; }
    const payload = { domain_id: id!, link_type: lt, price: pf.price ? +pf.price : null, currency: pf.currency, duration_months: pf.permanent ? null : +pf.duration, is_permanent: pf.permanent, notes: pf.notes || null };
    try {
      if (editPriceId) { const { domain_id, ...u } = payload; await api.updateLinkPrice(editPriceId, u); }
      else { await api.createLinkPrice(payload); if (pf.link_type === '__new__' && pf.custom) { await api.addLinkType(pf.custom).catch(() => {}); loadTypes(); } }
      toast(editPriceId ? 'Updated' : 'Added'); setPriceOpen(false); load();
    } catch (e: any) { toast(e.message, 'error'); }
  }

  async function delPrice(pid: string) { if (!confirm('Delete?')) return; try { await api.deleteLinkPrice(pid); toast('Deleted'); load(); } catch (e: any) { toast(e.message, 'error'); } }
  async function addType() { if (!newType.trim()) return; try { await api.addLinkType(newType.trim()); toast('Added'); setNewType(''); loadTypes(); } catch (e: any) { toast(e.message, 'error'); } }
  async function delType(n: string) { if (!confirm(`Delete "${n}"?`)) return; try { await api.deleteLinkType(n); toast('Deleted'); loadTypes(); } catch (e: any) { toast(e.message, 'error'); } }

  if (!domain) return <div className="text-gray-500 py-8 text-center">Loading...</div>;
  const d = domain;
  const ic = "w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-pink-500 text-sm";

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link to="/domains" className="text-gray-400 hover:text-white flex items-center gap-1"><ArrowLeft className="w-4 h-4" /> Domains</Link>
        {editDomain ? (
          <form onSubmit={async (e) => { e.preventDefault(); const v = editDomainVal.trim().toLowerCase().replace(/^https?:\/\//, '').replace(/\/.*$/, ''); if (!v) return; try { await api.updateDomain(id!, { domain: v }); toast('Domain updated'); setEditDomain(false); load(); } catch (err: any) { toast(err.message, 'error'); } }} className="flex items-center gap-2">
            <input type="text" value={editDomainVal} onChange={e => setEditDomainVal(e.target.value)} autoFocus className="px-3 py-1 bg-gray-700 border border-gray-600 rounded-lg text-xl font-semibold font-mono focus:outline-none focus:border-pink-500" />
            <Button type="submit" variant="primary" size="sm">Save</Button>
            <Button size="sm" onClick={() => setEditDomain(false)}>Cancel</Button>
          </form>
        ) : (
          <h1 className="text-xl font-semibold tracking-tight font-mono cursor-pointer hover:text-pink-400 transition-colors" onClick={() => { setEditDomainVal(d.domain); setEditDomain(true); }} title="Click to edit">{d.domain}</h1>
        )}
        <a href={`https://${d.domain}`} target="_blank" rel="noopener" className="text-pink-400 hover:text-pink-300 flex items-center gap-1 text-sm"><ExternalLink className="w-4 h-4" /> Visit</a>
        <StatusPill tone={statusTone(d.status)}>{d.status.toUpperCase()}</StatusPill>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-lg font-semibold">Metrics</h2>
            <Button size="sm" onClick={analyzeDomain} disabled={analyzing}>
              <RefreshCw className={`w-4 h-4 ${analyzing ? 'animate-spin' : ''}`} aria-hidden /> {analyzing ? 'Updating...' : 'Update from Ahrefs'}
            </Button>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[['Domain Rating', d.domain_rating], ['Organic Traffic', d.organic_traffic?.toLocaleString()], ['Referring Domains', d.referring_domains?.toLocaleString()], ['Backlinks', d.backlinks_count?.toLocaleString()]].map(([l, v]) => (
              <div key={l as string} className="bg-gray-800 rounded-lg p-4 border border-gray-700"><div className="text-xs text-gray-400">{l}</div><div className="text-2xl font-semibold tabular-nums">{v ?? '-'}</div></div>
            ))}
          </div>

          {/* Contact */}
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold">Contact Info</h2>
              <div className="flex gap-2">
                <button
                  onClick={async () => {
                    try {
                      toast('Searching inbox...');
                      const res = await api.grabContact(id!);
                      if (res.saved) {
                        toast(`Found & saved: ${res.saved_email}`);
                        load();
                      } else if (res.found > 0) {
                        toast(`Found ${res.found} contacts but domain already has one`);
                      } else {
                        toast('No emails found for this domain', 'error');
                      }
                    } catch (e: any) { toast(e.message, 'error'); }
                  }}
                  className="inline-flex items-center justify-center gap-1.5 px-3 py-1 text-sm rounded-md bg-gray-700 hover:bg-gray-600 transition-colors disabled:opacity-50 disabled:pointer-events-none"
                >
                  <Search className="w-4 h-4" aria-hidden /> Inbox
                </button>
                <Button size="sm" icon={Pencil} onClick={() => setEditContact(!editContact)}>{editContact ? 'Cancel' : 'Edit'}</Button>
              </div>
            </div>
            {editContact ? (
              <div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                  <div className="relative"><label className="block text-xs text-gray-400 mb-1">Owner</label>
                    <input type="text" value={contact.owner} onChange={e => onOwnerInput(e.target.value)} onFocus={() => { if (ownerSuggestions.length) setShowSuggestions(true); }} onBlur={() => setTimeout(() => setShowSuggestions(false), 150)} autoComplete="off" className={ic} />
                    {showSuggestions && (
                      <div className="absolute z-50 left-0 right-0 mt-1 bg-gray-800 border border-gray-600 rounded-lg shadow-lg max-h-64 overflow-y-auto">
                        {ownerSuggestions.map((s, i) => (
                          <button key={i} type="button" onMouseDown={() => pickOwner(s)} className="w-full text-left px-3 py-2 hover:bg-gray-700 text-sm">
                            <div className="font-medium">{s.owner}</div>
                            {s.email && <div className="text-xs text-gray-400">{s.email}</div>}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="relative"><label className="block text-xs text-gray-400 mb-1">Email</label>
                    <input type="text" value={contact.email} onChange={e => onEmailInput(e.target.value)} onFocus={() => { if (ownerSuggestions.length) setShowSuggestions(true); }} onBlur={() => setTimeout(() => setShowSuggestions(false), 150)} autoComplete="off" className={ic} />
                    {showSuggestions && (
                      <div className="absolute z-50 left-0 right-0 mt-1 bg-gray-800 border border-gray-600 rounded-lg shadow-lg max-h-64 overflow-y-auto">
                        {ownerSuggestions.map((s, i) => (
                          <button key={i} type="button" onMouseDown={() => pickOwner(s)} className="w-full text-left px-3 py-2 hover:bg-gray-700 text-sm">
                            <div className="font-medium">{s.owner}</div>
                            {s.email && <div className="text-xs text-gray-400">{s.email}</div>}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                  <div><label className="block text-xs text-gray-400 mb-1">Telegram</label><input type="text" value={contact.telegram} onChange={e => setContact({ ...contact, telegram: e.target.value })} className={ic} /></div>
                  <div><label className="block text-xs text-gray-400 mb-1">Language</label><input type="text" value={contact.language} onChange={e => setContact({ ...contact, language: e.target.value })} placeholder="English" className={ic} /></div>
                </div>
                <Button variant="primary" onClick={saveContact2}>Save</Button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div><div className="text-xs text-gray-400 mb-1">Owner</div><div className="text-sm">{d.owner || '-'}</div></div>
                <div><div className="text-xs text-gray-400 mb-1">Email</div><div className="text-sm flex items-center gap-2">{d.email ? <><a href={`mailto:${d.email}`} className="text-pink-400 hover:underline">{d.email}</a><button onClick={() => openSendEmail(d.email!)} className="text-gray-400 hover:text-pink-400" title="Send email"><Send className="w-4 h-4" /></button></> : '-'}</div></div>
                <div><div className="text-xs text-gray-400 mb-1">Telegram</div><div className="text-sm">{d.telegram ? <a href={`https://t.me/${d.telegram.replace('@','')}`} target="_blank" className="text-pink-400 hover:underline">{d.telegram}</a> : '-'}</div></div>
                <div><div className="text-xs text-gray-400 mb-1">Language</div><div className="text-sm">{d.language || 'English'}</div></div>
              </div>
            )}
          </div>

          {/* Saved Contacts */}
          {savedContacts.length > 0 && (
            <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-lg font-semibold">Saved Contacts <span className="text-sm text-gray-400 font-normal">({savedContacts.length})</span></h2>
              </div>
              <div className="space-y-2">
                {savedContacts.map((c: any) => (
                  <div key={c.id} className={`p-3 rounded-lg border flex items-start justify-between gap-3 ${c.is_primary ? 'bg-pink-600/10 border-pink-600/30' : 'bg-gray-700/50 border-gray-600'}`}>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <a href={`mailto:${c.email}`} className="text-sm text-pink-400 hover:underline font-medium">{c.email}</a>
                        {c.is_primary && <span className="text-xs bg-yellow-600/30 text-yellow-400 px-1.5 py-0.5 rounded">Primary</span>}
                      </div>
                      {(c.name || c.role) && (
                        <div className="text-xs text-gray-400 mt-0.5">
                          {c.name}{c.name && c.role && ' · '}{c.role}
                        </div>
                      )}
                      {c.source_page && <div className="text-xs text-gray-500 mt-0.5 truncate">From: {c.source_page}</div>}
                      {(c.social_twitter || c.social_linkedin || c.social_telegram) && (
                        <div className="flex gap-2 mt-1">
                          {c.social_twitter && <a href={c.social_twitter} target="_blank" className="text-xs text-blue-400 hover:underline">🐦 Twitter</a>}
                          {c.social_linkedin && <a href={c.social_linkedin} target="_blank" className="text-xs text-blue-400 hover:underline">💼 LinkedIn</a>}
                          {c.social_telegram && <a href={c.social_telegram} target="_blank" className="text-xs text-blue-400 hover:underline">✈️ Telegram</a>}
                        </div>
                      )}
                    </div>
                    <div className="flex items-center gap-1 flex-shrink-0 mt-0.5">
                      <button onClick={() => openSendEmail(c.email)} className="text-gray-500 hover:text-pink-400" title="Send email">
                        <Send className="w-4 h-4" />
                      </button>
                      <button onClick={() => togglePrimary(c.id)} className={`${c.is_primary ? 'text-yellow-400' : 'text-gray-500 hover:text-yellow-400'}`} title={c.is_primary ? 'Primary contact' : 'Set as primary'}>
                        <Star className="w-4 h-4" fill={c.is_primary ? 'currentColor' : 'none'} />
                      </button>
                      <button onClick={() => deleteContact(c.id)} className="text-gray-500 hover:text-red-400" title="Remove contact">
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Contacts Grabber */}
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold">Contacts Grabber</h2>
              <div className="flex gap-2">
                <Button size="sm" onClick={() => grabContacts(false)} disabled={grabbing}>
                  <Search className={`w-4 h-4 ${grabbing ? 'animate-spin' : ''}`} aria-hidden /> {grabbing ? 'Grabbing...' : 'Grab Contacts'}
                </Button>
                <Button variant="primary" size="sm" onClick={() => grabContacts(true)} disabled={grabbing} title="Deep scraping with browser automation (slower but finds more)">
                  <Search className={`w-4 h-4 ${grabbing ? 'animate-spin' : ''}`} aria-hidden /> {grabbing ? 'Deep Grabbing...' : 'Deep Grab'}
                </Button>
              </div>
            </div>

            {grabResult && (
              <div className="space-y-3 mb-4">
                <div className="text-sm text-gray-400">
                  Found <span className="text-pink-400 font-medium">{grabResult.emails?.length || 0}</span> emails,{' '}
                  <span className="text-pink-400 font-medium">{grabResult.contacts_added || 0}</span> new contacts added,{' '}
                  <span className="text-pink-400 font-medium">{grabResult.forms_detected || 0}</span> forms detected
                  {grabResult.method && (
                    <span className={`ml-2 px-2 py-0.5 rounded text-xs ${grabResult.method === 'browser' ? 'bg-pink-600/15 text-pink-300' : 'bg-gray-700 text-gray-400'}`}>
                      {grabResult.method === 'browser' ? '🌐 Browser mode' : '📄 Static mode'}
                    </span>
                  )}
                </div>
                {grabResult.emails?.length > 0 && (
                  <div className="space-y-1">
                    <div className="flex items-center justify-between">
                      <div className="text-xs text-gray-500 font-medium">Emails:</div>
                      {grabResult.emails.filter((e: any) => !savedEmails.has(e.email?.toLowerCase()) && !e.already_saved && !dismissedEmails.has(e.email?.toLowerCase())).length > 0 && (
                        <Button variant="primary" size="xs" icon={Plus} onClick={saveAllGrabbedEmails}>Save All</Button>
                      )}
                    </div>
                    {grabResult.emails.filter((e: any) => !dismissedEmails.has(e.email?.toLowerCase())).map((e: any, i: number) => {
                      const alreadySaved = savedEmails.has(e.email?.toLowerCase()) || e.already_saved;
                      return (
                        <div key={i} className="text-sm flex items-center gap-2">
                          <span className="text-pink-400">{e.email}</span>
                          <span className="text-gray-500 text-xs">({e.source_type})</span>
                          {alreadySaved ? (
                            <span className="text-xs text-green-400">✓ Saved</span>
                          ) : (
                            <>
                              <Button variant="primary" size="xs" onClick={() => saveGrabbedEmail(e)} disabled={savingEmails.has(e.email)}>
                                {savingEmails.has(e.email) ? '...' : 'Save'}
                              </Button>
                              <Button size="xs" onClick={() => setDismissedEmails(prev => new Set(prev).add(e.email.toLowerCase()))}>
                                Dismiss
                              </Button>
                            </>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
                {(grabResult.socials?.twitter?.length > 0 || grabResult.socials?.linkedin?.length > 0 || grabResult.socials?.telegram?.length > 0) && (
                  <div className="space-y-1">
                    <div className="text-xs text-gray-500 font-medium">Socials:</div>
                    {grabResult.socials.twitter?.map((u: string, i: number) => <a key={i} href={u} target="_blank" className="text-sm text-blue-400 hover:underline block">🐦 {u}</a>)}
                    {grabResult.socials.linkedin?.map((u: string, i: number) => <a key={i} href={u} target="_blank" className="text-sm text-blue-400 hover:underline block">💼 {u}</a>)}
                    {grabResult.socials.telegram?.map((u: string, i: number) => <a key={i} href={u} target="_blank" className="text-sm text-blue-400 hover:underline block">✈️ {u}</a>)}
                  </div>
                )}
              </div>
            )}

            {/* Detected Forms */}
            {forms.length > 0 && (
              <div>
                <div className="text-xs text-gray-500 font-medium mb-2">Detected Forms:</div>
                <div className="space-y-2">
                  {forms.map((f: any) => (
                    <div key={f.id} className="p-3 bg-gray-700/50 rounded-lg border border-gray-600">
                      <div className="flex justify-between items-start mb-2">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <a href={f.form_url} target="_blank" className="text-sm text-pink-400 hover:underline">{f.form_url}</a>
                            {f.has_captcha && (
                              <span className="px-2 py-0.5 bg-yellow-900/50 border border-yellow-700 rounded text-xs text-yellow-400 flex items-center gap-1">
                                <ShieldAlert className="w-4 h-4" aria-hidden /> CAPTCHA ({f.captcha_type?.replace('_', ' ')})
                              </span>
                            )}
                          </div>
                          <div className="text-xs text-gray-500">{f.form_method} → {f.form_action}</div>
                        </div>
                        <div className="flex gap-1 items-center">
                          {submitting === f.id && solvingStatus ? (
                            <span className="px-2 py-1 bg-yellow-600/50 border border-yellow-500 rounded text-xs text-yellow-300 flex items-center gap-1">
                              <RefreshCw className="w-3 h-3 animate-spin" /> {solvingStatus}
                            </span>
                          ) : (
                            <>
                              <Button size="xs" icon={Eye} onClick={() => previewSubmit(f.id)}>Preview</Button>
                              <Button
                                variant="primary"
                                size="xs"
                                icon={Send}
                                onClick={() => doSubmitForm(f.id, undefined, f.has_captcha)}
                                disabled={submitting === f.id}
                              >
                                {f.has_captcha ? (submitting === f.id ? 'Solving...' : 'Solve & Submit') : (submitting === f.id ? 'Sending...' : 'Submit')}
                              </Button>
                            </>
                          )}
                        </div>
                      </div>
                      {f.fields_json && (
                        <div className="flex flex-wrap gap-1">
                          {f.fields_json.map((field: any, i: number) => (
                            <span key={i} className="px-1.5 py-0.5 bg-gray-600 rounded text-xs text-gray-300">
                              {field.label || field.name}{field.required && <span className="text-pink-400">*</span>}
                            </span>
                          ))}
                        </div>
                      )}
                      {f.last_submitted_at && (
                        <div className="text-xs text-gray-500 mt-1">
                          Last submitted: {new Date(f.last_submitted_at).toLocaleString()} — 
                          <span className={f.submission_status === 'success' ? 'text-green-400' : 'text-red-400'}> {f.submission_status}</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {!grabResult && forms.length === 0 && (
              <p className="text-gray-500 text-sm">Click "Grab Contacts" to scan this domain for emails, socials, and contact forms.</p>
            )}
          </div>

          {/* Preview Modal */}
          {previewData && (
            <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={() => setPreviewData(null)}>
              <div className="bg-gray-800 rounded-lg p-6 border border-gray-700 max-w-lg w-full max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
                <div className="flex justify-between items-center mb-4">
                  <h3 className="text-lg font-semibold">Form Submission Preview</h3>
                  <button onClick={() => setPreviewData(null)} aria-label="Close preview" className="text-gray-400 hover:text-white"><X className="w-5 h-5" /></button>
                </div>
                <div className="space-y-3 text-sm">
                  <div><span className="text-gray-400">Template:</span> <span className="text-pink-400">{previewData.template_name}</span></div>
                  <div><span className="text-gray-400">Form:</span> <span className="text-gray-300">{previewData.form_action}</span></div>
                  <div><span className="text-gray-400">Method:</span> <span className="text-gray-300">{previewData.form_method}</span></div>
                  {previewData.subject && (
                    <div className="border-t border-gray-700 pt-3">
                      <div className="text-gray-400 mb-1">Subject:</div>
                      <div className="text-gray-300 bg-gray-700/50 rounded p-2 text-xs">{previewData.subject}</div>
                    </div>
                  )}
                  {previewData.body && (
                    <div className="mt-2">
                      <div className="text-gray-400 mb-1">Message:</div>
                      <div className="text-gray-300 whitespace-pre-wrap bg-gray-700/50 rounded p-2 text-xs">{previewData.body}</div>
                    </div>
                  )}
                  <div className="border-t border-gray-700 pt-3">
                    <div className="text-gray-400 mb-2">Form fields to be sent:</div>
                    {Object.entries(previewData.form_data || {}).map(([k, v]) => (
                      <div key={k} className="mb-2">
                        <span className="text-gray-500">{k}:</span>
                        <div className="text-gray-300 whitespace-pre-wrap bg-gray-700/50 rounded p-2 mt-0.5 text-xs">{v as string || '(empty)'}</div>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="flex gap-2 mt-4">
                  <Button variant="primary" onClick={() => doSubmitForm(previewData.form_id, previewData.template_id)} disabled={submitting !== null}>
                    {submitting ? 'Submitting...' : 'Confirm & Submit'}
                  </Button>
                  <Button onClick={() => setPreviewData(null)}>Cancel</Button>
                </div>
              </div>
            </div>
          )}

          {/* Publisher Rules */}
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold">Publisher Rules</h2>
              <div className="flex gap-2">
                <button
                  onClick={async () => {
                    try {
                      toast('Scanning emails for rules...');
                      const res = await api.grabPublisherRules(id!);
                      toast('Rules extracted from emails!');
                      loadPublisherRules();
                    } catch (e: any) { toast(e.message || 'Failed to grab rules', 'error'); }
                  }}
                  className="inline-flex items-center justify-center gap-1.5 px-3 py-1 text-sm rounded-md bg-gray-700 hover:bg-gray-600 transition-colors disabled:opacity-50 disabled:pointer-events-none"
                >
                  <Sparkles className="w-4 h-4" aria-hidden />
                  Grab Rules
                </button>
                <Button size="sm" icon={Pencil} onClick={() => setEditRules(!editRules)}>
                  {editRules ? 'Cancel' : 'Edit'}
                </Button>
              </div>
            </div>

            {editRules ? (
              <form onSubmit={savePublisherRules} className="space-y-4">
                {/* Row 1: URLs & Words */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Max URLs</label>
                    <input
                      type="number"
                      value={rulesForm.max_urls}
                      onChange={(e) => setRulesForm({ ...rulesForm, max_urls: e.target.value })}
                      placeholder="e.g. 2"
                      className={ic}
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Min Words</label>
                    <input
                      type="number"
                      value={rulesForm.min_words}
                      onChange={(e) => setRulesForm({ ...rulesForm, min_words: e.target.value })}
                      placeholder="e.g. 500"
                      className={ic}
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Max Words</label>
                    <input
                      type="number"
                      value={rulesForm.max_words}
                      onChange={(e) => setRulesForm({ ...rulesForm, max_words: e.target.value })}
                      placeholder="e.g. 1200"
                      className={ic}
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Link Attribute</label>
                    <select
                      value={rulesForm.link_attribute}
                      onChange={(e) => setRulesForm({ ...rulesForm, link_attribute: e.target.value })}
                      className={ic}
                    >
                      <option value="">Not specified</option>
                      <option value="dofollow">Dofollow</option>
                      <option value="nofollow">Nofollow</option>
                      <option value="sponsored">Sponsored</option>
                    </select>
                  </div>
                </div>

                {/* Row 2: Images & Resource Links */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Image Count</label>
                    <input
                      type="number"
                      value={rulesForm.image_count}
                      onChange={(e) => setRulesForm({ ...rulesForm, image_count: e.target.value })}
                      placeholder="e.g. 2"
                      className={ic}
                    />
                    <p className="text-xs text-gray-500 mt-1">Required images</p>
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Max Images</label>
                    <input
                      type="number"
                      value={rulesForm.max_images}
                      onChange={(e) => setRulesForm({ ...rulesForm, max_images: e.target.value })}
                      placeholder="e.g. 5"
                      className={ic}
                    />
                    <p className="text-xs text-gray-500 mt-1">Upper limit</p>
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Resource Links</label>
                    <input
                      type="number"
                      value={rulesForm.resource_links_count}
                      onChange={(e) => setRulesForm({ ...rulesForm, resource_links_count: e.target.value })}
                      placeholder="e.g. 3"
                      className={ic}
                    />
                    <p className="text-xs text-gray-500 mt-1">Authority outbound links</p>
                  </div>
                  <div className="flex items-end pb-1">
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={rulesForm.skip_resource_links === true}
                        onChange={(e) =>
                          setRulesForm({ ...rulesForm, skip_resource_links: e.target.checked ? true : null })
                        }
                      />
                      <span className="text-gray-300">No Outbound Links</span>
                    </label>
                  </div>
                </div>

                {/* Row 3: Flags */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={rulesForm.cross_domain === true}
                        onChange={(e) =>
                          setRulesForm({ ...rulesForm, cross_domain: e.target.checked ? true : null })
                        }
                      />
                      <span className="text-gray-300">Allow Cross-Domain Links</span>
                    </label>
                    <p className="text-xs text-gray-500 mt-1 ml-6">
                      Can link to different domains in the same article
                    </p>
                  </div>
                  <div>
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={rulesForm.we_write === true}
                        onChange={(e) =>
                          setRulesForm({ ...rulesForm, we_write: e.target.checked ? true : null })
                        }
                      />
                      <span className="text-gray-300">We Write Content</span>
                    </label>
                    <p className="text-xs text-gray-500 mt-1 ml-6">
                      We provide the article content
                    </p>
                  </div>
                </div>

                {/* Row 4: Brand Mention Rules */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Brand Scope</label>
                    <select
                      value={rulesForm.brand_mentions_scope}
                      onChange={(e) => setRulesForm({ ...rulesForm, brand_mentions_scope: e.target.value })}
                      className={ic}
                    >
                      <option value="">Not specified</option>
                      <option value="any">Any linked brand</option>
                      <option value="all">All linked brands</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Body Mentions</label>
                    <input
                      type="number"
                      value={rulesForm.brand_mentions_body_count}
                      onChange={(e) => setRulesForm({ ...rulesForm, brand_mentions_body_count: e.target.value })}
                      placeholder="e.g. 2"
                      className={ic}
                    />
                    <p className="text-xs text-gray-500 mt-1">Per required brand</p>
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Specific Brands</label>
                    <input
                      type="text"
                      value={rulesForm.brand_mentions_brands}
                      onChange={(e) => setRulesForm({ ...rulesForm, brand_mentions_brands: e.target.value })}
                      placeholder="CamHours, WebcamChamps"
                      className={ic}
                    />
                    <p className="text-xs text-gray-500 mt-1">Comma-separated. Overrides scope.</p>
                  </div>
                  <div className="flex items-end pb-1">
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={rulesForm.brand_mentions_in_title === true}
                        onChange={(e) =>
                          setRulesForm({ ...rulesForm, brand_mentions_in_title: e.target.checked ? true : null })
                        }
                      />
                      <span className="text-gray-300">Brand in Title</span>
                    </label>
                  </div>
                </div>

                {/* Row 5: Text areas */}
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Content Guidelines</label>
                  <textarea
                    value={rulesForm.content_guidelines}
                    onChange={(e) => setRulesForm({ ...rulesForm, content_guidelines: e.target.value })}
                    rows={3}
                    placeholder="Any content restrictions or requirements..."
                    className={ic}
                  />
                </div>

                <div>
                  <label className="block text-xs text-gray-400 mb-1">Placement Notes</label>
                  <textarea
                    value={rulesForm.placement_notes}
                    onChange={(e) => setRulesForm({ ...rulesForm, placement_notes: e.target.value })}
                    rows={2}
                    placeholder="Notes about link placement..."
                    className={ic}
                  />
                </div>

                <Button type="submit" variant="primary">Save Rules</Button>
              </form>
            ) : publisherRules ? (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                <div>
                  <div className="text-xs text-gray-400 mb-1">Max URLs</div>
                  <div className="text-gray-200">{publisherRules.max_urls || '—'}</div>
                </div>
                <div>
                  <div className="text-xs text-gray-400 mb-1">Min Words</div>
                  <div className="text-gray-200">{publisherRules.min_words || '—'}</div>
                </div>
                <div>
                  <div className="text-xs text-gray-400 mb-1">Max Words</div>
                  <div className="text-gray-200">{publisherRules.max_words || '—'}</div>
                </div>
                <div>
                  <div className="text-xs text-gray-400 mb-1">Link Attribute</div>
                  <div className="text-gray-200">
                    {publisherRules.link_attribute
                      ? <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                          publisherRules.link_attribute === 'dofollow' ? 'bg-green-600/30 text-green-400' :
                          publisherRules.link_attribute === 'nofollow' ? 'bg-red-600/30 text-red-400' :
                          'bg-yellow-600/30 text-yellow-400'
                        }`}>{publisherRules.link_attribute}</span>
                      : '—'}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-400 mb-1">Images</div>
                  <div className="text-gray-200">
                    {publisherRules.image_count || '—'}
                    {publisherRules.max_images ? ` (max ${publisherRules.max_images})` : ''}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-400 mb-1">Resource Links</div>
                  <div className="text-gray-200">
                    {publisherRules.skip_resource_links
                      ? <span className="text-red-400">✗ Not allowed</span>
                      : publisherRules.resource_links_count || '—'}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-400 mb-1">Cross-Domain</div>
                  <div className="text-gray-200">
                    {publisherRules.cross_domain === null
                      ? '—'
                      : publisherRules.cross_domain
                      ? '✓ Allowed'
                      : '✗ No'}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-400 mb-1">We Write</div>
                  <div className="text-gray-200">
                    {publisherRules.we_write === null
                      ? '—'
                      : publisherRules.we_write
                      ? '✓ Yes'
                      : '✗ No'}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-400 mb-1">Brand Scope</div>
                  <div className="text-gray-200">{publisherRules.brand_mentions_scope || '—'}</div>
                </div>
                <div>
                  <div className="text-xs text-gray-400 mb-1">Brand Mentions</div>
                  <div className="text-gray-200">{publisherRules.brand_mentions_body_count || '—'}</div>
                </div>
                <div>
                  <div className="text-xs text-gray-400 mb-1">Specific Brands</div>
                  <div className="text-gray-200">{publisherRules.brand_mentions_brands || '—'}</div>
                </div>
                <div>
                  <div className="text-xs text-gray-400 mb-1">Brand in Title</div>
                  <div className="text-gray-200">
                    {publisherRules.brand_mentions_in_title === null
                      ? '—'
                      : publisherRules.brand_mentions_in_title
                      ? '✓ Yes'
                      : '✗ No'}
                  </div>
                </div>
                {publisherRules.content_guidelines && (
                  <div className="col-span-2 md:col-span-4">
                    <div className="text-xs text-gray-400 mb-1">Content Guidelines</div>
                    <div className="text-gray-200 whitespace-pre-wrap bg-gray-700/50 rounded p-3 text-xs">
                      {publisherRules.content_guidelines}
                    </div>
                  </div>
                )}
                {publisherRules.placement_notes && (
                  <div className="col-span-2 md:col-span-4">
                    <div className="text-xs text-gray-400 mb-1">Placement Notes</div>
                    <div className="text-gray-200 whitespace-pre-wrap bg-gray-700/50 rounded p-3 text-xs">
                      {publisherRules.placement_notes}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-gray-500 text-sm">
                No publisher rules set.{' '}
                <button
                  onClick={() => setEditRules(true)}
                  className="text-pink-400 hover:underline"
                >
                  Add rules
                </button>
              </p>
            )}
          </div>

          {/* Prices */}
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold">Link Prices</h2>
              <div className="flex gap-2">
                <Button size="sm" icon={Settings} onClick={() => setTypesModal(true)}>Types</Button>
                <Button variant="primary" size="sm" icon={Plus} onClick={() => openPrice()}>Add</Button>
              </div>
            </div>
            {priceOpen && (
              <form onSubmit={savePrice} className="mb-4 p-4 bg-gray-700/50 rounded-lg border border-gray-600">
                <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-3">
                  <div><label className="block text-xs text-gray-400 mb-1">Type</label>
                    <select value={pf.link_type} onChange={e => setPf({ ...pf, link_type: e.target.value })} className={ic}><option value="">Select...</option>{linkTypes.map(t => <option key={t}>{t}</option>)}<option value="__new__">+ New</option></select>
                    {pf.link_type === '__new__' && <input type="text" value={pf.custom} onChange={e => setPf({ ...pf, custom: e.target.value })} placeholder="Custom type" className={`${ic} mt-1`} />}
                  </div>
                  <div><label className="block text-xs text-gray-400 mb-1">Price</label>
                    <div className="flex gap-1"><input type="number" step="0.01" value={pf.price} onChange={e => setPf({ ...pf, price: e.target.value })} className={`flex-1 ${ic}`} />
                    <select value={pf.currency} onChange={e => setPf({ ...pf, currency: e.target.value })} className="w-20 px-2 py-2 bg-gray-700 border border-gray-600 rounded-lg text-sm"><option>USD</option><option>EUR</option><option>GBP</option></select></div>
                  </div>
                  <div><label className="block text-xs text-gray-400 mb-1">Duration</label>
                    <select value={pf.duration} onChange={e => setPf({ ...pf, duration: e.target.value })} disabled={pf.permanent} className={ic}><option value="1">1mo</option><option value="3">3mo</option><option value="6">6mo</option><option value="12">12mo</option></select></div>
                  <div><label className="block text-xs text-gray-400 mb-1">&nbsp;</label>
                    <label className="flex items-center gap-2 px-3 py-2"><input type="checkbox" checked={pf.permanent} onChange={e => setPf({ ...pf, permanent: e.target.checked })} /><span className="text-sm">Permanent</span></label></div>
                </div>
                <input type="text" value={pf.notes} onChange={e => setPf({ ...pf, notes: e.target.value })} placeholder="Notes..." className={`${ic} mb-3`} />
                <div className="flex gap-2">
                  <Button type="submit" variant="primary">Save</Button>
                  <Button onClick={() => setPriceOpen(false)}>Cancel</Button>
                </div>
              </form>
            )}
            {!d.link_prices?.length ? <p className="text-gray-500 text-sm">No prices yet</p> : (
              <table className="w-full table-fixed"><thead><tr className="text-xs text-gray-400 border-b border-gray-700"><th className="py-2 text-left w-20">Type</th><th className="py-2 text-left w-20">Price</th><th className="py-2 text-left w-24">Duration</th><th className="py-2 text-left">Notes</th><th className="py-2 w-16"></th></tr></thead>
              <tbody>{d.link_prices.map(p => (
                <tr key={p.id} className="border-b border-gray-700/50 text-sm align-top">
                  <td className="py-2 font-medium">{p.link_type}</td>
                  <td className="py-2">{p.price != null ? `${p.price} ${p.currency}` : '-'}</td>
                  <td className="py-2">{p.is_permanent ? <span className="text-green-400">Permanent</span> : p.duration_months ? `${p.duration_months}mo` : '-'}</td>
                  <td className="py-2 text-gray-400 text-xs break-words">{p.notes || ''}</td>
                  <td className="py-2 text-right"><div className="flex gap-2 justify-end"><button onClick={() => openPrice(p)} aria-label="Edit price" className="text-gray-400 hover:text-white"><Pencil className="w-4 h-4" /></button><button onClick={() => delPrice(p.id)} aria-label="Delete price" className="text-red-400 hover:text-red-300"><Trash2 className="w-4 h-4" /></button></div></td>
                </tr>
              ))}</tbody></table>
            )}
          </div>

          {/* Payment Methods */}
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold">Payment Methods</h2>
              <Button variant="primary" size="sm" icon={Plus} onClick={() => { setPayEditId(null); setPayMethod(''); setPayDetailsMap({}); setPayOpen(!payOpen); }}>Add</Button>
            </div>
            {payOpen && (
              <form onSubmit={savePayment} className="mb-4 p-4 bg-gray-700/50 rounded-lg border border-gray-600">
                <div className="mb-3"><label className="block text-xs text-gray-400 mb-1">Method</label>
                  <select value={payMethod} onChange={e => { setPayMethod(e.target.value); setPayDetailsMap({}); }} disabled={!!payEditId} className={ic}><option value="">Select...</option>{availablePay.map(m => <option key={m}>{m}</option>)}</select></div>
                {payMethod && payFields[payMethod] && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
                    {payFields[payMethod].map((f: any) => (
                      <div key={f.key}><label className="block text-xs text-gray-400 mb-1">{f.label}{f.required && <span className="text-pink-400"> *</span>}</label>
                        {f.type === 'select' ? (
                          <select value={payDetailsMap[f.key] || ''} onChange={e => setPayDetailsMap(prev => ({ ...prev, [f.key]: e.target.value }))} className={ic}>
                            <option value="">Select...</option>{(f.options as string[]).map((o: string) => <option key={o}>{o}</option>)}
                          </select>
                        ) : (
                          <input type="text" value={payDetailsMap[f.key] || ''} onChange={e => setPayDetailsMap(prev => ({ ...prev, [f.key]: e.target.value }))} className={ic} />
                        )}</div>
                    ))}
                  </div>
                )}
                <div className="flex gap-2">
                  <Button type="submit" variant="primary">Save</Button>
                  <Button onClick={() => { setPayOpen(false); setPayEditId(null); setPayMethod(''); setPayDetailsMap({}); }}>Cancel</Button>
                </div>
              </form>
            )}
            {!payMethods.length ? <p className="text-gray-500 text-sm">No payment methods yet</p> : (
              <div className="space-y-2">{payMethods.map(pm => {
                const fields = payFields[pm.method] || [];
                const details = pm.details || {};
                return (
                <div key={pm.id} className={`p-3 rounded-lg border ${pm.is_preferred ? 'bg-pink-600/10 border-pink-600/30' : 'bg-gray-700/50 border-gray-600'}`}>
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">{pm.method}</span>
                      {pm.is_preferred && <span className="text-xs text-pink-400 flex items-center gap-1"><Star className="w-3 h-3" /> Preferred</span>}
                    </div>
                    <div className="flex gap-2">
                      <button onClick={() => openPayEdit(pm)} className="text-gray-400 hover:text-white" title="Edit"><Pencil className="w-4 h-4" /></button>
                      {!pm.is_preferred && <button onClick={() => setPreferred(pm.id)} className="text-gray-400 hover:text-pink-400" title="Set as preferred"><Star className="w-4 h-4" /></button>}
                      <button onClick={() => delPayment(pm.id)} aria-label="Delete payment method" className="text-red-400 hover:text-red-300"><Trash2 className="w-4 h-4" /></button>
                    </div>
                  </div>
                  {fields.length > 0 && Object.keys(details).length > 0 && (
                    <div className="grid grid-cols-2 gap-x-4 gap-y-1 mt-2">
                      {fields.map(f => details[f.key] ? (
                        <div key={f.key}><span className="text-xs text-gray-500">{f.label}:</span> <span className="text-xs text-gray-300">{details[f.key]}</span></div>
                      ) : null)}
                    </div>
                  )}
                </div>
              );})}</div>
            )}
          </div>

          {/* Notes */}
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold">Notes</h2>
              {!editNotes && <Button size="sm" icon={Pencil} onClick={() => setEditNotes(true)}>Edit</Button>}
            </div>
            {editNotes ? (
              <div><textarea value={notes} onChange={e => setNotes(e.target.value)} rows={4} className={`${ic} mb-2`} />
              <div className="flex gap-2"><Button variant="primary" onClick={saveNotes2}>Save</Button><Button onClick={() => { setEditNotes(false); setNotes(d.notes || ''); }}>Cancel</Button></div></div>
            ) : <p className="text-sm text-gray-300 whitespace-pre-wrap">{d.notes || '-'}</p>}
          </div>
        </div>

        <div className="space-y-6">
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <h2 className="text-lg font-semibold mb-4">Classification</h2>
            <div className="space-y-3">
              <div><label className="block text-xs text-gray-400 mb-1">Status</label><select value={d.status} onChange={e => saveField('status', e.target.value)} className={ic}>{DOMAIN_STATUSES.map(s => <option key={s}>{s}</option>)}</select></div>
              <div><label className="block text-xs text-gray-400 mb-1">Category</label><select value={d.category || ''} onChange={e => catChange(e.target.value)} className={ic}><option value="">None</option>{categories.map(c => <option key={c}>{c}</option>)}<option value="__new__">+ New</option></select></div>
              <div><label className="block text-xs text-gray-400 mb-1">Tags</label><input type="text" defaultValue={d.tags || ''} onBlur={e => saveField('tags', e.target.value || null)} className={ic} /></div>
              <div className="flex gap-4">
                <label className="flex items-center gap-2"><input type="checkbox" checked={d.is_competitor} onChange={e => saveField('is_competitor', e.target.checked)} /><span className="text-sm">Competitor</span></label>
                <label className="flex items-center gap-2"><input type="checkbox" checked={d.is_adult} onChange={e => saveField('is_adult', e.target.checked)} /><span className="text-sm">Adult</span></label>
              </div>
            </div>
          </div>
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <h2 className="text-lg font-semibold mb-4">Backlinks</h2>
            {!d.backlinks?.length ? <p className="text-gray-500 text-sm">No backlinks</p> : (
              <div className="space-y-3">{d.backlinks.map((bl: any, i: number) => (
                <div key={i} className="p-3 bg-gray-700/50 rounded-lg">
                  <div className="text-xs text-gray-400">→ <span className="text-pink-400">{bl.target_domain}</span></div>
                  <a href={bl.source_url} target="_blank" rel="noopener" className="text-pink-400 hover:underline text-xs break-all block mt-1">{bl.source_url}</a>
                  {bl.anchor_text && <div className="text-xs text-gray-500 mt-0.5">Anchor: {bl.anchor_text}</div>}
                </div>
              ))}</div>
            )}
          </div>
        </div>
      </div>

      {/* Send Email Modal */}
      <Modal open={sendEmailOpen} onClose={() => setSendEmailOpen(false)} title={`Send Email to ${sendEmailTo}`} maxWidth="max-w-lg">
        <div className="space-y-4">
          {sendEmailTemplates.length > 0 && (
            <div>
              <label className="block text-xs text-gray-400 mb-2">Use Template</label>
              <div className="flex flex-wrap gap-2">
                {sendEmailTemplates.map((t: any) => (
                  <Button key={t.id} size="xs" onClick={() => applyTemplate(t)}>{t.name}</Button>
                ))}
              </div>
            </div>
          )}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Subject</label>
            <input type="text" value={sendEmailSubject} onChange={e => setSendEmailSubject(e.target.value)} className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-sm focus:outline-none focus:border-pink-500" />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Body</label>
            <textarea value={sendEmailBody} onChange={e => setSendEmailBody(e.target.value)} rows={8} className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-sm focus:outline-none focus:border-pink-500 resize-none" />
          </div>
          <div className="flex justify-end gap-2">
            <Button onClick={() => setSendEmailOpen(false)}>Cancel</Button>
            <Button variant="primary" icon={Send} onClick={handleSendEmail} disabled={sendingEmail || !sendEmailSubject.trim() || !sendEmailBody.trim()}>
              {sendingEmail ? 'Sending...' : 'Send'}
            </Button>
          </div>
        </div>
      </Modal>

      <Modal open={typesModal} onClose={() => setTypesModal(false)} title="Link Types" maxWidth="max-w-md">
        <div className="space-y-2 mb-4 max-h-64 overflow-y-auto">
          {!linkTypes.length ? <p className="text-gray-500 text-sm">None yet</p> : linkTypes.map(t => (
            <div key={t} className="flex items-center gap-2 p-2 bg-gray-700/50 rounded-lg"><span className="flex-1 text-sm">{t}</span><button onClick={() => delType(t)} aria-label={`Delete link type ${t}`} className="text-red-400 hover:text-red-300"><X className="w-4 h-4" /></button></div>
          ))}
        </div>
        <div className="flex gap-2">
          <input type="text" value={newType} onChange={e => setNewType(e.target.value)} onKeyDown={e => e.key === 'Enter' && addType()} placeholder="New type..." className="flex-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-sm focus:outline-none focus:border-pink-500" />
          <Button variant="primary" onClick={addType}>Add</Button>
        </div>
      </Modal>
    </div>
  );
}
