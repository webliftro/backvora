import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Search } from 'lucide-react';
import { api } from '../api';
import { useToast } from '../components/Toast';
import { PageHeader } from '../components/ui';

export default function DashboardPage() {
  const { toast } = useToast();
  const [stats, setStats] = useState({ 
    domains: '-', contacts: '-', sent: '-', deals: '-',
    domainsWithContacts: '-', domainsWithoutContacts: '-', formsDetected: '-', formsWithCaptcha: '-'
  });
  const [showCompForm, setShowCompForm] = useState(false);
  const [compDomain, setCompDomain] = useState('');
  const [compLimit, setCompLimit] = useState(100);
  const [compResult, setCompResult] = useState<string | null>(null);

  useEffect(() => { loadStats(); }, []);

  async function loadStats() {
    try { 
      const d = await api.getDomains(1, 10000); 
      setStats(s => ({ ...s, domains: String(d.total || 0) }));
      
      // Calculate contact stats from domains (matches has_contact_info: saved contacts OR domain-level info OR forms)
      const domainsWithContacts = d.items.filter((domain: any) => domain.has_contact_info).length;
      const domainsWithoutContacts = d.total - domainsWithContacts;
      const formsDetected = d.items.filter((domain: any) => domain.has_form).length;
      const formsWithCaptcha = d.items.filter((domain: any) => domain.has_captcha).length;
      
      setStats(s => ({ 
        ...s, 
        domainsWithContacts: String(domainsWithContacts),
        domainsWithoutContacts: String(domainsWithoutContacts),
        formsDetected: String(formsDetected),
        formsWithCaptcha: String(formsWithCaptcha)
      }));
    } catch {}
    try { const c = await api.getContacts(1, 1); setStats(s => ({ ...s, contacts: String(c.total || 0) })); } catch {}
    try { const m = await api.getInboxStats(); setStats(s => ({ ...s, sent: String(m.sent_count || 0) })); } catch {}
  }

  async function handleFetchBacklinks(e: React.FormEvent) {
    e.preventDefault();
    setCompResult('Fetching backlinks...');
    try {
      const data = await api.fetchBacklinks(compDomain, compLimit);
      if (data.success) {
        setCompResult(`✓ Fetched ${data.total_fetched} backlinks → ${data.domains_added} new domains, ${data.backlinks_added} backlinks recorded`);
        loadStats();
      } else setCompResult('Error fetching backlinks');
    } catch (e: any) { setCompResult(`Error: ${e.message}`); }
  }

  const statCards = [
    { label: 'Total Domains', value: stats.domains, color: 'text-white', link: '/domains' },
    { label: 'Contacts Found', value: stats.contacts, color: 'text-pink-500' },
    { label: 'Emails Sent', value: stats.sent, color: 'text-pink-500' },
    { label: 'Deals Closed', value: stats.deals, color: 'text-green-500' },
  ];

  const contactsStats = [
    { label: 'Domains with Contacts', value: stats.domainsWithContacts, color: 'text-green-400' },
    { label: 'Domains without Contacts', value: stats.domainsWithoutContacts, color: 'text-orange-400' },
    { label: 'Forms Detected', value: stats.formsDetected, color: 'text-blue-400' },
    { label: 'Forms with CAPTCHA', value: stats.formsWithCaptcha, color: 'text-yellow-400' },
  ];

  return (
    <div className="space-y-6">
      <PageHeader title="Dashboard" />
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {statCards.map(({ label, value, color, link }) => {
          const inner = (<><div className="text-sm text-gray-400">{label}</div><div className={`text-2xl font-semibold tabular-nums ${color}`}>{value}</div></>);
          return link ? (
            <Link key={label} to={link} className="bg-gray-800 rounded-lg p-4 sm:p-6 border border-gray-700 hover:border-pink-500 transition-colors block">{inner}</Link>
          ) : (
            <div key={label} className="bg-gray-800 rounded-lg p-4 sm:p-6 border border-gray-700">{inner}</div>
          );
        })}
      </div>
      <div className="bg-gray-800 rounded-lg p-4 sm:p-6 border border-gray-700">
        <h2 className="text-lg font-semibold mb-4">Contacts Overview</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
          {contactsStats.map(({ label, value, color }) => (
            <div key={label} className="bg-gray-700/50 rounded-lg p-3 sm:p-4">
              <div className="text-xs text-gray-400 mb-1">{label}</div>
              <div className={`text-lg sm:text-xl font-semibold tabular-nums ${color}`}>{value}</div>
            </div>
          ))}
        </div>
      </div>
      <div className="bg-gray-800 rounded-lg p-4 sm:p-6 border border-gray-700">
        <h2 className="text-lg font-semibold mb-4">Quick Actions</h2>
        <div className="flex flex-wrap gap-2 sm:gap-3">
          <Link to="/domains" className="px-4 py-2 bg-pink-600 hover:bg-pink-700 rounded-lg text-sm font-medium flex items-center gap-1">
            <Plus className="w-4 h-4" /> <span className="hidden sm:inline">Add Domains</span><span className="sm:hidden">Add</span>
          </Link>
          <button onClick={() => setShowCompForm(!showCompForm)} className="px-4 py-2 bg-pink-600 hover:bg-pink-700 rounded-lg text-sm font-medium flex items-center gap-1">
            <Search className="w-4 h-4" /> <span className="hidden sm:inline">Analyze Competitor</span><span className="sm:hidden">Analyze</span>
          </button>
        </div>
      </div>
      {showCompForm && (
        <div className="bg-gray-800 rounded-lg p-4 sm:p-6 border border-gray-700">
          <h2 className="text-lg font-semibold mb-4">Analyze Competitor Backlinks</h2>
          <form onSubmit={handleFetchBacklinks} className="flex flex-col sm:flex-row gap-3">
            <input type="text" value={compDomain} onChange={e => setCompDomain(e.target.value)} placeholder="competitor.com"
              className="flex-1 px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-pink-500 text-sm" />
            <input type="number" value={compLimit} onChange={e => setCompLimit(Number(e.target.value))} min={1} max={1000}
              className="w-full sm:w-24 px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-pink-500 text-sm" />
            <button type="submit" className="px-6 py-2 bg-pink-600 hover:bg-pink-700 rounded-lg font-medium">Fetch</button>
          </form>
          {compResult && <div className="mt-4 text-sm text-green-400 whitespace-pre-line">{compResult}</div>}
        </div>
      )}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h2 className="text-lg font-semibold mb-4">Recent Activity</h2>
        <p className="text-sm text-gray-400">No recent activity</p>
      </div>
    </div>
  );
}
