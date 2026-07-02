import { Mail, Clock, Send, CalendarCheck } from 'lucide-react';
import { PageHeader } from '../components/ui';

export default function OutreachPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Outreach Campaigns" />
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <p className="text-gray-400 mb-4">Outreach management coming soon...</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {[
            { icon: Mail, label: 'Create email campaigns' },
            { icon: Send, label: 'Email templates with variables' },
            { icon: Clock, label: 'Send tracking' },
            { icon: CalendarCheck, label: 'Follow-up scheduling' },
          ].map(({ icon: Icon, label }) => (
            <div key={label} className="flex items-center gap-3 text-sm text-gray-500">
              <Icon className="w-4 h-4 text-gray-600" /> {label}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
