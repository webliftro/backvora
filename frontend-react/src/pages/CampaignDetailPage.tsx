import { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { Settings,
  ArrowLeft, Plus, Trash2, Edit2, ExternalLink, Package, Target as TargetIcon,
  BarChart3, Briefcase, Check, X as XIcon, DollarSign, Zap, Clock, Shield,
  Play, Pause, ChevronDown, ChevronUp, CheckCircle, AlertCircle, EyeOff,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { api } from '../api';
import { useToast } from '../components/Toast';
import Modal from '../components/Modal';
import { StatusPill } from '../components/ui';
import { statusTone } from '../components/styles';

const anchorColors: Record<string, string> = {
  brand: 'bg-blue-600',
  generic: 'bg-green-600',
  topical: 'bg-yellow-600',
  exact: 'bg-red-600',
};

const LINK_TYPES = ['Guest Post', 'Header', 'Footer', 'Navbar', 'Sidebar', 'Sidebar Friends', 'Toplist', 'Sticky Post', 'Topbar', 'Menu tab', 'Model+Content tab'];

function isVerificationOk(status?: string | null) {
  return ['ok', 'verified'].includes((status || '').toLowerCase());
}

export default function CampaignDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [campaign, setCampaign] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'targets' | 'anchors' | 'ready' | 'orders' | 'autopilot'>('targets');
  const [anchorStats, setAnchorStats] = useState<any>(null);
  const [readyDomains, setReadyDomains] = useState<any[]>([]);
  const [readySummary, setReadySummary] = useState<Record<string, number> | null>(null);
  const [readyFilters, setReadyFilters] = useState({ link_type: '', min_price: '', max_price: '', min_traffic: '', max_traffic: '', min_dr: '', max_dr: '', has_payment: '' });
  const [selectedReady, setSelectedReady] = useState<Record<string, { domain_id: string; link_type: string; price: number | null; contact_id: string | null }>>({});
  const [bulkAdding, setBulkAdding] = useState(false);
  const [hidingReadyDomainId, setHidingReadyDomainId] = useState<string | null>(null);
  const [expandedOrders, setExpandedOrders] = useState<Set<string>>(new Set());
  const [addLinkModal, setAddLinkModal] = useState<any>(null);
  const [linkForm, setLinkForm] = useState({ target_url: '', anchor_text: '', anchor_text_id: '', anchor_type: '', article_topic: '' });
  const [allTargetSites, setAllTargetSites] = useState<any[]>([]);
  const [selectedSiteId, setSelectedSiteId] = useState<string>('');

  // Modals
  const [targetModal, setTargetModal] = useState(false);
  const [editModal, setEditModal] = useState(false);
  const [orderModal, setOrderModal] = useState<any>(null);
  const [anchorPool, setAnchorPool] = useState<any>(null);
  const [articleModal, setArticleModal] = useState<any>(null);
  const [articleEditing, setArticleEditing] = useState(false);
  const [articleDraft, setArticleDraft] = useState('');
  const [articleSaving, setArticleSaving] = useState(false);
  const [targetForm, setTargetForm] = useState({ url: '', brand_name: '', description: '', priority: 1 });
  const [editForm, setEditForm] = useState<any>({});
  const [targetSiteData, setTargetSiteData] = useState<any>(null);
  const [showEditFilters, setShowEditFilters] = useState(false);

  // Autopilot state
  const [schedulerStatus, setSchedulerStatus] = useState<any>(null);
  const [runningCycle, setRunningCycle] = useState(false);
  const [orderChecks, setOrderChecks] = useState<Record<string, any[]>>({});
  const [verifyModal, setVerifyModal] = useState<any>(null); // { order_id, domain }
  const [verifyUrl, setVerifyUrl] = useState('');
  const [orderBrandDrafts, setOrderBrandDrafts] = useState<Record<string, {
    brand_mentions_scope: string;
    brand_mentions_brands: string;
    brand_mentions_in_title: boolean;
    brand_mentions_body_count: string;
  }>>({});

  useEffect(() => {
    if (id) {
      loadCampaign();
      loadAnchorStats();
      loadReadyDomains();
      api.getTargetSites().then(d => setAllTargetSites(d.items)).catch(() => {});
    }
  }, [id]);

  async function loadCampaign() {
    try {
      setLoading(true);
      const data = await api.getCampaign(id!);
      setCampaign(data);
      const drafts: Record<string, { brand_mentions_scope: string; brand_mentions_brands: string; brand_mentions_in_title: boolean; brand_mentions_body_count: string; }> = {};
      for (const o of data.orders || []) {
        drafts[o.id] = {
          brand_mentions_scope: o.brand_mentions_scope || '',
          brand_mentions_brands: o.brand_mentions_brands || '',
          brand_mentions_in_title: o.brand_mentions_in_title === true,
          brand_mentions_body_count: o.brand_mentions_body_count ? String(o.brand_mentions_body_count) : '',
        };
      }
      setOrderBrandDrafts(drafts);
      if (data.target_site_id) {
        api.getTargetSite(data.target_site_id).then(d => setTargetSiteData(d)).catch(() => {});
      }
      setEditForm({
        name: data.name,
        target_site: data.target_site,
        status: data.status,
        budget: data.budget || '',
        spent: data.spent || 0,
        notes: data.notes || '',
        anchor_brand_pct: data.anchor_brand_pct,
        anchor_generic_pct: data.anchor_generic_pct,
        anchor_topical_pct: data.anchor_topical_pct,
        anchor_exact_pct: data.anchor_exact_pct,
        mode: data.mode || 'manual',
        filter_traffic_min: data.filter_traffic_min || '',
        filter_traffic_max: data.filter_traffic_max || '',
        filter_dr_min: data.filter_dr_min || '',
        filter_dr_max: data.filter_dr_max || '',
        filter_price_min: data.filter_price_min || '',
        filter_price_max: data.filter_price_max || '',
        filter_niche_tags: data.filter_niche_tags || '',
        filter_link_type: data.filter_link_type || '',
        velocity_count: data.velocity_count || 1,
        velocity_period_days: data.velocity_period_days || 7,
        budget_total: data.budget_total || '',
        schedule_enabled: data.schedule_enabled || false,
        schedule_interval_hours: data.schedule_interval_hours || 6,
      });
      // Load scheduler status for auto campaigns
      if (data.mode === 'auto') {
        api.getSchedulerStatus().then(d => setSchedulerStatus(d)).catch(() => {});
      }
    } catch (e: any) {
      toast(e.message, 'error');
    } finally {
      setLoading(false);
    }
  }

  function getArticleTitle(content: string) {
    return content.split('\n').find((line: string) => line.startsWith('TITLE:'))?.replace('TITLE:', '').trim() || 'Article';
  }

  function getWordCount(content: string) {
    return content.trim().split(/\s+/).filter(Boolean).length;
  }

  function openArticleModal(order: any) {
    const articleContent = order.article_content || '';
    setArticleEditing(false);
    setArticleDraft(articleContent);
    setArticleModal({
      order_id: order.id,
      article_content: articleContent,
      title: getArticleTitle(articleContent),
      word_count: getWordCount(articleContent),
      images: order.images || [],
      target_urls: (order.links || []).map((l: any) => l.target_url).concat(order.target_url ? [order.target_url] : []),
    });
  }

  async function saveArticleEdit() {
    if (!articleModal || articleSaving) return;
    const nextContent = articleDraft;
    if (!nextContent.trim()) {
      toast('Article cannot be empty', 'error');
      return;
    }

    try {
      setArticleSaving(true);
      await api.updateOrder(articleModal.order_id, { article_content: nextContent });
      const nextTitle = getArticleTitle(nextContent);
      const nextWordCount = getWordCount(nextContent);

      setCampaign((current: any) => {
        if (!current?.orders) return current;
        return {
          ...current,
          orders: current.orders.map((order: any) => (
            order.id === articleModal.order_id
              ? { ...order, article_content: nextContent }
              : order
          )),
        };
      });
      setArticleModal({
        ...articleModal,
        article_content: nextContent,
        title: nextTitle,
        word_count: nextWordCount,
      });
      setArticleEditing(false);
      toast('Article updated');
    } catch (e: any) {
      toast(e.message, 'error');
    } finally {
      setArticleSaving(false);
    }
  }

  async function loadAnchorStats() {
    try {
      const data = await api.getAnchorStats(id!);
      setAnchorStats(data);
    } catch (e: any) {
      console.error('Failed to load anchor stats:', e);
    }
  }

  async function loadReadyDomains(filters?: Record<string, any>) {
    try {
      const f = filters || readyFilters;
      const data = await api.getReadyDomains(id!, f);
      setReadyDomains(data.items);
      setReadySummary(data.summary || null);
    } catch (e: any) {
      console.error('Failed to load ready domains:', e);
    }
  }

  async function hideReadyDomain(domainId: string) {
    setHidingReadyDomainId(domainId);
    try {
      await api.hideReadyDomain(id!, domainId, 'hidden from campaign ready list');
      setReadyDomains(prev => prev.filter(d => d.id !== domainId));
      setSelectedReady(prev => {
        const next = { ...prev };
        Object.keys(next).forEach(key => {
          if (key.startsWith(`${domainId}:`)) delete next[key];
        });
        return next;
      });
      toast('Hidden from this campaign');
    } catch (e: any) {
      toast(e.message, 'error');
    } finally {
      setHidingReadyDomainId(null);
    }
  }

  async function handleAddTarget(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api.createTarget(id!, targetForm);
      toast('Target added!');
      setTargetModal(false);
      setTargetForm({ url: '', brand_name: '', description: '', priority: 1 });
      loadCampaign();
    } catch (e: any) {
      toast(e.message, 'error');
    }
  }

  async function handleDeleteTarget(targetId: string) {
    if (!confirm('Delete this target?')) return;
    try {
      await api.deleteTarget(targetId);
      toast('Target deleted');
      loadCampaign();
    } catch (e: any) {
      toast(e.message, 'error');
    }
  }

  async function handleUpdateCampaign(e: React.FormEvent) {
    e.preventDefault();
    try {
      const payload: Record<string, any> = {
        ...editForm,
        budget: editForm.budget ? parseFloat(editForm.budget) : null,
      };
      if (editForm.mode === 'auto') {
        payload.filter_traffic_min = editForm.filter_traffic_min ? parseInt(editForm.filter_traffic_min) : null;
        payload.filter_traffic_max = editForm.filter_traffic_max ? parseInt(editForm.filter_traffic_max) : null;
        payload.filter_dr_min = editForm.filter_dr_min ? parseInt(editForm.filter_dr_min) : null;
        payload.filter_dr_max = editForm.filter_dr_max ? parseInt(editForm.filter_dr_max) : null;
        payload.filter_price_min = editForm.filter_price_min ? parseFloat(editForm.filter_price_min) : null;
        payload.filter_price_max = editForm.filter_price_max ? parseFloat(editForm.filter_price_max) : null;
        payload.budget_total = editForm.budget_total ? parseFloat(editForm.budget_total) : null;
        payload.velocity_count = parseInt(editForm.velocity_count) || 1;
        payload.velocity_period_days = parseInt(editForm.velocity_period_days) || 7;
        payload.schedule_interval_hours = parseInt(editForm.schedule_interval_hours) || 6;
      }
      await api.updateCampaign(id!, payload);
      toast('Campaign updated!');
      setEditModal(false);
      loadCampaign();
      loadAnchorStats();
    } catch (e: any) {
      toast(e.message, 'error');
    }
  }

  const [orderRules, setOrderRules] = useState<any>(null);
  const [askingRules, setAskingRules] = useState(false);

  function getOrderBrandDraft(order: any) {
    return orderBrandDrafts[order.id] || {
      brand_mentions_scope: order.brand_mentions_scope || '',
      brand_mentions_brands: order.brand_mentions_brands || '',
      brand_mentions_in_title: order.brand_mentions_in_title === true,
      brand_mentions_body_count: order.brand_mentions_body_count ? String(order.brand_mentions_body_count) : '',
    };
  }

  async function updateOrderBrandDraft(order: any, patch: Partial<{
    brand_mentions_scope: string;
    brand_mentions_brands: string;
    brand_mentions_in_title: boolean;
    brand_mentions_body_count: string;
  }>) {
    const current = getOrderBrandDraft(order);
    const next = { ...current, ...patch };
    setOrderBrandDrafts((prev) => ({ ...prev, [order.id]: next }));
    try {
      await api.updateOrder(order.id, {
        brand_mentions_scope: next.brand_mentions_scope || null,
        brand_mentions_brands: next.brand_mentions_brands || null,
        brand_mentions_in_title: !!next.brand_mentions_in_title,
        brand_mentions_body_count: next.brand_mentions_body_count ? parseInt(next.brand_mentions_body_count) : null,
      });
    } catch {}
  }

  async function openOrderModal(domain: any, linkType: string, price: any) {
    setOrderModal({ domain, link_type: linkType, price: price || '', target_url: '', anchor_text: '', anchor_text_id: '', anchor_type: '' });
    setOrderRules(null);
    try {
      const pool = await api.getAnchorPool(id!);
      setAnchorPool(pool);
      if (pool?.suggestion) {
        setOrderModal((m: any) => m ? ({
          ...m,
          anchor_text: pool.suggestion.text,
          anchor_text_id: pool.suggestion.anchor_id,
          anchor_type: pool.suggestion.anchor_type,
          target_url: pool.suggestion.target_url,
        }) : m);
      }
    } catch { setAnchorPool(null); }
    try {
      const rules = await api.getPublisherRules(domain.id);
      setOrderRules(rules);
    } catch { setOrderRules(null); }
  }

  async function handleCreateOrder(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api.createOrder(id!, {
        domain_id: orderModal.domain.id,
        link_type: orderModal.link_type,
        price: orderModal.price ? parseFloat(orderModal.price) : null,
        contact_id: orderModal.domain.contact_id || null,
        target_url: orderModal.target_url || null,
        anchor_text: orderModal.anchor_text || null,
        anchor_text_id: orderModal.anchor_text_id || null,
      });
      toast('Order created!');
      setOrderModal(null);
      setAnchorPool(null);
      loadCampaign();
      loadReadyDomains();
      loadAnchorStats();
    } catch (e: any) {
      toast(e.message, 'error');
    }
  }

  async function handleDeleteCampaign() {
    if (!confirm(`Delete campaign "${campaign?.name}"? This will also delete all orders.`)) return;
    try {
      await api.deleteCampaign(id!);
      toast('Campaign deleted');
      navigate('/campaigns');
    } catch (e: any) {
      toast(e.message, 'error');
    }
  }

  async function loadOrderChecks(orderId: string) {
    try {
      const checks = await api.getOrderChecks(orderId);
      setOrderChecks(prev => ({ ...prev, [orderId]: checks }));
    } catch { /* ignore */ }
  }

  if (loading || !campaign) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-gray-500">Loading campaign...</div>
      </div>
    );
  }

  const ic = "px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-pink-500 w-full";
  const isAuto = campaign.mode === 'auto';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <Link to="/campaigns" className="text-pink-400 hover:underline text-sm flex items-center gap-1 mb-3">
          <ArrowLeft className="w-4 h-4" />
          Back to Campaigns
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold tracking-tight flex items-center gap-3 flex-wrap">
              {campaign.name}
              {isAuto ? (
                <StatusPill tone="success"><Zap className="w-4 h-4" />Auto</StatusPill>
              ) : (
                <StatusPill tone="neutral">Manual</StatusPill>
              )}
              <StatusPill tone={statusTone(campaign.status)}>{campaign.status}</StatusPill>
            </h1>
            <p className="text-gray-400 mt-1">{campaign.target_site}</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setEditModal(true)}
              className="px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm flex items-center gap-1"
            >
              <Edit2 className="w-4 h-4" />
              Edit
            </button>
            <button
              onClick={handleDeleteCampaign}
              className="px-3 py-2 bg-red-600 hover:bg-red-700 rounded-lg text-sm flex items-center gap-1"
            >
              <Trash2 className="w-4 h-4" />
              Delete
            </button>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mt-6">
          <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
            <div className="flex items-center gap-2 text-gray-400 text-sm mb-1">
              <Package className="w-4 h-4" />
              Total Orders
            </div>
            <div className="text-2xl font-semibold tabular-nums">{campaign.orders.length}</div>
          </div>
          <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
            <div className="flex items-center gap-2 text-gray-400 text-sm mb-1">
              <Check className="w-4 h-4" />
              Links Live
            </div>
            <div className="text-2xl font-semibold tabular-nums text-green-400">
              {campaign.orders.filter((o: any) => ['published', 'paid', 'live'].includes(o.status)).length}
            </div>
          </div>
          <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
            <div className="flex items-center gap-2 text-gray-400 text-sm mb-1">
              <DollarSign className="w-4 h-4" />
              Spent
            </div>
            <div className="text-2xl font-semibold tabular-nums">${campaign.spent.toFixed(0)}</div>
            {campaign.budget && (
              <div className="text-xs text-gray-500 mt-1">of ${campaign.budget.toFixed(0)}</div>
            )}
          </div>
          <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-2 text-gray-400 text-sm">
                <TargetIcon className="w-4 h-4" />
                Targets
              </div>
              <button
                onClick={() => setTargetModal(true)}
                className="px-2 py-0.5 bg-pink-600 hover:bg-pink-700 rounded text-xs flex items-center gap-1"
              >
                <Plus className="w-3 h-3" />
                Add
              </button>
            </div>
            <div className="text-2xl font-semibold tabular-nums mb-2">{campaign.targets.length}</div>
            {campaign.targets.length > 0 && (
              <div className="space-y-1 border-t border-gray-700 pt-2">
                {campaign.targets.map((target: any) => (
                  <div key={target.id} className="flex items-center gap-2 text-xs group">
                    <a
                      href={target.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-pink-400 hover:underline truncate"
                    >
                      {target.url.replace(/^https?:\/\//, '')}
                    </a>
                    <button
                      onClick={() => handleDeleteTarget(target.id)}
                      aria-label="Delete target URL"
                      className="text-red-400/0 group-hover:text-red-400 focus-visible:text-red-400 hover:text-red-300 transition-colors shrink-0"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-700">
        <nav className="flex gap-6 overflow-x-auto">
          {[
            { key: 'targets', label: 'Targets', icon: TargetIcon },
            { key: 'anchors', label: 'Anchor Distribution', icon: BarChart3 },
            { key: 'ready', label: 'Ready Domains', icon: Briefcase },
            { key: 'orders', label: 'Orders', icon: Package },
            ...(isAuto ? [{ key: 'autopilot', label: 'Autopilot', icon: Zap }] : []),
          ].map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key as any)}
              className={`pb-3 border-b-2 transition-colors flex items-center gap-2 whitespace-nowrap ${
                activeTab === tab.key
                  ? 'border-pink-500 text-white'
                  : 'border-transparent text-gray-400 hover:text-white'
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Autopilot Tab */}
      {activeTab === 'autopilot' && isAuto && (
        <div className="space-y-6">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Zap className="w-5 h-5 text-emerald-400" />
            Autopilot Dashboard
          </h2>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Velocity Status */}
            <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
              <div className="flex items-center gap-2 text-gray-400 text-sm mb-2">
                <Clock className="w-4 h-4" />
                Velocity
              </div>
              <div className="text-lg font-bold">
                {campaign.velocity_count} link{campaign.velocity_count > 1 ? 's' : ''} / {campaign.velocity_period_days === 7 ? 'week' : `${campaign.velocity_period_days}d`}
              </div>
              <div className="text-xs text-gray-500 mt-1">
                {campaign.last_order_sent_at ? (
                  (() => {
                    const last = new Date(campaign.last_order_sent_at);
                    const next = new Date(last.getTime() + (campaign.velocity_period_days || 7) * 86400000);
                    const now = new Date();
                    const diff = Math.ceil((next.getTime() - now.getTime()) / 86400000);
                    return diff > 0 ? `Next order in ${diff} day${diff > 1 ? 's' : ''}` : 'Ready to send';
                  })()
                ) : 'Ready to send'}
              </div>
            </div>

            {/* Approval Mode */}
            <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
              <div className="flex items-center gap-2 text-gray-400 text-sm mb-2">
                <Shield className="w-4 h-4" />
                Approval
              </div>
              {campaign.approval_mode === 'auto' ? (
                <div className="text-lg font-bold text-emerald-400">Full Auto 🎓</div>
              ) : (
                <>
                  <div className="text-lg font-bold text-yellow-400">
                    Review ({campaign.consecutive_approvals || 0}/{campaign.approval_threshold || 10})
                  </div>
                  <div className="w-full bg-gray-700 rounded-full h-2 mt-2 overflow-hidden">
                    <div
                      className="bg-yellow-500 h-full rounded-full transition-all"
                      style={{ width: `${Math.min(100, ((campaign.consecutive_approvals || 0) / (campaign.approval_threshold || 10)) * 100)}%` }}
                    />
                  </div>
                </>
              )}
            </div>

            {/* Budget */}
            <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
              <div className="flex items-center gap-2 text-gray-400 text-sm mb-2">
                <DollarSign className="w-4 h-4" />
                Auto Budget
              </div>
              {campaign.budget_total ? (
                <>
                  <div className="text-lg font-bold">
                    ${(campaign.budget_spent || 0).toFixed(0)} / ${campaign.budget_total.toFixed(0)}
                  </div>
                  <div className="w-full bg-gray-700 rounded-full h-2 mt-2 overflow-hidden">
                    <div
                      className="bg-gray-400 h-full rounded-full transition-all"
                      style={{ width: `${Math.min(100, ((campaign.budget_spent || 0) / campaign.budget_total) * 100)}%` }}
                    />
                  </div>
                </>
              ) : (
                <div className="text-lg font-bold text-gray-500">No limit</div>
              )}
            </div>

            {/* Scheduler */}
            <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
              <div className="flex items-center gap-2 text-gray-400 text-sm mb-2">
                <Clock className="w-4 h-4" />
                Scheduler
              </div>
              {campaign.schedule_enabled ? (
                <div className="text-lg font-bold text-emerald-400">
                  Active — every {campaign.schedule_interval_hours}h
                </div>
              ) : (
                <div className="text-lg font-bold text-gray-500">Inactive</div>
              )}
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-3">
            <button
              disabled={runningCycle}
              onClick={async () => {
                setRunningCycle(true);
                try {
                  const result = await api.runCampaignCycle(id!);
                  if (result.success) {
                    toast(`Cycle complete: ${result.action} — ${result.domain} ($${result.price})`);
                    loadCampaign();
                  } else {
                    toast(result.reason || 'No action taken', 'error');
                  }
                } catch (e: any) {
                  toast(e.message, 'error');
                }
                setRunningCycle(false);
              }}
              className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 rounded-lg text-sm font-medium flex items-center gap-2 disabled:opacity-50"
            >
              <Play className="w-4 h-4" />
              {runningCycle ? 'Running...' : 'Run Cycle Now'}
            </button>
            <button
              onClick={async () => {
                try {
                  await api.updateCampaign(id!, {
                    schedule_enabled: !campaign.schedule_enabled,
                  });
                  toast(campaign.schedule_enabled ? 'Schedule paused' : 'Schedule resumed');
                  loadCampaign();
                } catch (e: any) {
                  toast(e.message, 'error');
                }
              }}
              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm font-medium flex items-center gap-2"
            >
              {campaign.schedule_enabled ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
              {campaign.schedule_enabled ? 'Pause Schedule' : 'Resume Schedule'}
            </button>
          </div>

          {/* Pending Review Orders */}
          {campaign.orders.filter((o: any) => o.status === 'pending_review').length > 0 && (
            <div className="space-y-3">
              <h3 className="text-sm font-semibold text-amber-400 flex items-center gap-2">
                <AlertCircle className="w-4 h-4" />
                Pending Review ({campaign.orders.filter((o: any) => o.status === 'pending_review').length})
              </h3>
              {campaign.orders.filter((o: any) => o.status === 'pending_review').map((order: any) => (
                <div key={order.id} className="bg-amber-900/20 border border-amber-700 rounded-lg p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <Link to={`/domains/${order.domain_id}`} className="text-pink-400 hover:underline font-medium">{order.domain}</Link>
                      <span className="text-sm text-gray-400">{order.link_type} · ${order.price}</span>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={async () => {
                          try {
                            await api.approveOrder(order.id);
                            toast('Order approved and sent!');
                            loadCampaign();
                          } catch (e: any) { toast(e.message, 'error'); }
                        }}
                        className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 rounded text-xs font-medium"
                      >
                        Approve
                      </button>
                      <button
                        onClick={async () => {
                          try {
                            await api.rejectOrder(order.id);
                            toast('Order rejected');
                            loadCampaign();
                          } catch (e: any) { toast(e.message, 'error'); }
                        }}
                        className="px-3 py-1.5 bg-red-600 hover:bg-red-700 rounded text-xs font-medium"
                      >
                        Reject
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Recent Activity */}
          <div>
            <h3 className="text-sm font-semibold text-gray-300 mb-3">Recent Orders</h3>
            <div className="space-y-2">
              {campaign.orders.slice(0, 5).map((order: any) => (
                <div key={order.id} className="flex items-center gap-3 text-sm bg-gray-800/50 rounded px-3 py-2">
                  <StatusPill tone={statusTone(order.status)}>{order.status}</StatusPill>
                  <span className="text-gray-300">{order.domain}</span>
                  <span className="text-gray-500">{order.link_type}</span>
                  <span className="text-gray-500">{order.price ? `$${order.price}` : '-'}</span>
                  <span className="text-gray-600 text-xs ml-auto">{order.created_at ? new Date(order.created_at).toLocaleDateString() : ''}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Tab Content */}
      {activeTab === 'targets' && (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <h2 className="text-lg font-semibold">
              Target Site: {campaign.target_site || 'Not set'}
              {targetSiteData && (
                <Link to={`/target-sites/${targetSiteData.id}`} className="ml-2 text-sm text-pink-400 hover:underline font-normal">
                  View full details →
                </Link>
              )}
            </h2>
            <button
              onClick={() => setTargetModal(true)}
              className="px-3 py-2 bg-pink-600 hover:bg-pink-700 rounded-lg text-sm flex items-center gap-1"
            >
              <Plus className="w-4 h-4" />
              Add Target URL
            </button>
          </div>

          {targetSiteData ? (
            <div className="space-y-4">
              <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
                <div className="flex items-center gap-4 mb-3">
                  <h3 className="font-semibold text-lg">{targetSiteData.domain}</h3>
                  {targetSiteData.brand_variations && (
                    <span className="text-gray-500 text-sm">Variations: {targetSiteData.brand_variations}</span>
                  )}
                </div>
                <div className="flex gap-3 flex-wrap text-sm">
                  <span className="px-2 py-1 bg-blue-600/30 rounded text-blue-300">Brand {targetSiteData.anchor_brand_pct}%</span>
                  <span className="px-2 py-1 bg-yellow-600/30 rounded text-yellow-300">Topical {targetSiteData.anchor_topical_pct}%</span>
                  <span className="px-2 py-1 bg-green-600/30 rounded text-green-300">Generic {targetSiteData.anchor_generic_pct}%</span>
                  <span className="px-2 py-1 bg-red-600/30 rounded text-red-300">Exact {targetSiteData.anchor_exact_pct}%</span>
                  <span className="px-2 py-1 bg-teal-600/30 rounded text-teal-300">URL {targetSiteData.anchor_url_pct}%</span>
                </div>
              </div>

              <div className="space-y-3">
                <h3 className="font-medium text-gray-300">Target URLs ({targetSiteData.urls?.length || 0})</h3>
                {targetSiteData.urls?.length === 0 ? (
                  <p className="text-gray-500 text-sm">No target URLs yet.</p>
                ) : (
                  targetSiteData.urls?.map((u: any) => (
                    <div key={u.id} className="bg-gray-800 rounded-lg border border-gray-700 p-4">
                      <div className="flex items-center gap-2 mb-2">
                        <a href={u.url} target="_blank" rel="noopener" className="text-pink-400 hover:underline text-sm font-medium">{u.url}</a>
                        {u.description && <span className="text-gray-500 text-xs">({u.description})</span>}
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {u.anchors?.map((a: any) => (
                          <span
                            key={a.id}
                            className={`px-2 py-1 rounded text-xs ${anchorColors[a.anchor_type] || 'bg-gray-600'}`}
                            title={`${a.anchor_type} · used ${a.times_used}x`}
                          >
                            {a.text}
                            {a.times_used > 0 && <span className="opacity-60 ml-1">({a.times_used})</span>}
                          </span>
                        ))}
                        {(!u.anchors || u.anchors.length === 0) && (
                          <span className="text-gray-500 text-xs">No anchors</span>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>

              {campaign.targets.length > 0 && (
                <div className="space-y-2 border-t border-gray-700 pt-4">
                  <h3 className="font-medium text-gray-300 text-sm">Campaign Target URLs</h3>
                  {campaign.targets.map((target: any) => (
                    <div key={target.id} className="flex items-center justify-between bg-gray-800/50 rounded px-3 py-2 text-sm">
                      <a href={target.url} target="_blank" rel="noopener" className="text-pink-400 hover:underline truncate">
                        {target.url}
                      </a>
                      <button onClick={() => handleDeleteTarget(target.id)} aria-label="Delete target URL" className="text-gray-500 hover:text-red-400 ml-2">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="bg-gray-800 rounded-lg border border-gray-700 p-8 text-center">
              <p className="text-gray-500">No target site linked to this campaign.</p>
            </div>
          )}
        </div>
      )}

      {activeTab === 'anchors' && anchorStats && (
        <div className="space-y-6">
          <h2 className="text-lg font-semibold">Anchor Text Distribution</h2>

          <div className="grid grid-cols-2 gap-6">
            {Object.keys(anchorStats.target).map((type) => (
              <div key={type} className="bg-gray-800 rounded-lg border border-gray-700 p-4">
                <div className="flex items-center justify-between mb-3">
                  <span className="font-medium capitalize">{type}</span>
                  <span className={`px-2 py-0.5 rounded text-xs ${anchorColors[type]}`}>
                    {anchorStats.current[type]}% / {anchorStats.target[type]}%
                  </span>
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between text-sm text-gray-400">
                    <span>Current</span>
                    <span>{anchorStats.counts[type] || 0} orders</span>
                  </div>
                  <div className="w-full bg-gray-700 rounded-full h-3 overflow-hidden">
                    <div
                      className={`h-full rounded-full ${anchorColors[type]}`}
                      style={{ width: `${anchorStats.current[type]}%` }}
                    />
                  </div>
                  <div className="flex justify-between text-xs text-gray-500">
                    <span>Target: {anchorStats.target[type]}%</span>
                    <span
                      className={
                        anchorStats.current[type] < anchorStats.target[type]
                          ? 'text-yellow-400'
                          : 'text-green-400'
                      }
                    >
                      {anchorStats.current[type] >= anchorStats.target[type] ? '✓' : '⚠'}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="bg-blue-900/20 border border-blue-700 rounded-lg p-4 text-sm">
            <p className="text-blue-300">
              <strong>Total orders with anchors:</strong> {anchorStats.total_orders}
            </p>
            <p className="text-gray-400 mt-1">
              When creating new orders, anchor types will be auto-selected to match your target distribution.
            </p>
          </div>
        </div>
      )}

      {activeTab === 'ready' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold">Ready Domains ({readyDomains.length})</h2>
              <p className="text-sm text-gray-400">Domains with contact info and pricing available for ordering</p>
            </div>
            <div className="flex gap-2">
              {Object.keys(selectedReady).length > 0 && (
                <button
                  disabled={bulkAdding}
                  onClick={async () => {
                    setBulkAdding(true);
                    try {
                      const orders = Object.values(selectedReady);
                      const res = await api.createBulkOrders(id!, orders);
                      toast(`Added ${res.created} orders${res.skipped ? `, ${res.skipped} skipped (duplicates)` : ''}`);
                      setSelectedReady({});
                      loadCampaign();
                      loadReadyDomains();
                    } catch (e: any) { toast(e.message, 'error'); }
                    setBulkAdding(false);
                  }}
                  className="px-3 py-1.5 bg-green-600 hover:bg-green-700 rounded text-sm font-medium"
                >
                  {bulkAdding ? 'Adding...' : `Add ${Object.keys(selectedReady).length} to Campaign`}
                </button>
              )}
              <button onClick={() => loadReadyDomains()} className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm">Refresh</button>
            </div>
          </div>

          {readySummary && (
            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2 text-sm">
              {[
                ['All', readySummary.all_domains],
                ['Available', readySummary.available_domains],
                ['Contact', readySummary.with_contact],
                ['Price', readySummary.with_price],
                ['Ready', readySummary.ready],
                ['Shown', readySummary.returned],
                ['Ordered', readySummary.ordered_in_campaign],
                ['Hidden', readySummary.hidden_in_campaign],
              ].map(([label, value]) => (
                <div key={label} className="rounded border border-gray-700 bg-gray-800 px-3 py-2">
                  <div className="text-xs text-gray-500">{label}</div>
                  <div className="font-semibold text-gray-100">{Number(value || 0).toLocaleString()}</div>
                </div>
              ))}
            </div>
          )}

          {/* Filters */}
          <div className="bg-gray-800 rounded-lg border border-gray-700 p-3">
            <div className="flex gap-3 items-center flex-wrap text-sm">
              <select value={readyFilters.link_type} onChange={e => { const f = { ...readyFilters, link_type: e.target.value }; setReadyFilters(f); loadReadyDomains(f); }} className="px-2 py-1.5 bg-gray-700 border border-gray-600 rounded-lg text-sm">
                <option value="">All Link Types</option>
                {LINK_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
              <div className="flex items-center gap-1">
                <span className="text-gray-400">Price:</span>
                <input type="number" placeholder="Min" value={readyFilters.min_price} onChange={e => setReadyFilters(f => ({ ...f, min_price: e.target.value }))} className="w-20 px-2 py-1 bg-gray-700 border border-gray-600 rounded-lg text-sm" />
                <span className="text-gray-500">-</span>
                <input type="number" placeholder="Max" value={readyFilters.max_price} onChange={e => setReadyFilters(f => ({ ...f, max_price: e.target.value }))} className="w-20 px-2 py-1 bg-gray-700 border border-gray-600 rounded-lg text-sm" />
              </div>
              <div className="flex items-center gap-1">
                <span className="text-gray-400">Traffic:</span>
                <input type="number" placeholder="Min" value={readyFilters.min_traffic} onChange={e => setReadyFilters(f => ({ ...f, min_traffic: e.target.value }))} className="w-24 px-2 py-1 bg-gray-700 border border-gray-600 rounded-lg text-sm" />
                <span className="text-gray-500">-</span>
                <input type="number" placeholder="Max" value={readyFilters.max_traffic} onChange={e => setReadyFilters(f => ({ ...f, max_traffic: e.target.value }))} className="w-24 px-2 py-1 bg-gray-700 border border-gray-600 rounded-lg text-sm" />
              </div>
              <div className="flex items-center gap-1">
                <span className="text-gray-400">DR:</span>
                <input type="number" placeholder="Min" value={readyFilters.min_dr} onChange={e => setReadyFilters(f => ({ ...f, min_dr: e.target.value }))} className="w-16 px-2 py-1 bg-gray-700 border border-gray-600 rounded-lg text-sm" />
                <span className="text-gray-500">-</span>
                <input type="number" placeholder="Max" value={readyFilters.max_dr} onChange={e => setReadyFilters(f => ({ ...f, max_dr: e.target.value }))} className="w-16 px-2 py-1 bg-gray-700 border border-gray-600 rounded-lg text-sm" />
              </div>
              <select value={readyFilters.has_payment} onChange={e => { const f = { ...readyFilters, has_payment: e.target.value }; setReadyFilters(f); loadReadyDomains(f); }} className="px-2 py-1.5 bg-gray-700 border border-gray-600 rounded-lg text-sm">
                <option value="">Payment: Any</option>
                <option value="true">Has Payment</option>
                <option value="false">No Payment</option>
              </select>
              <button onClick={() => loadReadyDomains()} className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm">Apply</button>
              <button onClick={() => { const f = { link_type: '', min_price: '', max_price: '', min_traffic: '', max_traffic: '', min_dr: '', max_dr: '', has_payment: '' }; setReadyFilters(f); loadReadyDomains(f); }} className="px-3 py-1.5 text-gray-400 hover:text-white text-sm">Clear</button>
              <span className="text-gray-600">|</span>
              <button onClick={() => {
                const sel: typeof selectedReady = {};
                const lt = readyFilters.link_type;
                readyDomains.forEach(d => {
                  const types = lt ? d.link_types.filter((t: any) => t.type === lt) : d.link_types;
                  types.forEach((t: any) => { sel[`${d.id}:${t.type}`] = { domain_id: d.id, link_type: t.type, price: t.price, contact_id: d.contact_id }; });
                });
                setSelectedReady(sel);
              }} className="px-3 py-1.5 text-gray-400 hover:text-white text-sm">Select All</button>
              <button onClick={() => setSelectedReady({})} className="px-3 py-1.5 text-gray-400 hover:text-white text-sm">Deselect All</button>
            </div>
          </div>

          {readyDomains.length === 0 ? (
            <div className="bg-gray-800 rounded-lg border border-gray-700 p-8 text-center">
              <p className="text-gray-500">No matching domains found. Try adjusting filters.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {readyDomains.map((d) => (
                <div key={d.id} className="bg-gray-800 rounded-lg border border-gray-700 p-4">
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-3">
                        <Link to={`/domains/${d.id}`} className="text-pink-400 hover:underline font-medium">{d.domain}</Link>
                        {d.domain_niche === 'adult' && (
                          <span className="px-1.5 py-0.5 bg-pink-900/40 text-pink-300 rounded text-xs">adult</span>
                        )}
                        {(d.type_tags || []).map((tag: string) => (
                          <span key={tag} className="px-1.5 py-0.5 bg-gray-700 text-gray-300 rounded text-xs">{tag}</span>
                        ))}
                        {d.payment_methods?.length > 0 && (
                          <span className="px-1.5 py-0.5 bg-green-900/50 text-green-400 rounded text-xs">{d.payment_methods.join(', ')}</span>
                        )}
                      </div>
                      <div className="flex items-center gap-4 text-sm text-gray-400 mt-1">
                        <span>DR: {d.domain_rating || '-'}</span>
                        <span>Traffic: {d.organic_traffic?.toLocaleString() || '-'}</span>
                        {d.contact_name && <span>👤 {d.contact_name}</span>}
                        {d.contact_email && <span>✉ {d.contact_email}</span>}
                      </div>
                      <div className="flex flex-wrap gap-2 mt-2">
                        {d.link_types.map((lt: any, i: number) => {
                          const key = `${d.id}:${lt.type}`;
                          const selected = key in selectedReady;
                          return (
                            <button
                              key={i}
                              onClick={() => {
                                setSelectedReady(prev => {
                                  if (selected) { const next = { ...prev }; delete next[key]; return next; }
                                  return { ...prev, [key]: { domain_id: d.id, link_type: lt.type, price: lt.price, contact_id: d.contact_id } };
                                });
                              }}
                              onDoubleClick={() => openOrderModal(d, lt.type, lt.price)}
                              className={`px-2 py-1 rounded text-xs transition-colors ${selected ? 'bg-pink-600/15 text-pink-300 ring-1 ring-inset ring-pink-600/30' : 'bg-gray-700 hover:bg-gray-600'}`}
                            >
                              {selected && '✓ '}{lt.type} {lt.price && `($${lt.price})`}{lt.duration && ` / ${lt.duration}mo`}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                    <button
                      type="button"
                      disabled={hidingReadyDomainId === d.id}
                      onClick={() => hideReadyDomain(d.id)}
                      title="Hide this domain from this campaign's ready list only"
                      className="ml-3 inline-flex items-center gap-1 px-2 py-1 rounded text-xs text-gray-400 hover:text-white hover:bg-gray-700 disabled:opacity-50"
                    >
                      <EyeOff className="w-3.5 h-3.5" />
                      {hidingReadyDomainId === d.id ? 'Hiding...' : 'Hide'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === 'orders' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">All Orders ({campaign.orders.length})</h2>
            {campaign.orders.some((o: any) => o.status === 'draft') && (
              <button
                onClick={async () => {
                  if (!confirm(`Process all draft orders in this campaign?\n\nThis will:\n1. Generate articles for all drafts\n2. Send them to publishers\n\nContinue?`)) return;
                  const btn = document.activeElement as HTMLButtonElement;
                  if (btn) {
                    btn.disabled = true;
                    btn.innerText = 'Processing...';
                  }
                  try {
                    const result = await api.processAllDrafts(campaign.id);
                    toast(`Done! Articles: ${result.articles_generated}, Sent: ${result.emails_sent}${result.errors.length > 0 ? `, Errors: ${result.errors.length}` : ''}`);
                    loadCampaign();
                  } catch (e: any) {
                    toast(e.message, 'error');
                  } finally {
                    if (btn) {
                      btn.disabled = false;
                      btn.innerText = 'Process All Drafts';
                    }
                  }
                }}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm font-medium disabled:opacity-50"
              >
                Process All Drafts
              </button>
            )}
          </div>

          {campaign.orders.length === 0 ? (
            <div className="bg-gray-800 rounded-lg border border-gray-700 p-8 text-center">
              <p className="text-gray-500">No orders yet. Create orders from the Ready Domains tab.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {campaign.orders.map((order: any) => {
                const expanded = expandedOrders.has(order.id);
                const allLinks = [
                  ...(order.anchor_text ? [{ id: '__legacy', target_url: order.target_url, anchor_text: order.anchor_text, anchor_type: order.anchor_type, slot: 0 }] : []),
                  ...(order.links || []),
                ];
                const linkCount = allLinks.length;
                return (
                  <div key={order.id} className="bg-gray-800 rounded-lg border border-gray-700">
                    {/* Order header */}
                    <div
                      className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-gray-700/50"
                      onClick={() => {
                        setExpandedOrders(prev => {
                          const next = new Set(prev);
                          expanded ? next.delete(order.id) : next.add(order.id);
                          return next;
                        });
                        if (!expanded && (order.status === 'live' || order.status === 'paid') && !orderChecks[order.id]) {
                          loadOrderChecks(order.id);
                        }
                      }}
                    >
                      <div className="flex items-center gap-4 flex-1 min-w-0">
                        <span className="text-gray-500 text-xs">{expanded ? '▼' : '▶'}</span>
                        <Link to={`/domains/${order.domain_id}`} className="text-pink-400 hover:underline font-medium" onClick={e => e.stopPropagation()}>
                          {order.domain}
                        </Link>
                        <span className="text-sm text-gray-400">{order.link_type}</span>
                        <span className="text-sm">{order.price ? `$${order.price}` : '-'}</span>
                        <StatusPill tone={statusTone(order.status)}>{order.status}</StatusPill>
                        <span className="text-xs text-gray-500">{linkCount} link{linkCount !== 1 ? 's' : ''}</span>
                        {order.live_url && (
                          <a href={order.live_url} target="_blank" rel="noopener" className="text-pink-400 hover:underline text-xs flex items-center gap-1" onClick={e => e.stopPropagation()}>
                            Live <ExternalLink className="w-3 h-3" />
                          </a>
                        )}
                        {order.status === 'paid' && <CheckCircle className="w-4 h-4 text-green-400" />}
                        {['published', 'paid', 'live'].includes(order.status) && order.last_checked_at && (
                          <span className="text-xs text-gray-600" title={`Last check: ${order.last_checked_at}`}>
                            checked {new Date(order.last_checked_at).toLocaleDateString()}
                            {order.last_check_status && (
                              <span className={isVerificationOk(order.last_check_status) ? 'text-green-500 ml-1' : 'text-red-400 ml-1'}>
                                {isVerificationOk(order.last_check_status) ? '✓' : '✗'}
                              </span>
                            )}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={async (e) => {
                            e.stopPropagation();
                            setAddLinkModal({ order_id: order.id, domain: order.domain });
                            setLinkForm({ target_url: '', anchor_text: '', anchor_text_id: '', anchor_type: '', article_topic: order.article_topic || '' });
                            const campaignSiteId = campaign.target_site_id;
                            if (campaignSiteId) {
                              setSelectedSiteId(campaignSiteId);
                              try {
                                const siteData = await api.getTargetSite(campaignSiteId);
                                let suggestion = null;
                                try { const s = await api.suggestAnchor(campaignSiteId); suggestion = s.suggestion; } catch {}
                                setAnchorPool({ urls: siteData.urls, suggestion, site: { id: siteData.id, name: siteData.name, domain: siteData.domain } });
                              } catch { setAnchorPool(null); }
                            }
                          }}
                          className="text-gray-500 hover:text-pink-400"
                          title="Add link"
                        >
                          <Plus className="w-4 h-4" />
                        </button>
                        <button
                          onClick={async (e) => {
                            e.stopPropagation();
                            if (!confirm(`Remove ${order.domain} (${order.link_type}) from this campaign?`)) return;
                            try { await api.deleteOrder(order.id); toast('Order removed'); loadCampaign(); } catch (e: any) { toast(e.message, 'error'); }
                          }}
                          className="text-gray-500 hover:text-red-400"
                          title="Remove order"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>

                    {/* Expanded */}
                    {expanded && (
                      <div className="px-4 pb-3 border-t border-gray-700 space-y-3">
                        {allLinks.length === 0 ? (
                          <p className="text-gray-500 text-sm py-2">No links assigned. Click + to add anchors and target URLs.</p>
                        ) : (
                          <div className="space-y-1 mt-2">
                            {allLinks.map((link: any, i: number) => (
                              <div key={link.id} className="flex items-center gap-3 text-sm py-1 px-2 rounded hover:bg-gray-700/30">
                                <span className="text-gray-600 text-xs w-4">{i + 1}</span>
                                <span className={`px-1.5 py-0.5 rounded text-xs ${anchorColors[link.anchor_type] || 'bg-gray-600'}`}>{link.anchor_type}</span>
                                <span className="font-medium">{link.anchor_text}</span>
                                <span className="text-gray-500">→</span>
                                <span className="text-gray-400 truncate text-xs">{link.target_url || '-'}</span>
                                <div className="ml-auto">
                                  {link.id !== '__legacy' && (
                                    <button onClick={async () => {
                                      try { await api.deleteOrderLink(link.id); toast('Link removed'); loadCampaign(); } catch (e: any) { toast(e.message, 'error'); }
                                    }} aria-label="Remove link" className="text-gray-600 hover:text-red-400">
                                      <Trash2 className="w-3 h-3" />
                                    </button>
                                  )}
                                </div>
                              </div>
                            ))}
                          </div>
                        )}

                        {/* Live URL display */}
                        {order.live_url && (
                          <div className="flex items-center gap-2 text-sm bg-emerald-900/20 border border-emerald-700 rounded p-2">
                            <ExternalLink className="w-4 h-4 text-emerald-400" />
                            <span className="text-gray-400">Live URL:</span>
                            <a href={order.live_url} target="_blank" rel="noopener" className="text-emerald-400 hover:underline truncate">{order.live_url}</a>
                          </div>
                        )}

                        {/* Verification History */}
                        {orderChecks[order.id] && orderChecks[order.id].length > 0 && (
                          <div className="bg-gray-900/50 rounded p-3 border border-gray-600">
                            <h4 className="text-xs font-medium text-gray-400 mb-2">Verification History</h4>
                            <div className="space-y-1">
                              {orderChecks[order.id].map((check: any) => (
                                <div key={check.id} className="flex items-center gap-3 text-xs">
                                  <span className={`w-2 h-2 rounded-full ${isVerificationOk(check.status) ? 'bg-green-400' : 'bg-red-400'}`} />
                                  <span className="text-gray-500">{check.checked_at ? new Date(check.checked_at).toLocaleString() : '-'}</span>
                                  <span className={isVerificationOk(check.status) ? 'text-green-400' : 'text-red-400'}>{check.status}</span>
                                  {check.http_status && <span className="text-gray-600">HTTP {check.http_status}</span>}
                                  {check.notes && <span className="text-gray-500 truncate">{check.notes}</span>}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Article Preview */}
                        {order.article_content && (
                          <div className="mt-3 bg-gray-900/50 rounded p-3 border border-gray-600">
                            <div className="flex items-center justify-between mb-2">
                              <span className="text-xs font-medium text-gray-400">Article Content</span>
                              <span className="text-xs text-gray-500">
                                {order.article_content.split(' ').length} words
                                {order.images && order.images.length > 0 && ` • ${order.images.length} images`}
                              </span>
                            </div>
                            <div
                              onClick={() => openArticleModal(order)}
                              className="text-xs text-gray-400 cursor-pointer hover:text-pink-400 transition-colors"
                            >
                              {order.article_content.substring(0, 150).replace(/^TITLE:.*?\n\n?/, '')}... <span className="text-pink-400 font-medium">Click to expand ▸</span>
                            </div>
                          </div>
                        )}

                        {/* Article Generation Settings */}
                        {['draft', 'content_ready'].includes(order.status) && (
                          <div className="mt-3 bg-gray-900/60 rounded-lg p-3 border border-gray-700/50" onClick={e => e.stopPropagation()}>
                            <div className="text-xs font-semibold text-gray-300 mb-3 flex items-center gap-1.5">
                              <Settings className="w-3.5 h-3.5 text-pink-400" />
                              Article Settings
                            </div>
                            <div className="space-y-3">
                              {/* Content Row */}
                              <div className="flex flex-wrap gap-4">
                                <div className="flex flex-col gap-1">
                                  <span className="text-[10px] uppercase tracking-wider text-gray-500 font-medium">Max Words</span>
                                  <input type="number" defaultValue={order.max_words || ''} placeholder="1200"
                                    onBlur={async (e) => { const v = e.target.value ? parseInt(e.target.value) : null; try { await api.updateOrder(order.id, { max_words: v }); } catch {} }}
                                    className="w-20 px-2.5 py-1.5 bg-gray-800 border border-gray-600 rounded-md text-xs text-white focus:outline-none focus:border-pink-500 focus:ring-1 focus:ring-pink-500/30 transition-colors" />
                                </div>
                                <div className="flex flex-col gap-1">
                                  <span className="text-[10px] uppercase tracking-wider text-gray-500 font-medium">Resource Links</span>
                                  <input type="number" defaultValue={order.resource_links_count || ''} placeholder="3" min="0" max="10"
                                    onBlur={async (e) => { const v = e.target.value ? parseInt(e.target.value) : null; try { await api.updateOrder(order.id, { resource_links_count: v }); } catch {} }}
                                    className="w-14 px-2.5 py-1.5 bg-gray-800 border border-gray-600 rounded-md text-xs text-white focus:outline-none focus:border-pink-500 focus:ring-1 focus:ring-pink-500/30 transition-colors" />
                                </div>
                                <div className="flex flex-col gap-1">
                                  <span className="text-[10px] uppercase tracking-wider text-gray-500 font-medium">Brand Scope</span>
                                  {(() => { const draft = getOrderBrandDraft(order); return (
                                  <select
                                    value={draft.brand_mentions_scope}
                                    onChange={async (e) => { await updateOrderBrandDraft(order, { brand_mentions_scope: e.target.value }); }}
                                    className="w-24 px-2.5 py-1.5 bg-gray-800 border border-gray-600 rounded-md text-xs text-white focus:outline-none focus:border-pink-500 focus:ring-1 focus:ring-pink-500/30 transition-colors"
                                  >
                                    <option value="">Off</option>
                                    <option value="any">Any</option>
                                    <option value="all">All</option>
                                  </select>
                                  ); })()}
                                </div>
                                <div className="flex flex-col gap-1">
                                  <span className="text-[10px] uppercase tracking-wider text-gray-500 font-medium">Brand Mentions</span>
                                  {(() => { const draft = getOrderBrandDraft(order); return (
                                  <input type="number" value={draft.brand_mentions_body_count} placeholder="2" min="1" max="20"
                                    onChange={async (e) => { await updateOrderBrandDraft(order, { brand_mentions_body_count: e.target.value }); }}
                                    className="w-16 px-2.5 py-1.5 bg-gray-800 border border-gray-600 rounded-md text-xs text-white focus:outline-none focus:border-pink-500 focus:ring-1 focus:ring-pink-500/30 transition-colors" />
                                  ); })()}
                                </div>
                                <div className="flex flex-col gap-1 min-w-[210px]">
                                  <span className="text-[10px] uppercase tracking-wider text-gray-500 font-medium">Specific Brands</span>
                                  {(() => { const draft = getOrderBrandDraft(order); return (
                                  <input
                                    type="text"
                                    value={draft.brand_mentions_brands}
                                    placeholder="CamHours, WebcamChamps"
                                    onChange={async (e) => { await updateOrderBrandDraft(order, { brand_mentions_brands: e.target.value }); }}
                                    className="px-2.5 py-1.5 bg-gray-800 border border-gray-600 rounded-md text-xs text-white focus:outline-none focus:border-pink-500 focus:ring-1 focus:ring-pink-500/30 transition-colors"
                                  />
                                  ); })()}
                                </div>
                              </div>
                              {/* Toggles Row */}
                              <div className="flex flex-wrap gap-x-4 gap-y-2">
                                {[
                                  { key: 'skip_resource_links', label: 'No resource links', val: order.skip_resource_links },
                                  { key: 'nofollow_target', label: 'Nofollow target', val: order.nofollow_target },
                                  { key: 'nofollow_resources', label: 'Nofollow resources', val: order.nofollow_resources },
                                  { key: 'brand_mentions_in_title', label: 'Brand in title', val: getOrderBrandDraft(order).brand_mentions_in_title },
                                ].map(opt => (
                                  <label key={opt.key} className="relative flex items-center gap-2 text-xs text-gray-400 cursor-pointer group select-none">
                                    <div className="relative">
                                      {opt.key === 'brand_mentions_in_title' ? (
                                        <input type="checkbox" checked={!!opt.val}
                                          onChange={async (e) => { await updateOrderBrandDraft(order, { brand_mentions_in_title: e.target.checked }); }}
                                          className="sr-only peer" />
                                      ) : (
                                        <input type="checkbox" defaultChecked={!!opt.val}
                                          onChange={async (e) => { try { await api.updateOrder(order.id, { [opt.key]: e.target.checked }); } catch {} }}
                                          className="sr-only peer" />
                                      )}
                                      <div className="w-8 h-[18px] bg-gray-700 rounded-full peer-checked:bg-pink-600 transition-colors" />
                                      <div className="absolute top-[2px] left-[2px] w-[14px] h-[14px] bg-gray-400 rounded-full peer-checked:translate-x-[14px] peer-checked:bg-white transition-all" />
                                    </div>
                                    <span className="group-hover:text-gray-300 transition-colors">{opt.label}</span>
                                  </label>
                                ))}
                              </div>
                            </div>
                          </div>
                        )}

                        {/* Action Buttons */}
                        <div className="flex items-center gap-2 pt-2 border-t border-gray-600 flex-wrap">
                          {order.status === 'pending_review' && (
                            <>
                              <button
                                onClick={async (e) => {
                                  e.stopPropagation();
                                  try {
                                    await api.approveOrder(order.id);
                                    toast('Order approved and sent!');
                                    loadCampaign();
                                  } catch (e: any) { toast(e.message, 'error'); }
                                }}
                                className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 rounded text-xs font-medium"
                              >
                                Approve
                              </button>
                              <button
                                onClick={async (e) => {
                                  e.stopPropagation();
                                  try {
                                    await api.rejectOrder(order.id);
                                    toast('Order rejected');
                                    loadCampaign();
                                  } catch (e: any) { toast(e.message, 'error'); }
                                }}
                                className="px-3 py-1.5 bg-red-600 hover:bg-red-700 rounded text-xs font-medium"
                              >
                                Reject
                              </button>
                            </>
                          )}
                          {order.status === 'draft' && (
                            <button
                              onClick={async (e) => {
                                e.stopPropagation();
                                const btn = e.currentTarget;
                                btn.disabled = true;
                                btn.innerText = 'Generating...';
                                try {
                                  // Prompt for language before generating
                                  const domainData = await api.getDomain(order.domain_id);
                                  const defaultLang = domainData?.language || 'English';
                                  const lang = prompt(`Article language:`, defaultLang);
                                  if (!lang) { btn.disabled = false; btn.innerText = 'Generate Article'; return; }
                                  // Update domain language if changed
                                  if (lang !== defaultLang && domainData) {
                                    await api.updateDomain(domainData.id, { language: lang });
                                  }
                                  const brandDraft = getOrderBrandDraft(order);
                                  const result = await api.generateArticle(order.id, {
                                    brand_mentions_scope: brandDraft.brand_mentions_scope ? (brandDraft.brand_mentions_scope as 'any' | 'all') : undefined,
                                    brand_mentions_brands: brandDraft.brand_mentions_brands || undefined,
                                    brand_mentions_in_title: !!brandDraft.brand_mentions_in_title,
                                    brand_mentions_body_count: brandDraft.brand_mentions_body_count ? parseInt(brandDraft.brand_mentions_body_count) : undefined,
                                  });
                                  toast(`Article generated (${result.word_count} words, ${lang})`);
                                  loadCampaign();
                                } catch (e: any) {
                                  toast(e.message, 'error');
                                } finally {
                                  btn.disabled = false;
                                  btn.innerText = 'Generate Article';
                                }
                              }}
                              className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded text-xs font-medium disabled:opacity-50"
                            >
                              Generate Article
                            </button>
                          )}
                          {order.status === 'content_ready' && (
                            <>
                              <button
                                onClick={async (e) => {
                                  e.stopPropagation();
                                  const btn = e.currentTarget;
                                  btn.disabled = true;
                                  btn.innerText = 'Regenerating...';
                                  try {
                                    const domainData = await api.getDomain(order.domain_id);
                                    const defaultLang = domainData?.language || 'English';
                                    const lang = prompt(`Article language:`, defaultLang);
                                    if (!lang) { btn.disabled = false; btn.innerText = 'Regenerate Article'; return; }
                                    if (lang !== defaultLang && domainData) {
                                      await api.updateDomain(domainData.id, { language: lang });
                                    }
                                    const brandDraft = getOrderBrandDraft(order);
                                    const result = await api.generateArticle(order.id, {
                                      brand_mentions_scope: brandDraft.brand_mentions_scope ? (brandDraft.brand_mentions_scope as 'any' | 'all') : undefined,
                                      brand_mentions_brands: brandDraft.brand_mentions_brands || undefined,
                                      brand_mentions_in_title: !!brandDraft.brand_mentions_in_title,
                                      brand_mentions_body_count: brandDraft.brand_mentions_body_count ? parseInt(brandDraft.brand_mentions_body_count) : undefined,
                                    });
                                    toast(`Article regenerated (${result.word_count} words, ${lang})`);
                                    loadCampaign();
                                  } catch (e: any) {
                                    toast(e.message, 'error');
                                  } finally {
                                    btn.disabled = false;
                                    btn.innerText = 'Regenerate Article';
                                  }
                                }}
                                className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded text-xs font-medium disabled:opacity-50"
                              >
                                Regenerate Article
                              </button>
                              <button
                                onClick={async (e) => {
                                  e.stopPropagation();
                                  if (!confirm('Dismiss this article and reset to draft?')) return;
                                  try {
                                    await api.updateOrder(order.id, { article_content: null, status: 'draft' });
                                    toast('Article dismissed');
                                    loadCampaign();
                                  } catch (e: any) {
                                    toast(e.message, 'error');
                                  }
                                }}
                                className="px-3 py-1.5 bg-gray-600 hover:bg-gray-700 rounded text-xs font-medium"
                              >
                                Dismiss Article
                              </button>
                              <button
                                onClick={async (e) => {
                                  e.stopPropagation();
                                  const btn = e.currentTarget;
                                  btn.disabled = true;
                                  btn.innerText = 'Sending...';
                                  try {
                                    const result = await api.sendOrder(order.id);
                                    toast(`Sent to ${result.sent_to}`);
                                    loadCampaign();
                                  } catch (e: any) {
                                    toast(e.message, 'error');
                                  } finally {
                                    btn.disabled = false;
                                    btn.innerText = 'Send to Publisher';
                                  }
                                }}
                                className="px-3 py-1.5 bg-green-600 hover:bg-green-700 rounded text-xs font-medium disabled:opacity-50"
                              >
                                Send to Publisher
                              </button>
                            </>
                          )}
                          {order.status === 'sent' && (
                            <>
                              <button
                                onClick={async (e) => {
                                  e.stopPropagation();
                                  if (!confirm('Resend the article to the publisher?')) return;
                                  const btn = e.currentTarget;
                                  btn.disabled = true;
                                  btn.innerText = 'Sending...';
                                  try {
                                    const result = await api.sendOrder(order.id);
                                    toast(`Resent to ${result.sent_to}`);
                                    loadCampaign();
                                  } catch (e: any) {
                                    toast(e.message, 'error');
                                  } finally {
                                    btn.disabled = false;
                                    btn.innerText = 'Resend Article';
                                  }
                                }}
                                className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded text-xs font-medium"
                              >
                                Resend Article
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setVerifyModal({ order_id: order.id, domain: order.domain });
                                  setVerifyUrl('');
                                }}
                                className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 rounded text-xs font-medium"
                              >
                                Verify Live URL
                              </button>
                            </>
                          )}
                          {['draft', 'content_ready', 'sent'].includes(order.status) && (
                            <button
                              onClick={async (e) => {
                                e.stopPropagation();
                                if (!confirm('Mark payment as sent for this order? Status will change to "payment_sent".')) return;
                                const btn = e.currentTarget;
                                btn.disabled = true;
                                btn.innerText = 'Marking...';
                                try {
                                  const result = await api.markPaymentSent(order.id);
                                  toast(result.email_sent ? `💸 Payment marked as sent — email sent to ${result.email_to}` : '💸 Payment marked as sent (no contact email found)');
                                  loadCampaign();
                                } catch (e: any) {
                                  toast(e.message, 'error');
                                } finally {
                                  btn.disabled = false;
                                  btn.innerText = 'Mark Payment Sent';
                                }
                              }}
                              className="px-3 py-1.5 bg-teal-600 hover:bg-teal-700 rounded text-xs font-medium disabled:opacity-50"
                            >
                              Mark Payment Sent
                            </button>
                          )}
                          {order.status === 'payment_sent' && (
                            <>
                              <span className="text-xs text-teal-400 flex items-center gap-1">
                                💸 Payment sent
                                {order.payment_sent_at && <span className="text-gray-500 ml-1">({new Date(order.payment_sent_at).toLocaleDateString()})</span>}
                              </span>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setVerifyModal({ order_id: order.id, domain: order.domain });
                                  setVerifyUrl('');
                                }}
                                className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 rounded text-xs font-medium"
                              >
                                Verify Live URL
                              </button>
                            </>
                          )}
                          {order.status === 'live' && (
                            <>
                              <span className="text-xs text-emerald-400">✓ Live</span>
                              <button
                                onClick={async (e) => {
                                  e.stopPropagation();
                                  if (!confirm('Confirm payment for this order? This will send a confirmation email.')) return;
                                  try {
                                    await api.confirmPayment(order.id);
                                    toast('💰 Payment confirmed & email sent');
                                    loadCampaign();
                                  } catch (e: any) {
                                    toast(e.message, 'error');
                                  }
                                }}
                                className="px-3 py-1.5 bg-orange-600 hover:bg-orange-700 rounded text-xs font-medium"
                              >
                                Confirm Payment
                              </button>
                            </>
                          )}
                          {order.status === 'paid' && (
                            <span className="text-xs text-green-400 flex items-center gap-1">
                              <CheckCircle className="w-3.5 h-3.5" /> Paid
                              {order.paid_at && <span className="text-gray-500 ml-1">({new Date(order.paid_at).toLocaleDateString()})</span>}
                            </span>
                          )}
                          {order.status === 'rejected' && (
                            <span className="text-xs text-red-400">✗ Rejected</span>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Add Target Modal */}
      <Modal open={targetModal} onClose={() => setTargetModal(false)} title="Add Target URL">
        <form onSubmit={handleAddTarget} className="space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-2">Target URL *</label>
            <input
              type="url"
              value={targetForm.url}
              onChange={(e) => setTargetForm({ ...targetForm, url: e.target.value })}
              placeholder="https://camhours.com/girls"
              required
              className={ic}
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-2">Brand Name *</label>
            <input
              type="text"
              value={targetForm.brand_name}
              onChange={(e) => setTargetForm({ ...targetForm, brand_name: e.target.value })}
              placeholder="CamHours"
              required
              className={ic}
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-2">Description</label>
            <input
              type="text"
              value={targetForm.description}
              onChange={(e) => setTargetForm({ ...targetForm, description: e.target.value })}
              placeholder="For toplist descriptors (optional)"
              className={ic}
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-2">Priority</label>
            <input
              type="number"
              min="1"
              value={targetForm.priority}
              onChange={(e) => setTargetForm({ ...targetForm, priority: parseInt(e.target.value) })}
              className={ic}
            />
          </div>
          <div className="flex justify-end gap-3 mt-6">
            <button type="button" onClick={() => setTargetModal(false)} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm">Cancel</button>
            <button type="submit" className="px-4 py-2 bg-pink-600 hover:bg-pink-700 rounded-lg text-sm font-medium">Add Target</button>
          </div>
        </form>
      </Modal>

      {/* Edit Campaign Modal */}
      <Modal open={editModal} onClose={() => setEditModal(false)} title="Edit Campaign">
        <form onSubmit={handleUpdateCampaign} className="space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-2">Campaign Name</label>
            <input type="text" value={editForm.name} onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} required className={ic} />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-2">Target Site</label>
            <input type="text" value={editForm.target_site} onChange={(e) => setEditForm({ ...editForm, target_site: e.target.value })} required className={ic} />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-2">Status</label>
            <select value={editForm.status} onChange={(e) => setEditForm({ ...editForm, status: e.target.value })} className={ic}>
              <option value="active">Active</option>
              <option value="paused">Paused</option>
              <option value="completed">Completed</option>
            </select>
          </div>

          {/* Mode Selection */}
          <div>
            <label className="block text-sm text-gray-400 mb-2">Campaign Mode</label>
            <div className="flex gap-2">
              <button type="button" onClick={() => setEditForm({ ...editForm, mode: 'manual' })}
                className={`flex-1 px-3 py-2 rounded-lg border text-sm font-medium transition-colors ${editForm.mode === 'manual' ? 'border-pink-500 bg-pink-600/15 text-white' : 'border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600'}`}>
                Manual
              </button>
              <button type="button" onClick={() => setEditForm({ ...editForm, mode: 'auto' })}
                className={`flex-1 px-3 py-2 rounded-lg border text-sm font-medium transition-colors flex items-center justify-center gap-1.5 ${editForm.mode === 'auto' ? 'border-emerald-500 bg-emerald-600/20 text-white' : 'border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600'}`}>
                <Zap className="w-4 h-4" />Auto
              </button>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-2">Budget (USD)</label>
              <input type="number" step="0.01" value={editForm.budget} onChange={(e) => setEditForm({ ...editForm, budget: e.target.value })} className={ic} />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-2">Spent (USD)</label>
              <input type="number" step="0.01" value={editForm.spent} onChange={(e) => setEditForm({ ...editForm, spent: parseFloat(e.target.value) })} className={ic} />
            </div>
          </div>

          {/* Auto Mode Settings */}
          {editForm.mode === 'auto' && (
            <div className="space-y-4 border-t border-gray-700 pt-4">
              <div>
                <button type="button" onClick={() => setShowEditFilters(!showEditFilters)} className="flex items-center gap-2 text-sm font-medium text-gray-300 hover:text-white w-full">
                  {showEditFilters ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  Domain Filters
                </button>
                {showEditFilters && (
                  <div className="mt-3 space-y-3 bg-gray-900/50 rounded-lg p-3">
                    <div className="grid grid-cols-2 gap-3">
                      <div><label className="block text-xs text-gray-500 mb-1">Traffic Min</label><input type="number" value={editForm.filter_traffic_min} onChange={e => setEditForm({ ...editForm, filter_traffic_min: e.target.value })} placeholder="0" className={ic} /></div>
                      <div><label className="block text-xs text-gray-500 mb-1">Traffic Max</label><input type="number" value={editForm.filter_traffic_max} onChange={e => setEditForm({ ...editForm, filter_traffic_max: e.target.value })} placeholder="∞" className={ic} /></div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div><label className="block text-xs text-gray-500 mb-1">DR Min</label><input type="number" value={editForm.filter_dr_min} onChange={e => setEditForm({ ...editForm, filter_dr_min: e.target.value })} className={ic} /></div>
                      <div><label className="block text-xs text-gray-500 mb-1">DR Max</label><input type="number" value={editForm.filter_dr_max} onChange={e => setEditForm({ ...editForm, filter_dr_max: e.target.value })} className={ic} /></div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div><label className="block text-xs text-gray-500 mb-1">Price Min ($)</label><input type="number" step="0.01" value={editForm.filter_price_min} onChange={e => setEditForm({ ...editForm, filter_price_min: e.target.value })} className={ic} /></div>
                      <div><label className="block text-xs text-gray-500 mb-1">Price Max ($)</label><input type="number" step="0.01" value={editForm.filter_price_max} onChange={e => setEditForm({ ...editForm, filter_price_max: e.target.value })} className={ic} /></div>
                    </div>
                    <div><label className="block text-xs text-gray-500 mb-1">Niche Tags</label><input type="text" value={editForm.filter_niche_tags} onChange={e => setEditForm({ ...editForm, filter_niche_tags: e.target.value })} placeholder="comma-separated" className={ic} /></div>
                    <div><label className="block text-xs text-gray-500 mb-1">Link Type</label>
                      <select value={editForm.filter_link_type} onChange={e => setEditForm({ ...editForm, filter_link_type: e.target.value })} className={ic}>
                        <option value="">Any</option>
                        {LINK_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                      </select>
                    </div>
                  </div>
                )}
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-2">Link Velocity</label>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-gray-400">Build</span>
                  <input type="number" min="1" value={editForm.velocity_count} onChange={e => setEditForm({ ...editForm, velocity_count: e.target.value })} className="w-16 px-2 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-pink-500 text-center" />
                  <span className="text-sm text-gray-400">link(s) every</span>
                  <input type="number" min="1" value={editForm.velocity_period_days} onChange={e => setEditForm({ ...editForm, velocity_period_days: e.target.value })} className="w-16 px-2 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-pink-500 text-center" />
                  <span className="text-sm text-gray-400">days</span>
                </div>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-2">Total Budget ($)</label>
                <input type="number" step="0.01" value={editForm.budget_total} onChange={e => setEditForm({ ...editForm, budget_total: e.target.value })} placeholder="Auto-pauses when reached" className={ic} />
              </div>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm text-gray-400">Enable Scheduling</label>
                  <button type="button" onClick={() => setEditForm({ ...editForm, schedule_enabled: !editForm.schedule_enabled })}
                    className={`w-10 h-5 rounded-full transition-colors relative ${editForm.schedule_enabled ? 'bg-emerald-600' : 'bg-gray-600'}`}>
                    <div className={`w-4 h-4 bg-white rounded-full absolute top-0.5 transition-transform ${editForm.schedule_enabled ? 'translate-x-5' : 'translate-x-0.5'}`} />
                  </button>
                </div>
                {editForm.schedule_enabled && (
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-gray-400">Check every</span>
                    <input type="number" min="1" value={editForm.schedule_interval_hours} onChange={e => setEditForm({ ...editForm, schedule_interval_hours: e.target.value })} className="w-16 px-2 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-pink-500 text-center" />
                    <span className="text-sm text-gray-400">hours</span>
                  </div>
                )}
              </div>
            </div>
          )}

          <div>
            <label className="block text-sm text-gray-400 mb-2">Notes</label>
            <textarea value={editForm.notes} onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })} rows={3} className={ic} />
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-3">Anchor Distribution Targets (%)</label>
            <div className="grid grid-cols-2 gap-3">
              <div><label className="block text-xs text-gray-500 mb-1">Brand</label><input type="number" min="0" max="100" value={editForm.anchor_brand_pct} onChange={(e) => setEditForm({ ...editForm, anchor_brand_pct: parseInt(e.target.value) })} className={ic} /></div>
              <div><label className="block text-xs text-gray-500 mb-1">Generic</label><input type="number" min="0" max="100" value={editForm.anchor_generic_pct} onChange={(e) => setEditForm({ ...editForm, anchor_generic_pct: parseInt(e.target.value) })} className={ic} /></div>
              <div><label className="block text-xs text-gray-500 mb-1">Topical</label><input type="number" min="0" max="100" value={editForm.anchor_topical_pct} onChange={(e) => setEditForm({ ...editForm, anchor_topical_pct: parseInt(e.target.value) })} className={ic} /></div>
              <div><label className="block text-xs text-gray-500 mb-1">Exact</label><input type="number" min="0" max="100" value={editForm.anchor_exact_pct} onChange={(e) => setEditForm({ ...editForm, anchor_exact_pct: parseInt(e.target.value) })} className={ic} /></div>
            </div>
          </div>

          <div className="flex justify-end gap-3 mt-6">
            <button type="button" onClick={() => setEditModal(false)} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm">Cancel</button>
            <button type="submit" className="px-4 py-2 bg-pink-600 hover:bg-pink-700 rounded-lg text-sm font-medium">Save Changes</button>
          </div>
        </form>
      </Modal>

      {/* Verify URL Modal */}
      {verifyModal && (
        <Modal open={!!verifyModal} onClose={() => setVerifyModal(null)} title={`Verify: ${verifyModal.domain}`}>
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-2">Published Article URL</label>
              <input
                type="url"
                value={verifyUrl}
                onChange={e => setVerifyUrl(e.target.value)}
                placeholder="https://example.com/your-guest-post"
                className={ic}
                autoFocus
              />
            </div>
            <div className="flex justify-end gap-3">
              <button onClick={() => setVerifyModal(null)} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm">Cancel</button>
              <button
                onClick={async () => {
                  if (!verifyUrl) { toast('Enter a URL', 'error'); return; }
                  try {
                    const result = await api.verifyOrder(verifyModal.order_id, verifyUrl);
                    if (result.verified) {
                      toast(`Verified live: ${result.live_url}`);
                    } else {
                      const reason = result.reason || result.status || (result.issues?.join(', ')) || 'Unknown error';
                      toast(`Verification failed: ${reason}`, 'error');
                    }
                    setVerifyModal(null);
                    loadCampaign();
                  } catch (e: any) { toast(e.message || 'Request failed — server may be down', 'error'); }
                }}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 rounded-lg text-sm font-medium"
              >
                Verify
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Add Link to Order Modal */}
      {addLinkModal && (
        <Modal open={!!addLinkModal} onClose={() => { setAddLinkModal(null); setAnchorPool(null); setSelectedSiteId(''); }} title={`Add Link: ${addLinkModal.domain}`}>
          <div className="space-y-4">
            {allTargetSites.length > 0 && (
              <div>
                <label className="block text-sm text-gray-400 mb-1">Target Site</label>
                <select
                  value={selectedSiteId}
                  onChange={async (e) => {
                    const siteId = e.target.value;
                    setSelectedSiteId(siteId);
                    if (!siteId) { setAnchorPool(null); return; }
                    try {
                      const siteData = await api.getTargetSite(siteId);
                      let suggestion = null;
                      try { const s = await api.suggestAnchor(siteId); suggestion = s.suggestion; } catch {}
                      setAnchorPool({ urls: siteData.urls, suggestion, site: { id: siteData.id, name: siteData.name, domain: siteData.domain } });
                    } catch { setAnchorPool(null); }
                  }}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-sm"
                >
                  <option value="">Select target site...</option>
                  {allTargetSites.map(s => (
                    <option key={s.id} value={s.id}>{s.name} ({s.domain})</option>
                  ))}
                </select>
              </div>
            )}

            {anchorPool?.urls?.length > 0 && (
              <div>
                <label className="block text-sm text-gray-400 mb-2">
                  Pick from {anchorPool.site?.name || 'Anchor Pool'}
                </label>
                {anchorPool.suggestion && (
                  <div className="bg-gray-800 border border-gray-700 rounded p-2 mb-2 text-xs">
                    <span className="text-gray-400">Suggested: </span>
                    <button type="button" onClick={() => setLinkForm({
                      anchor_text: anchorPool.suggestion.text, anchor_text_id: anchorPool.suggestion.anchor_id,
                      anchor_type: anchorPool.suggestion.anchor_type, target_url: anchorPool.suggestion.target_url, article_topic: '',
                    })} className="text-teal-300 hover:text-white font-medium">
                      "{anchorPool.suggestion.text}" <span className={`px-1 py-0.5 rounded text-xs ml-1 ${anchorColors[anchorPool.suggestion.anchor_type] || 'bg-gray-600'}`}>{anchorPool.suggestion.anchor_type}</span>
                    </button>
                  </div>
                )}
                <div className="max-h-40 overflow-auto space-y-2">
                  {anchorPool.urls.map((u: any) => (
                    <div key={u.id} className="text-xs">
                      <div className="text-gray-500 mb-1 truncate">{u.url}</div>
                      <div className="flex flex-wrap gap-1">
                        {u.anchors.map((a: any) => {
                          const selected = linkForm.anchor_text_id === a.id;
                          return (
                            <button key={a.id} type="button" onClick={() => setLinkForm({
                              anchor_text: a.text, anchor_text_id: a.id, anchor_type: a.anchor_type, target_url: u.url, article_topic: '',
                            })} className={`px-2 py-0.5 rounded transition-all ${anchorColors[a.anchor_type] || 'bg-gray-600'} ${selected ? 'ring-2 ring-white/80' : 'hover:ring-1 ring-white/30'}`}>
                              {a.text} {a.times_used > 0 && <span className="opacity-60">({a.times_used})</span>}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div>
              <label className="block text-sm text-gray-400 mb-1">Anchor Text</label>
              <input value={linkForm.anchor_text} onChange={e => setLinkForm(f => ({ ...f, anchor_text: e.target.value, anchor_text_id: '' }))} className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-sm" placeholder="Type or pick from pool" />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Target URL</label>
              <input value={linkForm.target_url} onChange={e => setLinkForm(f => ({ ...f, target_url: e.target.value }))} className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-sm" placeholder="https://..." />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Article Topic <span className="text-gray-600">(optional)</span></label>
              <input value={linkForm.article_topic} onChange={e => setLinkForm(f => ({ ...f, article_topic: e.target.value }))} className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-sm" placeholder="e.g. Best cam sites for beginners in 2026" />
              <p className="text-xs text-gray-600 mt-1">Sets the topic/angle for the generated article</p>
            </div>

            <div className="flex justify-end gap-3">
              <button onClick={() => { setAddLinkModal(null); setAnchorPool(null); setSelectedSiteId(''); }} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm">Cancel</button>
              <button
                onClick={async () => {
                  if (!linkForm.anchor_text || !linkForm.target_url) { toast('Anchor text and URL required', 'error'); return; }
                  try {
                    await api.addOrderLink(addLinkModal.order_id, {
                      target_url: linkForm.target_url,
                      anchor_text: linkForm.anchor_text,
                      anchor_text_id: linkForm.anchor_text_id || null,
                      article_topic: linkForm.article_topic || null,
                    });
                    toast('Link added');
                    setAddLinkModal(null);
                    setAnchorPool(null);
                    setSelectedSiteId('');
                    loadCampaign();
                  } catch (e: any) { toast(e.message, 'error'); }
                }}
                className="px-4 py-2 bg-pink-600 hover:bg-pink-700 rounded text-sm font-medium"
              >Add Link</button>
            </div>
          </div>
        </Modal>
      )}

      {/* Create Order Modal */}
      {orderModal && (
        <Modal
          open={!!orderModal}
          onClose={() => { setOrderModal(null); setAnchorPool(null); }}
          title={`Create Order: ${orderModal.domain.domain}`}
        >
          <form onSubmit={handleCreateOrder} className="space-y-4">
            <div className="flex gap-4">
              <div className="flex-1">
                <label className="block text-sm text-gray-400 mb-1">Link Type</label>
                <input type="text" value={orderModal.link_type} readOnly className={ic} />
              </div>
              <div className="w-32">
                <label className="block text-sm text-gray-400 mb-1">Price (USD)</label>
                <input type="number" step="0.01" value={orderModal.price} onChange={(e) => setOrderModal({ ...orderModal, price: e.target.value })} className={ic} />
              </div>
            </div>

            {anchorPool?.urls?.length > 0 ? (
              <div>
                <label className="block text-sm text-gray-400 mb-2">Pick Anchor from Pool</label>
                {anchorPool.suggestion && (
                  <div className="bg-gray-800 border border-gray-700 rounded p-2 mb-2 text-xs">
                    <span className="text-gray-400">Suggested: </span>
                    <button type="button" onClick={() => setOrderModal((m: any) => ({
                      ...m, anchor_text: anchorPool.suggestion.text, anchor_text_id: anchorPool.suggestion.anchor_id,
                      anchor_type: anchorPool.suggestion.anchor_type, target_url: anchorPool.suggestion.target_url,
                    }))} className="text-teal-300 hover:text-white font-medium">
                      "{anchorPool.suggestion.text}" <span className={`px-1 py-0.5 rounded text-xs ml-1 ${({'brand':'bg-blue-600','topical':'bg-teal-600','generic':'bg-gray-600','exact':'bg-green-600','url':'bg-yellow-600'} as any)[anchorPool.suggestion.anchor_type] || 'bg-gray-600'}`}>{anchorPool.suggestion.anchor_type}</span>
                    </button>
                    <span className="text-gray-500 ml-1">→ {anchorPool.suggestion.target_url}</span>
                  </div>
                )}
                <div className="max-h-48 overflow-auto space-y-2">
                  {anchorPool.urls.map((u: any) => (
                    <div key={u.id} className="text-xs">
                      <div className="text-gray-500 mb-1 truncate">{u.url}</div>
                      <div className="flex flex-wrap gap-1">
                        {u.anchors.map((a: any) => {
                          const selected = orderModal.anchor_text_id === a.id;
                          return (
                            <button key={a.id} type="button" onClick={() => setOrderModal((m: any) => ({
                              ...m, anchor_text: a.text, anchor_text_id: a.id, anchor_type: a.anchor_type, target_url: u.url,
                            }))} className={`px-2 py-0.5 rounded transition-all ${({'brand':'bg-blue-600','topical':'bg-teal-600','generic':'bg-gray-600','exact':'bg-green-600','url':'bg-yellow-600'} as any)[a.anchor_type] || 'bg-gray-600'} ${selected ? 'ring-2 ring-white/80' : 'hover:ring-1 ring-white/30'}`}>
                              {a.text} {a.times_used > 0 && <span className="opacity-60">({a.times_used})</span>}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
                {anchorPool.distribution && (
                  <div className="flex gap-3 mt-2 text-xs text-gray-500">
                    {Object.entries(anchorPool.distribution.gaps as Record<string, number>).map(([k, v]) => (
                      <span key={k} className={v > 0 ? 'text-green-400' : v < -5 ? 'text-red-400' : ''}>
                        {k}: {v > 0 ? '+' : ''}{v}%
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div>
                <label className="block text-sm text-gray-400 mb-1">Target URL</label>
                <input type="text" value={orderModal.target_url} onChange={(e) => setOrderModal({ ...orderModal, target_url: e.target.value })} placeholder="https://..." className={ic} />
              </div>
            )}

            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Anchor Text {orderModal.anchor_type && <span className={`ml-1 px-1.5 py-0.5 rounded text-xs ${({'brand':'bg-blue-600','topical':'bg-teal-600','generic':'bg-gray-600','exact':'bg-green-600','url':'bg-yellow-600'} as any)[orderModal.anchor_type] || 'bg-gray-600'}`}>{orderModal.anchor_type}</span>}
              </label>
              <input type="text" value={orderModal.anchor_text} onChange={(e) => setOrderModal({ ...orderModal, anchor_text: e.target.value, anchor_text_id: '' })} placeholder="Type custom or pick from pool above" className={ic} />
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1">Target URL</label>
              <input type="text" value={orderModal.target_url} onChange={(e) => setOrderModal({ ...orderModal, target_url: e.target.value })} className={ic} />
            </div>

            {orderRules && !orderRules.exists && (
              <div className="bg-yellow-900/20 border border-yellow-700 rounded-lg p-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-yellow-300">⚠ No publisher rules found for this domain</span>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      disabled={askingRules}
                      onClick={async () => {
                        setAskingRules(true);
                        try {
                          await api.grabPublisherRules(orderModal.domain.id);
                          const rules = await api.getPublisherRules(orderModal.domain.id);
                          setOrderRules(rules);
                          toast('Rules extracted from emails!');
                        } catch {
                          const email = orderModal.domain.contact_email;
                          if (email && confirm(`No email history found. Send rules inquiry to ${email}?`)) {
                            try {
                              await api.composeEmail(
                                email,
                                `Re: Guest post on ${orderModal.domain.domain}`,
                                `Hi ${orderModal.domain.contact_name || 'there'},\n\nThank you for the information about advertising on ${orderModal.domain.domain}.\n\nBefore we proceed, could you let us know:\n- How many outgoing links can we include in a guest post?\n- Are links to multiple domains allowed in the same article?\n- Do you have any minimum word count requirements?\n- Should we provide the article, or do you handle content creation?\n- Any other content guidelines we should follow?\n\nThank you!\n\nBest regards,\nTony`,
                                orderModal.domain.id,
                              );
                              toast('Rules inquiry sent!');
                            } catch (e: any) { toast(e.message, 'error'); }
                          }
                        }
                        setAskingRules(false);
                      }}
                      className="px-2 py-1 bg-yellow-700 hover:bg-yellow-600 rounded text-xs"
                    >
                      {askingRules ? 'Checking...' : 'Grab from Emails'}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {orderRules?.exists && (
              <div className="bg-gray-900 rounded-lg p-3 text-xs text-gray-400">
                <div className="flex gap-4 flex-wrap">
                  {orderRules.max_urls && <span>Max URLs: <strong className="text-white">{orderRules.max_urls}</strong></span>}
                  {orderRules.cross_domain !== null && <span>Cross-domain: <strong className="text-white">{orderRules.cross_domain ? 'Yes' : 'No'}</strong></span>}
                  {orderRules.we_write !== null && <span>We write: <strong className="text-white">{orderRules.we_write ? 'Yes' : 'No'}</strong></span>}
                  {orderRules.min_words && <span>Min words: <strong className="text-white">{orderRules.min_words}</strong></span>}
                </div>
                {orderRules.content_guidelines && <div className="mt-1 text-gray-500">{orderRules.content_guidelines}</div>}
              </div>
            )}

            <div className="flex justify-end gap-3 mt-4">
              <button type="button" onClick={() => { setOrderModal(null); setAnchorPool(null); }} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm">Cancel</button>
              <button type="submit" className="px-4 py-2 bg-pink-600 hover:bg-pink-700 rounded-lg text-sm font-medium">Create Order</button>
            </div>
          </form>
        </Modal>
      )}

      {/* Full-Screen Article Preview Modal */}
      {articleModal && (
        <div className="fixed inset-0 bg-black/90 z-50 flex items-center justify-center p-4 overflow-auto">
          <div className="bg-gray-900 rounded-lg border border-gray-700 w-full max-w-5xl max-h-[90vh] overflow-auto">
            <div className="sticky top-0 bg-gray-900 border-b border-gray-700 px-6 py-4 flex items-center justify-between">
              <div>
                <h2 className="text-xl font-bold text-white">{articleModal.title}</h2>
                <div className="flex items-center gap-4 text-sm text-gray-400 mt-1">
                  <span>{articleEditing ? getWordCount(articleDraft) : articleModal.word_count} words</span>
                  {articleModal.images.length > 0 && <span>• {articleModal.images.length} images</span>}
                </div>
              </div>
              <div className="flex items-center gap-2">
                {articleEditing ? (
                  <>
                    <button
                      onClick={saveArticleEdit}
                      disabled={articleSaving}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-green-600 hover:bg-green-700 disabled:opacity-60 disabled:cursor-not-allowed rounded text-sm font-medium text-white transition-colors"
                    >
                      <Check className="w-4 h-4" />
                      {articleSaving ? 'Saving...' : 'Save'}
                    </button>
                    <button
                      onClick={() => {
                        setArticleDraft(articleModal.article_content);
                        setArticleEditing(false);
                      }}
                      disabled={articleSaving}
                      className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 disabled:opacity-60 disabled:cursor-not-allowed rounded text-sm text-gray-200 transition-colors"
                    >
                      Cancel
                    </button>
                  </>
                ) : (
                  <button
                    onClick={() => {
                      setArticleDraft(articleModal.article_content);
                      setArticleEditing(true);
                    }}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-pink-600 hover:bg-pink-700 rounded text-sm font-medium text-white transition-colors"
                  >
                    <Edit2 className="w-4 h-4" />
                    Edit
                  </button>
                )}
                <button
                  onClick={() => {
                    setArticleModal(null);
                    setArticleEditing(false);
                    setArticleDraft('');
                  }}
                  aria-label="Close article preview"
                  className="text-gray-400 hover:text-white transition-colors"
                >
                  <XIcon className="w-6 h-6" />
                </button>
              </div>
            </div>
            <div className="px-8 py-6">
              {articleEditing ? (
                <textarea
                  value={articleDraft}
                  onChange={(e) => setArticleDraft(e.target.value)}
                  className="w-full min-h-[65vh] resize-y rounded-lg border border-gray-700 bg-gray-950 p-4 font-mono text-sm leading-6 text-gray-100 outline-none focus:border-pink-500 focus:ring-1 focus:ring-pink-500"
                  spellCheck={false}
                />
              ) : (
                <div className="prose prose-invert prose-lg max-w-none
                            prose-headings:text-white prose-headings:font-semibold
                            prose-h2:text-2xl prose-h2:mt-8 prose-h2:mb-4 prose-h2:border-b prose-h2:border-gray-700 prose-h2:pb-2
                            prose-h3:text-xl prose-h3:mt-6 prose-h3:mb-3
                            prose-p:text-gray-300 prose-p:leading-relaxed prose-p:mb-4
                            prose-a:text-pink-400 prose-a:no-underline hover:prose-a:underline
                            prose-strong:text-white prose-strong:font-semibold
                            prose-ul:text-gray-300 prose-ol:text-gray-300
                            prose-li:my-1
                            prose-img:rounded-lg prose-img:my-6 prose-img:max-w-full prose-img:shadow-lg">
                <ReactMarkdown
                  components={{
                    a: ({ href, children, ...props }) => {
                      const targetUrls: string[] = articleModal.target_urls || [];
                      const isAnchorLink = href && targetUrls.some((u: string) => u && href.includes(u.replace(/^https?:\/\//, '').replace(/\/$/, '')));
                      return (
                        <a
                          href={href}
                          {...props}
                          className={isAnchorLink ? 'text-green-400 font-semibold underline decoration-green-400/50 decoration-2 underline-offset-2' : 'text-pink-400 no-underline hover:underline'}
                          title={isAnchorLink ? '⚓ Anchor link' : undefined}
                        >
                          {children}
                        </a>
                      );
                    },
                  }}
                >{articleModal.article_content}</ReactMarkdown>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
