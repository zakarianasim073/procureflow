import { useState } from 'react';
import { Calculator, DollarSign, Percent, FileSpreadsheet } from 'lucide-react';
import { runAgent } from '../api/client';

interface TaxBreakdown {
  gross_amount: number;
  contract_type: string;
  breakdown: {
    vat: { rate_pct: number; amount: number; label: string };
    ait: { rate_pct: number; amount: number; label: string };
    sd: { rate_pct: number; amount: number; label: string };
    it: { rate_pct: number; amount: number; label: string };
  };
  total_tax: { amount: number; effective_rate_pct: number };
  net_amount: number;
  explanation_bn: string;
}

const CONTRACT_TYPES = [
  { value: 'construction', label: 'Construction' },
  { value: 'supply', label: 'Supply' },
  { value: 'service', label: 'Service' },
  { value: 'works', label: 'Works' },
];

export default function VatTaxCalculator() {
  const [contractValue, setContractValue] = useState('50000000');
  const [contractType, setContractType] = useState('construction');
  const [companyTaxRate, setCompanyTaxRate] = useState('22.5');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<TaxBreakdown | null>(null);
  const [error, setError] = useState('');

  const handleCalculate = async () => {
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const data = await runAgent('agent-032-vat-tax-calculator', {
        contract_value: parseFloat(contractValue) || 0,
        contract_type: contractType,
        company_tax_rate: parseFloat(companyTaxRate) || 22.5,
      });
      setResult(data.output);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Calculation failed');
    } finally {
      setLoading(false);
    }
  };

  const formatBDT = (n: number) => `BDT ${n.toLocaleString('en-IN')}`;

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <Calculator className="text-primary-600" size={28} />
          VAT/Tax Calculator
        </h1>
        <p className="text-gray-500 dark:text-gray-400 mt-1">
          Calculate applicable Bangladeshi taxes for construction tender bids
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Contract Details</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Contract Value (BDT)</label>
              <div className="relative">
                <DollarSign size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                <input
                  type="number"
                  value={contractValue}
                  onChange={(e) => setContractValue(e.target.value)}
                  className="w-full pl-10 pr-4 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Contract Type</label>
              <select
                value={contractType}
                onChange={(e) => setContractType(e.target.value)}
                className="w-full px-3 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
              >
                {CONTRACT_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                <span className="flex items-center gap-1">Company Tax Rate <Percent size={14} /></span>
              </label>
              <input
                type="number"
                step="0.1"
                value={companyTaxRate}
                onChange={(e) => setCompanyTaxRate(e.target.value)}
                className="w-full px-3 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
              />
            </div>
            <button
              onClick={handleCalculate}
              disabled={loading}
              className="w-full py-2.5 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-400 text-white rounded-lg font-medium text-sm transition-colors flex items-center justify-center gap-2"
            >
              {loading ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <><Calculator size={16} /> Calculate</>}
            </button>
          </div>
          {error && <div className="mt-4 p-3 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 rounded-lg text-sm">{error}</div>}
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Tax Breakdown</h2>
          {result ? (
            <div className="space-y-4">
              <div className="p-3 bg-primary-50 dark:bg-primary-900/10 rounded-lg">
                <div className="text-xs text-gray-500 dark:text-gray-400">Gross Contract Value</div>
                <div className="text-xl font-bold text-gray-900 dark:text-white">{formatBDT(result.gross_amount)}</div>
              </div>
              <div className="divide-y divide-gray-100 dark:divide-gray-700">
                {[
                  { key: 'vat' as const, color: 'text-blue-600' },
                  { key: 'ait' as const, color: 'text-orange-600' },
                  { key: 'sd' as const, color: 'text-purple-600' },
                  { key: 'it' as const, color: 'text-red-600' },
                ].map(({ key, color }) => {
                  const item = result.breakdown[key];
                  return (
                    <div key={key} className="flex items-center justify-between py-2.5">
                      <div>
                        <div className="text-sm font-medium text-gray-900 dark:text-white">{item.label}</div>
                        <div className="text-xs text-gray-400">Rate: {item.rate_pct}%</div>
                      </div>
                      <div className={`text-sm font-semibold ${color}`}>{formatBDT(item.amount)}</div>
                    </div>
                  );
                })}
              </div>
              <div className="p-3 bg-gray-50 dark:bg-gray-700/30 rounded-lg">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Total Tax</span>
                  <span className="text-sm font-bold text-red-600">{formatBDT(result.total_tax.amount)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Effective Rate</span>
                  <span className="text-sm font-semibold text-gray-900 dark:text-white">{result.total_tax.effective_rate_pct}%</span>
                </div>
              </div>
              <div className="p-4 bg-green-50 dark:bg-green-900/10 rounded-lg border border-green-200 dark:border-green-800">
                <div className="text-xs text-green-600 dark:text-green-400 font-medium">Net Amount After Tax</div>
                <div className="text-2xl font-bold text-green-700 dark:text-green-300">{formatBDT(result.net_amount)}</div>
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-64 text-gray-400">
              <FileSpreadsheet size={48} className="mb-3 opacity-50" />
              <p className="text-sm">Enter contract details and click Calculate</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
