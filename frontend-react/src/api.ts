import type { DomainListResponse, Domain, Competitor, LinkPrice } from './types';

const B = '/api/v1';

function authHeaders(): Record<string, string> {
  const t = localStorage.getItem('token');
  return t ? { Authorization: `Bearer ${t}` } : {};
}

const J = (body: unknown): RequestInit => ({ method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify(body) });

function formatApiDetail(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map(item => {
      if (!item || typeof item !== 'object') return String(item);
      const record = item as Record<string, unknown>;
      const loc = Array.isArray(record.loc) ? record.loc.join('.') : '';
      const msg = typeof record.msg === 'string' ? record.msg : JSON.stringify(record);
      return loc ? `${loc}: ${msg}` : msg;
    }).join('; ');
  }
  if (detail && typeof detail === 'object') {
    const record = detail as Record<string, unknown>;
    if (typeof record.message === 'string') return record.message;
    if (typeof record.error === 'string') return record.error;
    return JSON.stringify(record);
  }
  return '';
}

async function req<T>(url: string, o?: RequestInit): Promise<T> {
  const headers = { ...authHeaders(), ...(o?.headers || {}) };
  const r = await fetch(url, { ...o, headers });
  if (r.status === 401) { localStorage.removeItem('token'); localStorage.removeItem('refresh_token'); window.location.href = '/login'; throw new Error('Unauthorized'); }
  if (!r.ok) { const e = await r.json().catch(() => ({ detail: r.statusText })); throw new Error(formatApiDetail(e.detail) || `${r.status}`); }
  if (r.status === 204) return undefined as T;
  return r.json();
}

