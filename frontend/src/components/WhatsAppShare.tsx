import { Share2, Check } from 'lucide-react';
import { useState } from 'react';

interface ShareProps {
  title: string;
  message: string;
  compact?: boolean;
}

export default function WhatsAppShare({ title, message, compact }: ShareProps) {
  const [copied, setCopied] = useState(false);

  const shareViaWhatsApp = () => {
    const encoded = encodeURIComponent(`${title}\n\n${message}`);
    window.open(`https://wa.me/?text=${encoded}`, '_blank');
  };

  const copyToClipboard = async () => {
    await navigator.clipboard.writeText(message);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (compact) {
    return (
      <div className="flex gap-1">
        <button
          onClick={shareViaWhatsApp}
          className="p-1.5 rounded-lg hover:bg-green-50 dark:hover:bg-green-900/20 text-green-600 transition-colors"
          title="Share on WhatsApp"
        >
          <Share2 size={14} />
        </button>
        <button
          onClick={copyToClipboard}
          className={`p-1.5 rounded-lg transition-colors ${copied ? 'text-green-600' : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'}`}
          title={copied ? 'Copied!' : 'Copy to clipboard'}
        >
          <Check size={14} />
        </button>
      </div>
    );
  }

  return (
    <div className="flex gap-2">
      <button
        onClick={shareViaWhatsApp}
        className="px-3 py-1.5 bg-green-500 hover:bg-green-600 text-white text-sm rounded-lg flex items-center gap-1.5 transition-colors"
      >
        <Share2 size={14} />
        Share on WhatsApp
      </button>
      <button
        onClick={copyToClipboard}
        className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50 text-sm rounded-lg flex items-center gap-1.5 transition-colors"
      >
        {copied ? <><Check size={14} /> Copied</> : <><Check size={14} /> Copy</>}
      </button>
    </div>
  );
}
