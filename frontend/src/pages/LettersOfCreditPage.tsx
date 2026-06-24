import { CreditCard, Globe2, ShieldCheck } from 'lucide-react';

export default function LettersOfCreditPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Letters of Credit</h1>
        <p className="text-sm text-gray-500 mt-1">Frontend surface restored. Wire banking and import-finance APIs here when those backend modules are added.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          { icon: CreditCard, label: 'LC Register', value: 'Ready for live feed' },
          { icon: Globe2, label: 'Import Exposure', value: 'Awaiting finance source' },
          { icon: ShieldCheck, label: 'Compliance Review', value: 'Can plug into agent output' },
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
