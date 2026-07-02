import { Handshake, DollarSign, CheckCircle, TrendingUp } from 'lucide-react';
import { PageHeader } from '../components/ui';

export default function DealsPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Deal Tracker" />
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <p className="text-gray-400 mb-4">Deal tracking coming soon...</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {[
            { icon: Handshake, label: 'Track link negotiations' },
            { icon: DollarSign, label: 'Pricing and payment status' },
            { icon: CheckCircle, label: 'Link verification' },
            { icon: TrendingUp, label: 'ROI tracking' },
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
