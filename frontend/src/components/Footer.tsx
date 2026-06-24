import { Link } from 'react-router-dom';
import { Cpu } from 'lucide-react';

export default function Footer() {
  return (
    <footer className="border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 mt-auto">
      <div className="max-w-7xl mx-auto px-6 py-6">
        <div className="flex flex-col md:flex-row justify-between items-center gap-4">
          <div className="flex flex-col gap-1 text-sm text-gray-400">
            <div className="flex items-center gap-2">
              <Cpu size={16} className="text-primary-600" />
              <span>ProcureFlow Bid Assist v2.0</span>
              <span className="mx-2">•</span>
              <span>© {new Date().getFullYear()} All rights reserved</span>
            </div>
            <div className="pl-6">
              <span className="brand-signature">@zmnasim73</span>
            </div>
          </div>
          <div className="flex items-center gap-6 text-sm">
            <Link
              to="/terms"
              className="text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors"
            >
              Terms of Service
            </Link>
            <Link
              to="/privacy"
              className="text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors"
            >
              Privacy Policy
            </Link>
            <a
              href="mailto:support@procurementflow.com.bd"
              className="text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors"
            >
              Contact
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
}
