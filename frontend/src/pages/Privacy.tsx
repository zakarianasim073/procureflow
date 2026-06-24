import { Shield } from 'lucide-react';

export default function Privacy() {
  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <Shield className="text-primary-600" size={28} />
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Privacy Policy</h1>
      </div>
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-8 space-y-6 text-gray-600 dark:text-gray-300">
        <p className="text-sm text-gray-400">Last updated: June 5, 2026</p>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">1. Information We Collect</h2>
          <p>We collect information you provide when creating an account and using our services, including:</p>
          <ul className="list-disc pl-6 mt-2 space-y-1">
            <li>Account information: name, email address, company details</li>
            <li>Tender documents you upload for analysis (BOQ, TDS, NIT, etc.)</li>
            <li>Usage data: features used, analysis performed, export activities</li>
            <li>Payment information (processed securely by Stripe — we never store card details)</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">2. How We Use Your Data</h2>
          <ul className="list-disc pl-6 space-y-1">
            <li>To provide and improve our tender analysis services</li>
            <li>To train and improve our AI models (anonymized and aggregated only)</li>
            <li>To send service updates, alerts, and relevant tender notifications</li>
            <li>To comply with legal obligations</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">3. Data Storage & Security</h2>
          <p>All data is encrypted in transit (TLS) and at rest. We use industry-standard security measures including:</p>
          <ul className="list-disc pl-6 mt-2 space-y-1">
            <li>AES-256 encryption for stored documents</li>
            <li>JWT-based authentication with token expiration</li>
            <li>Regular security audits and penetration testing</li>
            <li>Access control with role-based permissions</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">4. Data Retention</h2>
          <p>We retain your data for as long as your account is active. Upon account deletion, all associated data is permanently deleted within 30 days.</p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">5. Third-Party Services</h2>
          <p>We use the following third-party services: Stripe (payments), OpenAI/Anthropic (AI processing), and DigitalOcean/Hetzner (hosting). Each service has its own privacy policy governing data handling.</p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">6. Your Rights</h2>
          <p>You have the right to access, correct, or delete your personal data. Contact us at privacy@procurementflow.com.bd for requests.</p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">7. Cookies</h2>
          <p>We use essential cookies for authentication and session management. No tracking cookies are used without explicit consent.</p>
        </section>
      </div>
    </div>
  );
}
