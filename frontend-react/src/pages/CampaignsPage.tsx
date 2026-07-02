import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Target, TrendingUp, DollarSign, Package, Zap, ChevronDown, ChevronUp } from 'lucide-react';
import { api } from '../api';
import { useToast } from '../components/Toast';
import Modal from '../components/Modal';

interface Campaign {
  id: string;
  name: string;
  target_site: string;
  status: string;
  budget: number | null;
  spent: number;
  total_orders: number;
  links_live: number;
  created_at: string;
  mode?: string;
  velocity_count?: number;
  velocity_period_days?: number;
  approval_mode?: string;
  consecutive_approvals?: number;
  approval_threshold?: number;
}

const statusColors: Record<string, string> = {
  active: 'bg-green-600',
  paused: 'bg-yellow-600',
  completed: 'bg-gray-600',
};

const LINK_TYPES = ['Guest Post', 'Header', 'Footer', 'Navbar', 'Sidebar', 'Sidebar Friends', 'Toplist', 'Sticky Post', 'Topbar', 'Menu tab', 'Model+Content tab'];

export default function CampaignsPage() {
  const { toast } = useToast();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    target_site: '',
    target_site_id: '',
    status: 'active',
    budget: '',
    notes: '',
    mode: 'manual',
    // Auto mode fields
    filter_traffic_min: '',
    filter_traffic_max: '',
    filter_dr_min: '',
    filter_dr_max: '',
    filter_price_min: '',
    filter_price_max: '',
    filter_niche_tags: '',
    filter_link_type: '',
    velocity_count: '1',
    velocity_period_days: '7',
    budget_total: '',
    schedule_enabled: false,
    schedule_interval_hours: '6',
  });
  const [targetSites, setTargetSites] = useState<any[]>([]);
  const [showFilters, setShowFilters] = useState(false);

  useEffect(() => {
    loadCampaigns();
    api.getTargetSites().then(d => setTargetSites(d.items)).catch(() => {});
  }, []);

  async function loadCampaigns() {
    try {
      setLoading(true);
      const data = await api.getCampaigns();
      setCampaigns(data.items);
    } catch (e: any) {
      toast(e.message, 'error');
    } finally {
      setLoading(false);
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    try {
      const payload: Record<string, unknown> = {
        name: formData.name,
        target_site: formData.target_site,
        target_site_id: formData.target_site_id || null,
        status: formData.status,
        budget: formData.budget ? parseFloat(formData.budget) : null,
        notes: formData.notes || null,
        mode: formData.mode,
      };
      if (formData.mode === 'auto') {
        if (formData.filter_traffic_min) payload.filter_traffic_min = parseInt(formData.filter_traffic_min);
        if (formData.filter_traffic_max) payload.filter_traffic_max = parseInt(formData.filter_traffic_max);
        if (formData.filter_dr_min) payload.filter_dr_min = parseInt(formData.filter_dr_min);
        if (formData.filter_dr_max) payload.filter_dr_max = parseInt(formData.filter_dr_max);
        if (formData.filter_price_min) payload.filter_price_min = parseFloat(formData.filter_price_min);
        if (formData.filter_price_max) payload.filter_price_max = parseFloat(formData.filter_price_max);
        if (formData.filter_niche_tags) payload.filter_niche_tags = formData.filter_niche_tags;
        if (formData.filter_link_type) payload.filter_link_type = formData.filter_link_type;
        payload.velocity_count = parseInt(formData.velocity_count) || 1;
        payload.velocity_period_days = parseInt(formData.velocity_period_days) || 7;
        if (formData.budget_total) payload.budget_total = parseFloat(formData.budget_total);
        payload.schedule_enabled = formData.schedule_enabled;
        payload.schedule_interval_hours = parseInt(formData.schedule_interval_hours) || 6;
      }
      await api.createCampaign(payload);
      toast('Campaign created!');
      setCreateOpen(false);
      setFormData({ name: '', target_site: '', target_site_id: '', status: 'active', budget: '', notes: '', mode: 'manual', filter_traffic_min: '', filter_traffic_max: '', filter_dr_min: '', filter_dr_max: '', filter_price_min: '', filter_price_max: '', filter_niche_tags: '', filter_link_type: '', velocity_count: '1', velocity_period_days: '7', budget_total: '', schedule_enabled: false, schedule_interval_hours: '6' });
      setShowFilters(false);
      loadCampaigns();
    } catch (e: any) {
      toast(e.message, 'error');
    }
  }

  const ic = "w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-sm focus:outline-none focus:border-pink-500";

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight flex items-center gap-2">
            <Target className="w-5 h-5 text-pink-500" />
            Campaigns
          </h1>
          <p className="text-gray-400 text-sm mt-1">Manage your link building campaigns</p>
        </div>
        <button
          onClick={() => setCreateOpen(true)}
          className="px-4 py-2 bg-pink-600 hover:bg-pink-700 rounded-lg font-medium flex items-center gap-2 self-start sm:self-auto"
        >
          <Plus className="w-4 h-4" />
          <span className="hidden sm:inline">New Campaign</span>
          <span className="sm:hidden">New</span>
        </button>
      </div>

      {loading ? (
        <div className="text-center py-12 text-gray-500">Loading campaigns...</div>
      ) : campaigns.length === 0 ? (
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-12 text-center">
          <Target className="w-12 h-12 text-gray-600 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-400 mb-2">No campaigns yet</h3>
          <p className="text-gray-500 text-sm mb-6">
            Create your first campaign to start organizing your link building efforts
          </p>
          <button
            onClick={() => setCreateOpen(true)}
            className="px-4 py-2 bg-pink-600 hover:bg-pink-700 rounded-lg font-medium inline-flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            Create Campaign
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {campaigns.map((campaign) => (
            <Link
              key={campaign.id}
              to={`/campaigns/${campaign.id}`}
              className="bg-gray-800 rounded-lg border border-gray-700 p-4 sm:p-5 hover:border-pink-500 transition-colors group"
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-lg group-hover:text-pink-400 transition-colors truncate">
                    {campaign.name}
                  </h3>
                  <p className="font-mono text-[13px] text-gray-400 truncate">{campaign.target_site}</p>
                </div>
                <div className="flex items-center gap-1.5 ml-2">
                  {campaign.mode === 'auto' ? (
                    <span className="px-2 py-0.5 rounded text-xs font-medium bg-emerald-600 flex items-center gap-1">
                      <Zap className="w-3 h-3" />Auto
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 rounded text-xs font-medium bg-gray-600">Manual</span>
                  )}
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-medium ${
                      statusColors[campaign.status] || 'bg-gray-600'
                    }`}
                  >
                    {campaign.status}
                  </span>
                </div>
              </div>

              <div className="space-y-2 mb-4">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-400 flex items-center gap-1.5">
                    <Package className="w-4 h-4" />
                    Orders
                  </span>
                  <span className="font-medium">{campaign.total_orders}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-400 flex items-center gap-1.5">
                    <TrendingUp className="w-4 h-4" />
                    Live Links
                  </span>
                  <span className="font-medium text-green-400">{campaign.links_live}</span>
                </div>
                {campaign.budget && (
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-gray-400 flex items-center gap-1.5">
                      <DollarSign className="w-4 h-4" />
                      Budget
                    </span>
                    <span className="font-medium">
                      ${campaign.spent.toFixed(0)} / ${campaign.budget.toFixed(0)}
                    </span>
                  </div>
                )}
                {campaign.mode === 'auto' && (
                  <>
                    {campaign.velocity_count && campaign.velocity_period_days && (
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-gray-400 flex items-center gap-1.5">
                          <Zap className="w-4 h-4" />
                          Velocity
                        </span>
                        <span className="font-medium text-emerald-400">
                          {campaign.velocity_count} link{campaign.velocity_count > 1 ? 's' : ''}/{campaign.velocity_period_days === 7 ? 'week' : `${campaign.velocity_period_days}d`}
                        </span>
                      </div>
                    )}
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-gray-400">Approval</span>
                      <span className="font-medium">
                        {campaign.approval_mode === 'auto' ? (
                          <span className="text-emerald-400">Auto ✓</span>
                        ) : (
                          <span className="text-yellow-400">Review ({campaign.consecutive_approvals || 0}/{campaign.approval_threshold || 10})</span>
                        )}
                      </span>
                    </div>
                  </>
                )}
              </div>

              {campaign.budget && (
                <div className="space-y-1">
                  <div className="flex justify-between text-xs text-gray-400">
                    <span>Spent</span>
                    <span>{Math.round((campaign.spent / campaign.budget) * 100)}%</span>
                  </div>
                  <div className="w-full bg-gray-700 rounded-full h-2 overflow-hidden">
                    <div
                      className="bg-pink-600 h-full rounded-full transition-all"
                      style={{
                        width: `${Math.min(100, (campaign.spent / campaign.budget) * 100)}%`,
                      }}
                    />
                  </div>
                </div>
              )}

              <div className="mt-3 pt-3 border-t border-gray-700 text-xs text-gray-500">
                Created {new Date(campaign.created_at).toLocaleDateString()}
              </div>
            </Link>
          ))}
        </div>
      )}

      {/* Create Campaign Modal */}
      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="Create Campaign">
        <form onSubmit={handleCreate} className="space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-2">Campaign Name *</label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              placeholder="e.g. CamHours Growth Q1"
              required
              className={ic}
            />
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-2">Target Site *</label>
            {targetSites.length > 0 ? (
              <select
                value={formData.target_site_id}
                onChange={(e) => {
                  const ts = targetSites.find(s => s.id === e.target.value);
                  setFormData({ ...formData, target_site_id: e.target.value, target_site: ts?.domain || '' });
                }}
                required
                className={ic}
              >
                <option value="">Select a target site</option>
                {targetSites.map(s => <option key={s.id} value={s.id}>{s.name} ({s.domain})</option>)}
              </select>
            ) : (
            <input
              type="text"
              value={formData.target_site}
              onChange={(e) => setFormData({ ...formData, target_site: e.target.value })}
              placeholder="e.g. camhours.com"
              required
              className={ic}
            />
            )}
          </div>

          {/* Mode Selection */}
          <div>
            <label className="block text-sm text-gray-400 mb-2">Campaign Mode</label>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setFormData({ ...formData, mode: 'manual' })}
                className={`flex-1 px-4 py-3 rounded-lg border text-sm font-medium transition-colors ${
                  formData.mode === 'manual'
                    ? 'border-pink-500 bg-pink-600/20 text-white'
                    : 'border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600'
                }`}
              >
                <div className="font-semibold">Manual</div>
                <div className="text-xs opacity-70 mt-0.5">You manage everything</div>
              </button>
              <button
                type="button"
                onClick={() => setFormData({ ...formData, mode: 'auto' })}
                className={`flex-1 px-4 py-3 rounded-lg border text-sm font-medium transition-colors ${
                  formData.mode === 'auto'
                    ? 'border-emerald-500 bg-emerald-600/20 text-white'
                    : 'border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600'
                }`}
              >
                <div className="font-semibold flex items-center gap-1.5"><Zap className="w-4 h-4" />Auto</div>
                <div className="text-xs opacity-70 mt-0.5">Campaign runs itself</div>
              </button>
            </div>
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-2">Status</label>
            <select
              value={formData.status}
              onChange={(e) => setFormData({ ...formData, status: e.target.value })}
              className={ic}
            >
              <option value="active">Active</option>
              <option value="paused">Paused</option>
              <option value="completed">Completed</option>
            </select>
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-2">Budget (USD)</label>
            <input
              type="number"
              step="0.01"
              value={formData.budget}
              onChange={(e) => setFormData({ ...formData, budget: e.target.value })}
              placeholder="Optional"
              className={ic}
            />
          </div>

          {/* Auto Mode Settings */}
          {formData.mode === 'auto' && (
            <div className="space-y-4 border-t border-gray-700 pt-4">
              {/* Domain Filters */}
              <div>
                <button
                  type="button"
                  onClick={() => setShowFilters(!showFilters)}
                  className="flex items-center gap-2 text-sm font-medium text-gray-300 hover:text-white w-full"
                >
                  {showFilters ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  Domain Filters
                </button>
                {showFilters && (
                  <div className="mt-3 space-y-3 bg-gray-900/50 rounded-lg p-3">
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs text-gray-500 mb-1">Traffic Min</label>
                        <input type="number" value={formData.filter_traffic_min} onChange={e => setFormData({ ...formData, filter_traffic_min: e.target.value })} placeholder="0" className={ic} />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-500 mb-1">Traffic Max</label>
                        <input type="number" value={formData.filter_traffic_max} onChange={e => setFormData({ ...formData, filter_traffic_max: e.target.value })} placeholder="∞" className={ic} />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs text-gray-500 mb-1">DR Min</label>
                        <input type="number" value={formData.filter_dr_min} onChange={e => setFormData({ ...formData, filter_dr_min: e.target.value })} placeholder="0" className={ic} />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-500 mb-1">DR Max</label>
                        <input type="number" value={formData.filter_dr_max} onChange={e => setFormData({ ...formData, filter_dr_max: e.target.value })} placeholder="100" className={ic} />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs text-gray-500 mb-1">Price Min ($)</label>
                        <input type="number" step="0.01" value={formData.filter_price_min} onChange={e => setFormData({ ...formData, filter_price_min: e.target.value })} placeholder="0" className={ic} />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-500 mb-1">Price Max ($)</label>
                        <input type="number" step="0.01" value={formData.filter_price_max} onChange={e => setFormData({ ...formData, filter_price_max: e.target.value })} placeholder="∞" className={ic} />
                      </div>
                    </div>
                    <div>
                      <label className="block text-xs text-gray-500 mb-1">Niche Tags (comma-separated)</label>
                      <input type="text" value={formData.filter_niche_tags} onChange={e => setFormData({ ...formData, filter_niche_tags: e.target.value })} placeholder="e.g. adult, cam, dating" className={ic} />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-500 mb-1">Link Type</label>
                      <select value={formData.filter_link_type} onChange={e => setFormData({ ...formData, filter_link_type: e.target.value })} className={ic}>
                        <option value="">Any</option>
                        {LINK_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                      </select>
                    </div>
                  </div>
                )}
              </div>

              {/* Velocity */}
              <div>
                <label className="block text-sm text-gray-400 mb-2">Link Velocity</label>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-gray-400">Build</span>
                  <input type="number" min="1" value={formData.velocity_count} onChange={e => setFormData({ ...formData, velocity_count: e.target.value })} className="w-16 px-2 py-2 bg-gray-700 border border-gray-600 rounded-lg text-sm focus:outline-none focus:border-pink-500 text-center" />
                  <span className="text-sm text-gray-400">link(s) every</span>
                  <input type="number" min="1" value={formData.velocity_period_days} onChange={e => setFormData({ ...formData, velocity_period_days: e.target.value })} className="w-16 px-2 py-2 bg-gray-700 border border-gray-600 rounded-lg text-sm focus:outline-none focus:border-pink-500 text-center" />
                  <span className="text-sm text-gray-400">days</span>
                </div>
              </div>

              {/* Budget Total */}
              <div>
                <label className="block text-sm text-gray-400 mb-2">Total Budget ($)</label>
                <input type="number" step="0.01" value={formData.budget_total} onChange={e => setFormData({ ...formData, budget_total: e.target.value })} placeholder="Auto-pauses when reached" className={ic} />
              </div>

              {/* Schedule */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm text-gray-400">Enable Scheduling</label>
                  <button
                    type="button"
                    onClick={() => setFormData({ ...formData, schedule_enabled: !formData.schedule_enabled })}
                    className={`w-10 h-5 rounded-full transition-colors relative ${formData.schedule_enabled ? 'bg-emerald-600' : 'bg-gray-600'}`}
                  >
                    <div className={`w-4 h-4 bg-white rounded-full absolute top-0.5 transition-transform ${formData.schedule_enabled ? 'translate-x-5' : 'translate-x-0.5'}`} />
                  </button>
                </div>
                {formData.schedule_enabled && (
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-gray-400">Check every</span>
                    <input type="number" min="1" value={formData.schedule_interval_hours} onChange={e => setFormData({ ...formData, schedule_interval_hours: e.target.value })} className="w-16 px-2 py-2 bg-gray-700 border border-gray-600 rounded-lg text-sm focus:outline-none focus:border-pink-500 text-center" />
                    <span className="text-sm text-gray-400">hours</span>
                  </div>
                )}
              </div>
            </div>
          )}

          <div>
            <label className="block text-sm text-gray-400 mb-2">Notes</label>
            <textarea
              value={formData.notes}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
              rows={3}
              placeholder="Campaign notes..."
              className={ic}
            />
          </div>

          <div className="flex justify-end gap-3 mt-6">
            <button
              type="button"
              onClick={() => setCreateOpen(false)}
              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-pink-600 hover:bg-pink-700 rounded-lg text-sm font-medium"
            >
              Create Campaign
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
