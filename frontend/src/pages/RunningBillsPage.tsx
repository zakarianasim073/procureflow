import { Receipt, Clock3, Landmark } from 'lucide-react';

export default function RunningBillsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Running Bills</h1>
        <p className="text-sm text-gray-500 mt-1">Operational surface restored from the sibling app. Connect bill APIs next if you want live finance workflow data here.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          { icon: Receipt, label: 'Tracked Bills', value: 'Ready for API' },
          { icon: Clock3, label: 'Pending Certification', value: 'Needs backend feed' },
          { icon: Landmark, label: 'Payment Pipeline', value: 'Schema ready' },
        ].map((item) => (
          <div key={item.label} className="rounded-xl border border-gray-200 bg-white p-5">
            <item.icon size={18} className="text-primary-600 mb-3" />
            <div className="text-sm text-gray-500">{item.label}</div>
            <div className="text-lg font-semibold text-gray-900 mt-1">{item.value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
