import { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { api } from '../api';
import { Pencil, Trash2, Plus, X } from 'lucide-react';
import { PageHeader } from '../components/ui';

export default function SettingsPage() {
  const { user, token } = useAuth();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [loading, setLoading] = useState(false);

  // Templates
  const [templates, setTemplates] = useState<any[]>([]);
  const [editTpl, setEditTpl] = useState<any>(null);
  const [tplForm, setTplForm] = useState({ name: '', subject_template: '', body_template: '', is_active: true });

  useEffect(() => { loadTemplates(); }, []);

  async function loadTemplates() {
    try { const r = await api.getTemplates(); setTemplates(r.items || []); } catch {}
  }

  function openEdit(t?: any) {
    if (t) {
      setEditTpl(t);
      setTplForm({ name: t.name, subject_template: t.subject_template || '', body_template: t.body_template || '', is_active: t.is_active });
    } else {
      setEditTpl({ id: null });
      setTplForm({ name: '', subject_template: 'Advertising on $domain', body_template: '', is_active: true });
    }
  }

  async function saveTpl(e: React.FormEvent) {
    e.preventDefault();
    try {
      if (editTpl?.id) {
        await api.updateTemplate(editTpl.id, tplForm);
      } else {
        await api.createTemplate(tplForm);
      }
      setEditTpl(null);
      loadTemplates();
    } catch (err: any) {
      setMessage({ type: 'error', text: err.message });
    }
  }

  async function deleteTpl(id: string) {
    if (!confirm('Delete this template?')) return;
    try { await api.deleteTemplate(id); loadTemplates(); } catch {}
  }

  async function toggleActive(t: any) {
    try { await api.updateTemplate(t.id, { is_active: !t.is_active }); loadTemplates(); } catch {}
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage(null);
    if (newPassword !== confirmPassword) { setMessage({ type: 'error', text: 'New passwords do not match' }); return; }
    if (newPassword.length < 6) { setMessage({ type: 'error', text: 'Password must be at least 6 characters' }); return; }
    setLoading(true);
    try {
      const r = await fetch('/api/v1/auth/change-password', {
        method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || 'Failed to change password');
      setMessage({ type: 'success', text: 'Password changed successfully!' });
      setCurrentPassword(''); setNewPassword(''); setConfirmPassword('');
    } catch (err: any) { setMessage({ type: 'error', text: err.message }); }
    finally { setLoading(false); }
  };

  const ic = "w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-pink-500";

  return (
    <div className="max-w-2xl space-y-6">
      <PageHeader title="Settings" />

      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h2 className="text-lg font-semibold mb-1">Account</h2>
        <p className="text-gray-400 text-sm mb-4">{user?.email}</p>
      </div>

      {/* Outreach Templates */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold">Outreach Templates</h2>
          <button onClick={() => openEdit()} className="px-3 py-1 bg-pink-600 hover:bg-pink-700 rounded text-sm flex items-center gap-1"><Plus className="w-3 h-3" /> New</button>
        </div>

        {editTpl && (
          <form onSubmit={saveTpl} className="mb-4 p-4 bg-gray-700/50 rounded-lg border border-gray-600 space-y-3">
            <div><label className="block text-xs text-gray-400 mb-1">Name</label>
              <input type="text" value={tplForm.name} onChange={e => setTplForm({ ...tplForm, name: e.target.value })} required className={ic} /></div>
            <div><label className="block text-xs text-gray-400 mb-1">Subject (use $domain)</label>
              <input type="text" value={tplForm.subject_template} onChange={e => setTplForm({ ...tplForm, subject_template: e.target.value })} className={ic} /></div>
            <div><label className="block text-xs text-gray-400 mb-1">Body (use $domain)</label>
              <textarea value={tplForm.body_template} onChange={e => setTplForm({ ...tplForm, body_template: e.target.value })} rows={4} className={ic} /></div>
            <label className="flex items-center gap-2"><input type="checkbox" checked={tplForm.is_active} onChange={e => setTplForm({ ...tplForm, is_active: e.target.checked })} /><span className="text-sm">Active</span></label>
            <div className="flex gap-2">
              <button type="submit" className="px-4 py-2 bg-pink-600 hover:bg-pink-700 rounded-lg text-sm font-medium">Save</button>
              <button type="button" onClick={() => setEditTpl(null)} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm">Cancel</button>
            </div>
          </form>
        )}

        <div className="space-y-2">
          {templates.map(t => (
            <div key={t.id} className={`p-3 rounded-lg border ${t.is_active ? 'bg-gray-700/50 border-gray-600' : 'bg-gray-700/20 border-gray-700 opacity-60'}`}>
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <div className="font-medium text-sm">{t.name}</div>
                  <div className="text-xs text-gray-400 mt-0.5">Subject: {t.subject_template}</div>
                  <div className="text-xs text-gray-500 mt-1 whitespace-pre-wrap line-clamp-2">{t.body_template}</div>
                </div>
                <div className="flex gap-1 ml-2">
                  <button onClick={() => toggleActive(t)} className={`px-2 py-1 rounded text-xs ${t.is_active ? 'bg-green-900/50 text-green-400' : 'bg-gray-600 text-gray-400'}`}>
                    {t.is_active ? 'Active' : 'Inactive'}
                  </button>
                  <button onClick={() => openEdit(t)} aria-label="Edit template" className="text-gray-400 hover:text-white p-1"><Pencil className="w-3.5 h-3.5" /></button>
                  <button onClick={() => deleteTpl(t.id)} aria-label="Delete template" className="text-red-400 hover:text-red-300 p-1"><Trash2 className="w-3.5 h-3.5" /></button>
                </div>
              </div>
            </div>
          ))}
          {templates.length === 0 && <p className="text-gray-500 text-sm">No templates yet. They'll be auto-created on first use.</p>}
        </div>
      </div>

      {/* Change Password */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h2 className="text-lg font-semibold mb-4">Change Password</h2>
        {message && (
          <div className={`mb-4 p-3 rounded text-sm ${message.type === 'success' ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'}`}>{message.text}</div>
        )}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div><label className="block text-sm text-gray-400 mb-1">Current Password</label><input type="password" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} required className={ic} /></div>
          <div><label className="block text-sm text-gray-400 mb-1">New Password</label><input type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} required className={ic} /></div>
          <div><label className="block text-sm text-gray-400 mb-1">Confirm New Password</label><input type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} required className={ic} /></div>
          <button type="submit" disabled={loading} className="w-full py-2 bg-pink-600 hover:bg-pink-700 disabled:opacity-50 rounded-lg text-white font-medium transition-colors">{loading ? 'Changing...' : 'Change Password'}</button>
        </form>
      </div>
    </div>
  );
}