export const api = {
  getDomains: (p = 1, pp = 10000) => req<DomainListResponse>(`${B}/domains?page=${p}&per_page=${pp}`),
  getDomain: (id: string) => req<Domain>(`${B}/domains/${id}`),
  createDomain: (d: Record<string, unknown>) => req<Domain>(`${B}/domains`, J(d)),
  updateDomain: (id: string, d: Record<string, unknown>) => req<Domain>(`${B}/domains/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(d) }),
  deleteDomain: (id: string) => req<void>(`${B}/domains/${id}`, { method: 'DELETE' }),
  bulkDeleteDomains: (ids: string[]) => req<{ deleted: number }>(`${B}/domains/bulk-delete`, J({ ids })),
  bulkUpdateDomains: (ids: string[], category?: string | null, tags?: string | null) => req<{ updated: number }>(`${B}/domains/bulk-update`, J({ ids, category, tags })),
  bulkImportDomains: (domains: string[], is_competitor = false) => req<{ added: number; skipped: number; skipped_domains: string[] }>(`${B}/domains/bulk-import`, J({ domains, is_competitor })),
  analyzeDomain: (id: string) => req<{ success: boolean; domain: Record<string, unknown>; metrics: Record<string, unknown> }>(`${B}/domains/${id}/analyze`, { method: 'POST', signal: AbortSignal.timeout(60000) }),
  saveMetrics: (id: string, metrics: Record<string, unknown>) => req<{ success: boolean }>(`${B}/domains/${id}/save-metrics`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(metrics) }),
  checkMetrics: (domain: string) => req<{ success: boolean; metrics: { domain: string; domain_rating: number | null; ahrefs_rank: number | null; organic_traffic: number | null; organic_keywords: number | null; referring_domains: number | null; backlinks_count: number | null } }>(`${B}/domains/check-metrics?domain=${encodeURIComponent(domain)}`, { method: 'POST', signal: AbortSignal.timeout(60000) }),
  getCategories: () => req<{ categories: string[]; predefined: string[] }>(`${B}/domains/categories/list`),
  getTags: () => req<{ tags: string[]; predefined: string[] }>(`${B}/domains/tags/list`),
  savePresetCategories: (c: string[]) => req<{ saved: number }>(`${B}/domains/presets/categories`, J(c)),
  savePresetTags: (t: string[]) => req<{ saved: number }>(`${B}/domains/presets/tags`, J(t)),
  getCompetitors: () => req<{ items: Competitor[] }>(`${B}/domains/competitors/list`),
  fetchBacklinks: (domain: string, limit = 100) => req<{ success: boolean; total_fetched: number; unique_domains: number; domains_added: number; backlinks_added: number }>(`${B}/backlinks/fetch/${encodeURIComponent(domain)}?limit=${limit}`, { method: 'POST' }),
  removeCompetitor: (domain: string, deleteBacklinks = true, deleteDomains = false) => req<{ competitor: string; backlinks_deleted: number; domains_deleted: number }>(`${B}/domains/competitors/${encodeURIComponent(domain)}?delete_backlinks=${deleteBacklinks}&delete_domains=${deleteDomains}`, { method: 'DELETE' }),
  importAhrefsCsv: (file: File, comp: string) => { const f = new FormData(); f.append('file', file); f.append('competitor_domain', comp); return req<{ success: boolean; domains_added: number; backlinks_added: number; skipped: number }>(`${B}/import/ahrefs-backlinks`, { method: 'POST', body: f }); },
  importDomainsCsv: (file: File, filters?: { min_traffic?: number; max_traffic?: number; min_dr?: number; max_dr?: number; skip_non_adult?: boolean }) => { const f = new FormData(); f.append('file', file); if (filters?.min_traffic) f.append('min_traffic', String(filters.min_traffic)); if (filters?.max_traffic) f.append('max_traffic', String(filters.max_traffic)); if (filters?.min_dr) f.append('min_dr', String(filters.min_dr)); if (filters?.max_dr) f.append('max_dr', String(filters.max_dr)); if (filters?.skip_non_adult) f.append('skip_non_adult', 'true'); return req<{ success: boolean; added: number; skipped: number; total_rows: number; filtered_out: number; adult_scan?: { fetched: number; resolved: number; deferred: number }; domains: string[] }>(`${B}/import/domains-csv`, { method: 'POST', body: f }); },
  getLinkTypes: () => req<{ types: string[] }>(`${B}/link-prices/types/list`),
  addLinkType: (name: string) => req<void>(`${B}/link-prices/types/add?name=${encodeURIComponent(name)}`, { method: 'POST' }),
  renameLinkType: (o: string, n: string) => req<{ prices_updated: number }>(`${B}/link-prices/types/rename?old_name=${encodeURIComponent(o)}&new_name=${encodeURIComponent(n)}`, { method: 'PUT' }),
  deleteLinkType: (name: string) => req<void>(`${B}/link-prices/types/delete?name=${encodeURIComponent(name)}`, { method: 'DELETE' }),
  createLinkPrice: (d: Record<string, unknown>) => req<LinkPrice>(`${B}/link-prices`, J(d)),
  updateLinkPrice: (id: string, d: Record<string, unknown>) => req<LinkPrice>(`${B}/link-prices/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(d) }),
  deleteLinkPrice: (id: string) => req<void>(`${B}/link-prices/${id}`, { method: 'DELETE' }),
  // Owner autocomplete
  searchOwners: (q: string) => req<{ items: { owner: string; email: string | null; telegram: string | null }[] }>(`${B}/domains/owners/search?q=${encodeURIComponent(q)}`),
  // Payment methods
  getPaymentMethods: (domainId: string) => req<{ items: { id: string; method: string; details: Record<string, string>; is_preferred: boolean }[]; available: string[]; fields: Record<string, { key: string; label: string; required: boolean }[]> }>(`${B}/domains/${domainId}/payment-methods`),
  addPaymentMethod: (domainId: string, d: { method: string; details?: Record<string, string> }) => req<{ id: string; method: string; details: Record<string, string>; is_preferred: boolean }>(`${B}/domains/${domainId}/payment-methods`, J(d)),
  updatePaymentMethod: (domainId: string, pmId: string, d: Record<string, unknown>) => req<void>(`${B}/domains/${domainId}/payment-methods/${pmId}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(d) }),
  setPreferredPayment: (domainId: string, pmId: string) => req<void>(`${B}/domains/${domainId}/payment-methods/${pmId}/set-preferred`, { method: 'POST' }),
  deletePaymentMethod: (domainId: string, pmId: string) => req<void>(`${B}/domains/${domainId}/payment-methods/${pmId}`, { method: 'DELETE' }),
  getContacts: (p = 1, pp = 1) => req<{ total: number }>(`${B}/contacts?per_page=${pp}&page=${p}`),
  getDomainContacts: (domainId: string) => req<{ items: any[]; total: number }>(`${B}/contacts?domain_id=${domainId}&per_page=100`),
  createContact: (d: Record<string, unknown>) => req<any>(`${B}/contacts`, J(d)),
  setPrimaryContact: (contactId: string) => req<any>(`${B}/contacts/${contactId}/set-primary`, { method: 'POST' }),
  getOutreachMessages: (status?: string, pp = 1) => req<{ total: number }>(`${B}/outreach/messages?per_page=${pp}${status ? `&status=${status}` : ''}`),
  // Contacts Grabber
  grabContacts: (domainId: string, useBrowser = false) => req<any>(`${B}/contacts/grab/${domainId}?use_browser=${useBrowser}`, { method: 'POST' }),
  bulkGrabContacts: (domainIds?: string[]) => req<any>(`${B}/contacts/grab-bulk`, J({ domain_ids: domainIds || null })),
  selectedGrabContacts: (ids: string[]) => req<{ scanned: number; found: number; results: { domain: string; email: string | null }[] }>(`${B}/domains/selected-grab-contacts`, J({ domain_ids: ids })),
  classifyAdult: (ids: string[], forceRefresh = false) => req<{ scanned: number; adult: number; non_adult: number; unclear: number; results: any[] }>(`${B}/domains/classify-adult`, J({ domain_ids: ids, force_refresh: forceRefresh })),
  classifyDomainTypes: (ids: string[]) => req<{ scanned: number; updated: number; unmatched: number; results: any[] }>(`${B}/domains/classify-type`, J({ domain_ids: ids })),
  setAdultOverride: (id: string, verdict: 'adult' | 'non_adult', note?: string) => req<{ success: boolean; root_domain: string; verdict: string; note: string | null; domains_updated: number }>(`${B}/domains/${id}/adult-override`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ verdict, note }) }),
  clearAdultOverride: (id: string) => req<{ success: boolean; domains_reset: number }>(`${B}/domains/${id}/adult-override`, { method: 'DELETE' }),
  // Operational Agent
  getAgentActions: () => req<{ actions: { name: string; description: string; permission: string; requires_confirmation: boolean }[] }>(`${B}/agent/actions`),
  sendAgentCommand: (d: { message: string; session_id?: string; action_name?: string; action_args?: Record<string, unknown> }) => req<{ session_id: string; message: { id: string; role: string; content: string; meta: Record<string, unknown> }; action: Record<string, unknown> | null }>(`${B}/agent/commands`, J(d)),
  executeAgentAction: (d: { session_id?: string; action_name: string; action_args?: Record<string, unknown>; confirm?: boolean }) => req<{ session_id: string; message: { id: string; role: string; content: string; meta: Record<string, unknown> }; action: Record<string, unknown> | null }>(`${B}/agent/actions`, J(d)),
  confirmAgentAction: (id: string) => req<{ session_id: string; message: { id: string; role: string; content: string; meta: Record<string, unknown> }; action: Record<string, unknown> }>(`${B}/agent/actions/${id}/confirm`, { method: 'POST' }),
  cancelAgentAction: (id: string) => req<{ success: boolean; action: Record<string, unknown> }>(`${B}/agent/actions/${id}/cancel`, { method: 'POST' }),
  getAgentSessions: () => req<{ items: { id: string; title: string | null; created_at: string | null; updated_at: string | null }[] }>(`${B}/agent/sessions`),
  getAgentSession: (id: string) => req<{ session: Record<string, unknown>; messages: { id: string; role: string; content: string; meta: Record<string, unknown>; created_at: string | null }[]; actions: Record<string, unknown>[] }>(`${B}/agent/sessions/${id}`),
  deleteAgentSession: (id: string) => req<{ success: boolean; id: string }>(`${B}/agent/sessions/${id}`, { method: 'DELETE' }),
  getForms: (domainId: string) => req<{ items: any[] }>(`${B}/contacts/forms/${domainId}`),
  submitForm: (domainId: string, formId?: string, templateId?: string) => req<any>(`${B}/contacts/submit-form/${domainId}?${formId ? `form_id=${formId}` : ''}${templateId ? `&template_id=${templateId}` : ''}`, { method: 'POST' }),
  previewFormSubmission: (domainId: string, formId?: string, templateId?: string) => req<any>(`${B}/contacts/submit-form/${domainId}/preview?${formId ? `form_id=${formId}` : ''}${templateId ? `&template_id=${templateId}` : ''}`, { method: 'POST' }),
  // Templates
  getTemplates: () => req<{ items: any[] }>(`${B}/contacts/templates/list`),
  createTemplate: (d: Record<string, unknown>) => req<any>(`${B}/contacts/templates`, J(d)),
  updateTemplate: (id: string, d: Record<string, unknown>) => req<any>(`${B}/contacts/templates/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(d) }),
  deleteContact: (id: string) => req<void>(`${B}/contacts/${id}`, { method: 'DELETE' }),
  deleteTemplate: (id: string) => req<void>(`${B}/contacts/templates/${id}`, { method: 'DELETE' }),
  // Inbox
  getEmails: (limit = 50, offset = 0, unreadOnly = false, search?: string) => req<any[]>(`${B}/inbox?limit=${limit}&offset=${offset}&unread_only=${unreadOnly}${search ? `&search=${encodeURIComponent(search)}` : ''}`),
  getEmail: (uid: string) => req<any>(`${B}/inbox/${uid}`),
  markEmailRead: (uid: string) => req<{ success: boolean }>(`${B}/inbox/${uid}/mark-read`, { method: 'POST' }),
  replyToEmail: (uid: string, body: string, quoteOriginal = true) => req<{ success: boolean; message: string }>(`${B}/inbox/${uid}/reply`, J({ body, quote_original: quoteOriginal })),
  composeEmail: (to: string, subject: string, body: string, domain_id?: string) => req<{ success: boolean; message: string }>(`${B}/inbox/compose`, J({ to, subject, body, domain_id })),
  scanReplies: () => req<{ processed: number; results: any[] }>(`${B}/inbox/scan-replies`, { method: 'POST', headers: authHeaders() }),
  getInboxStats: () => req<{ sent_count: number; unread: number }>(`${B}/inbox/stats`),
  // Campaigns
  getCampaigns: () => req<{ items: any[] }>(`${B}/campaigns`),
  getCampaign: (id: string) => req<any>(`${B}/campaigns/${id}`),
  createCampaign: (d: Record<string, unknown>) => req<any>(`${B}/campaigns`, J(d)),
  updateCampaign: (id: string, d: Record<string, unknown>) => req<{ success: boolean }>(`${B}/campaigns/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(d) }),
  deleteCampaign: (id: string) => req<{ success: boolean }>(`${B}/campaigns/${id}`, { method: 'DELETE' }),
  // Campaign targets
  createTarget: (campaignId: string, d: Record<string, unknown>) => req<any>(`${B}/campaigns/${campaignId}/targets`, J(d)),
  updateTarget: (targetId: string, d: Record<string, unknown>) => req<{ success: boolean }>(`${B}/campaigns/targets/${targetId}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(d) }),
  deleteTarget: (targetId: string) => req<{ success: boolean }>(`${B}/campaigns/targets/${targetId}`, { method: 'DELETE' }),
  // Publisher rules
  getPublisherRules: (domainId: string) => req<any>(`${B}/campaigns/publisher-rules/${domainId}`),
  savePublisherRules: (domainId: string, d: Record<string, unknown>) => req<any>(`${B}/campaigns/publisher-rules/${domainId}`, J(d)),
  grabPublisherRules: (domainId: string) => req<any>(`${B}/campaigns/publisher-rules/${domainId}/grab`, J({})),
  grabContact: (domainId: string) => req<any>(`${B}/domains/${domainId}/grab-contact`, J({})),
  deletePublisherRules: (domainId: string) => req<{ success: boolean }>(`${B}/campaigns/publisher-rules/${domainId}`, { method: 'DELETE' }),
  // Orders
  createOrder: (campaignId: string, d: Record<string, unknown>) => req<any>(`${B}/campaigns/${campaignId}/orders`, J(d)),
  createBulkOrders: (campaignId: string, orders: any[]) => req<{ created: number; skipped: number }>(`${B}/campaigns/${campaignId}/orders/bulk`, J({ orders })),
  updateOrder: (orderId: string, d: Record<string, unknown>) => req<{ success: boolean }>(`${B}/campaigns/orders/${orderId}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(d) }),
  deleteOrder: (orderId: string) => req<{ success: boolean }>(`${B}/campaigns/orders/${orderId}`, { method: 'DELETE' }),
  // Campaign analytics
  getAnchorStats: (campaignId: string) => req<any>(`${B}/campaigns/${campaignId}/anchor-stats`),
  getAnchorPool: (campaignId: string) => req<any>(`${B}/campaigns/${campaignId}/anchor-pool`),
  addOrderLink: (orderId: string, d: Record<string, any>) => req<any>(`${B}/campaigns/orders/${orderId}/links`, J(d)),
  deleteOrderLink: (linkId: string) => req<any>(`${B}/campaigns/order-links/${linkId}`, { method: 'DELETE' }),
  getReadyDomains: (campaignId: string, filters?: Record<string, any>) => {
    const params = new URLSearchParams();
    if (filters) Object.entries(filters).forEach(([k, v]) => { if (v !== '' && v !== null && v !== undefined) params.set(k, String(v)); });
    const qs = params.toString();
    return req<{ items: any[]; total: number; summary?: Record<string, number> }>(`${B}/campaigns/${campaignId}/ready-domains${qs ? '?' + qs : ''}`);
  },
  hideReadyDomain: (campaignId: string, domainId: string, reason?: string) => req<{ success: boolean; id: string; domain_id: string }>(`${B}/campaigns/${campaignId}/ready-domain-exclusions`, J({ domain_id: domainId, reason: reason || null })),
  unhideReadyDomain: (campaignId: string, domainId: string) => req<{ success: boolean; domain_id: string }>(`${B}/campaigns/${campaignId}/ready-domain-exclusions/${domainId}`, { method: 'DELETE' }),
  // Target Sites
  getTargetSites: () => req<{ items: any[] }>(`${B}/target-sites`),
  createTargetSite: (d: Record<string, any>) => req<any>(`${B}/target-sites`, J(d)),
  getTargetSite: (id: string) => req<any>(`${B}/target-sites/${id}`),
  updateTargetSite: (id: string, d: Record<string, any>) => req<any>(`${B}/target-sites/${id}`, { ...J(d), method: 'PUT' }),
  deleteTargetSite: (id: string) => req<any>(`${B}/target-sites/${id}`, { method: 'DELETE' }),
  addTargetURL: (siteId: string, d: Record<string, any>) => req<any>(`${B}/target-sites/${siteId}/urls`, J(d)),
  deleteTargetURL: (urlId: string) => req<any>(`${B}/target-sites/urls/${urlId}`, { method: 'DELETE' }),
  addAnchor: (urlId: string, d: Record<string, any>) => req<any>(`${B}/target-sites/urls/${urlId}/anchors`, J(d)),
  updateAnchor: (anchorId: string, d: Record<string, any>) => req<any>(`${B}/target-sites/anchors/${anchorId}`, { ...J(d), method: 'PUT' }),
  deleteAnchor: (anchorId: string) => req<any>(`${B}/target-sites/anchors/${anchorId}`, { method: 'DELETE' }),
  bulkImportURLs: (siteId: string, entries: string[], siteName?: string) => req<any>(`${B}/target-sites/${siteId}/bulk-import`, J({ entries, site_name: siteName })),
  suggestAnchor: (siteId: string) => req<any>(`${B}/target-sites/${siteId}/suggest-anchor`),
  // Article generation & order sending
  generateArticle: (orderId: string, opts?: {
    nofollow_target?: boolean;
    nofollow_resources?: boolean;
    skip_resource_links?: boolean;
    max_words?: number;
    resource_links_count?: number;
    brand_mentions_scope?: 'any' | 'all';
    brand_mentions_brands?: string;
    brand_mentions_in_title?: boolean;
    brand_mentions_body_count?: number;
  }) => req<{ success: boolean; order_id: string; article_content: string; word_count: number; status: string }>(`${B}/internal/orders/${orderId}/generate-article`, J(opts || {})),
  sendOrder: (orderId: string) => req<{ success: boolean; order_id: string; sent_to: string; subject: string; status: string; sent_at: string }>(`${B}/internal/orders/${orderId}/send`, { method: 'POST' }),
  verifyLive: (orderId: string, url: string) => req<{ verified: boolean; order_id: string; live_url?: string; reason?: string; found_backlinks?: string[]; missing_backlinks?: string[] }>(`${B}/internal/orders/${orderId}/verify-live?url=${encodeURIComponent(url)}`, { method: 'POST' }),
  processAllDrafts: (campaignId: string) => req<{ total: number; articles_generated: number; emails_sent: number; errors: any[] }>(`${B}/internal/campaigns/${campaignId}/process-drafts`, { method: 'POST' }),
  // Orders lifecycle
  approveOrder: (orderId: string, articleContent?: string) => req<any>(`${B}/internal/orders/${orderId}/approve`, J({ modified: !!articleContent, article_content: articleContent || null })),
  rejectOrder: (orderId: string) => req<any>(`${B}/internal/orders/${orderId}/reject`, { method: 'POST' }),
  confirmPayment: (orderId: string, notes?: string) => req<any>(`${B}/orders/${orderId}/confirm-payment`, J({ notes: notes || null })),
  markPaymentSent: (orderId: string, notes?: string) => req<any>(`${B}/orders/${orderId}/mark-payment-sent`, J({ notes: notes || null })),
  verifyOrder: (orderId: string, url: string) => req<any>(`${B}/orders/${orderId}/verify`, J({ url })),
  getOrderChecks: (orderId: string) => req<any[]>(`${B}/orders/${orderId}/checks`),
  checkAllLinks: () => req<any>(`${B}/internal/orders/check-links`, { method: 'POST' }),
  // Campaign autopilot
  runCampaignCycle: (campaignId: string) => req<any>(`${B}/campaigns/${campaignId}/run-cycle`, { method: 'POST' }),
  runAllAutoCampaigns: () => req<any>(`${B}/campaigns/run-all-auto`, { method: 'POST' }),
  getSchedulerStatus: () => req<any>(`${B}/campaigns/scheduler/status`),
};
