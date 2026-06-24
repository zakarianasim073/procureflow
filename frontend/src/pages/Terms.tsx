import { Scale } from 'lucide-react';

export default function Terms() {
  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <Scale className="text-primary-600" size={28} />
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Terms of Service</h1>
      </div>
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-8 space-y-6 text-gray-600 dark:text-gray-300">
        <p className="text-sm text-gray-400">Last updated: June 5, 2026</p>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">1. Acceptance of Terms</h2>
          <p>By accessing and using Procurement Flow Specialist BD ("the Platform"), you agree to be bound by these Terms of Service. If you do not agree, do not use the Platform.</p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">2. Service Description</h2>
          <p>Procurement Flow Specialist BD provides AI-powered tender processing tools including but not limited to:</p>
          <ul className="list-disc pl-6 mt-2 space-y-1">
            <li>BOQ (Bill of Quantities) analysis and comparison against SOR rates</li>
            <li>Tender document parsing and extraction</li>
            <li>eGP tender monitoring and alerts</li>
            <li>PPR 2025 compliance evaluation</li>
            <li>Competitor and award intelligence</li>
            <li>Bid preparation and analysis tools</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">3. User Accounts</h2>
          <p>You are responsible for maintaining the confidentiality of your account credentials. All activities under your account are your responsibility. You must notify us immediately of any unauthorized use.</p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">4. Subscription & Payments</h2>
          <p>Paid plans are billed monthly. Cancellation takes effect at the end of the current billing period. Refunds are provided at our discretion for service disruptions.</p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">5. Data Privacy</h2>
          <p>Your tender documents and analysis data remain your property. We do not share your data with third parties. See our Privacy Policy for details.</p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">6. Limitation of Liability</h2>
          <p>The Platform provides analytical tools and estimates. All bid decisions remain the sole responsibility of the user. We are not liable for any financial losses resulting from use of the Platform.</p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">7. Changes to Terms</h2>
          <p>We reserve the right to modify these terms. Users will be notified of material changes via email or platform notification.</p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">8. Contact</h2>
          <p>For questions about these terms, contact us at support@procurementflow.com.bd</p>
        </section>
      </div>
    </div>
  );
}
