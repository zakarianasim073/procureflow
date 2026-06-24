import { ComparisonItem } from '../api/client';

interface Props { data: ComparisonItem[]; compact?: boolean }

const flagStyles: Record<string, string> = {
  'AT SOR': 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  'VARIANCE': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  'MISMATCH': 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  'BELOW SOR': 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  'ABOVE SOR': 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
};

const flagIcons: Record<string, string> = {
  'AT SOR': '✅', 'VARIANCE': '⚠️', 'MISMATCH': '🔴', 'BELOW SOR': '🔵', 'ABOVE SOR': '🔴',
};

export default function ComparisonTable({ data, compact }: Props) {
  if (!data || data.length === 0) {
    return <div className="text-center py-12 text-gray-400">No comparison data yet</div>;
  }

  const headerCells = compact
    ? [
        '#',
        'Code',
        'Description',
        'Qty',
        'SOR Rate',
        'Quoted',
        'Diff',
        'Status',
      ]
    : [
        '#',
        'Code',
        'Agency',
        'Work Type',
        'Description',
        'Unit',
        'Qty',
        'SOR Rate',
        'Quoted',
        'Diff',
        'Var %',
        'Status',
      ];

  return (
    <div className="overflow-x-auto custom-scrollbar">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
            {headerCells.map((label) => (
              <th
                key={label}
                className={`px-3 py-2 font-medium text-gray-500 ${
                  label === 'Qty' || label === 'SOR Rate' || label === 'Quoted' || label === 'Diff' || label === 'Var %'
                    ? 'text-right'
                    : label === 'Status' || label === 'Unit'
                      ? 'text-center'
                      : 'text-left'
                }`}
                style={!compact && label === 'Description' ? { minWidth: 300 } : undefined}
              >
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((item, i) => (
            <tr key={i} className="border-b border-gray-100 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-800/50">
              {[
                <td key="item_no" className="px-3 py-2 text-gray-500">{item.item_no || i + 1}</td>,
                <td key="code" className="px-3 py-2 font-mono text-xs text-gray-700 dark:text-gray-300">{item.code}</td>,
                ...(compact ? [] : [
                  <td key="agency" className="px-3 py-2 text-gray-600">{item.agency}</td>,
                  <td key="work_type" className="px-3 py-2 text-gray-600">{item.work_type}</td>,
                ]),
                <td key="desc" className="px-3 py-2 text-gray-700 dark:text-gray-300 max-w-xs truncate" title={item.desc}>{item.desc}</td>,
                <td key="unit" className="px-3 py-2 text-center text-gray-600">{item.unit}</td>,
                <td key="qty" className="px-3 py-2 text-right font-mono">{item.qty?.toLocaleString()}</td>,
                <td key="sor_rate" className="px-3 py-2 text-right font-mono">{item.sor_rate?.toLocaleString() ?? '—'}</td>,
                <td key="quoted" className="px-3 py-2 text-right font-mono">{item.rate?.toLocaleString() ?? '—'}</td>,
                <td key="diff" className={`px-3 py-2 text-right font-mono ${(item.diff ?? 0) < 0 ? 'text-green-600' : (item.diff ?? 0) > 0 ? 'text-red-600' : ''}`}>
                  {item.diff?.toLocaleString() ?? '—'}
                </td>,
                ...(compact ? [] : [
                  <td key="pct_diff" className={`px-3 py-2 text-right font-mono ${(item.pct_diff ?? 0) < 0 ? 'text-green-600' : (item.pct_diff ?? 0) > 0 ? 'text-red-600' : ''}`}>
                    {item.pct_diff != null ? `${item.pct_diff > 0 ? '+' : ''}${item.pct_diff.toFixed(1)}%` : '—'}
                  </td>,
                ]),
                <td key="status" className="px-3 py-2 text-center">
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${flagStyles[item.flag] || 'bg-gray-100 text-gray-600'}`}>
                    {flagIcons[item.flag] || '❓'} {item.flag}
                  </span>
                </td>,
              ]}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
