import { useState } from 'react';
import { Check, Loader2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAppStore } from '../store/appStore';
import api from '../api/client';

const plans = [
  {
    name: 'Free',
    price: '৳0',
    period: '/month',
    description: 'For evaluating the platform',
    features: ['5 Tender Analyses / month', 'Basic SOR Comparison', 'PDF Export'],
    cta: 'Current Plan',
    disabled: true,
    stripe_price_id: null,
    plan_name: 'free',
  },
  {
    name: 'Professional',
    price: '৳15,000',
    period: '/month',
    description: 'For active contractors bidding weekly',
    features: [
      'Unlimited Tender Analyses',
      'PPR 2025 SLT/LERT Engine',
      'eGP Radar & Alerts',
      'Competitor Intelligence',
      'Priority AI Processing',
    ],
    cta: 'Upgrade to Pro',
    disabled: false,
    stripe_price_id: 'price_pro',
    plan_name: 'pro',
    popular: true,
  },
  {
    name: 'Enterprise',
    price: '৳45,000',
    period: '/month',
    description: 'For large firms with multiple estimators',
    features: [
      'Everything in Pro',
      '5 User Seats',
      'Custom SOR Database',
      'API Access',
      'Dedicated Account Manager',
    ],
    cta: 'Contact Sales',
    disabled: false,
    stripe_price_id: 'price_enterprise',
    plan_name: 'enterprise',
  },
];

export default function Pricing() {
  const navigate = useNavigate();
  const { auth } = useAppStore();
  const [loadingPlan, setLoadingPlan] = useState<string | null>(null);
  const [checkoutError, setCheckoutError] = useState('');

  const handleCheckout = async (plan: typeof plans[1]) => {
    if (!plan.stripe_price_id) return;
    if (!auth.token) {
      navigate('/settings');
      return;
    }

    setLoadingPlan(plan.plan_name);
    setCheckoutError('');
    try {
      const { data } = await api.post<{ session_url: string }>(
        '/payments/create-checkout-session',
        { price_id: plan.stripe_price_id, plan_name: plan.plan_name }
      );
      window.location.href = data.session_url;
    } catch {
      setCheckoutError('Checkout is unavailable right now. Open Settings to confirm authentication or contact support.');
    } finally {
      setLoadingPlan(null);
    }
  };

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="text-center mb-12">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
          Win More Tenders with AI
        </h1>
        <p className="text-gray-500 dark:text-gray-400 mt-2">
          Choose the plan that fits your bidding volume.
        </p>
      </div>

      {checkoutError && (
        <div className="mb-6 rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 px-4 py-3 text-sm text-amber-800 dark:text-amber-200">
          {checkoutError}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
        {plans.map((plan) => (
          <div
            key={plan.plan_name}
            className={`relative bg-white dark:bg-gray-800 rounded-2xl border p-8 flex flex-col ${
              plan.popular
                ? 'border-primary-500 shadow-xl scale-105'
                : 'border-gray-200 dark:border-gray-700'
            }`}
          >
            {plan.popular && (
              <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-primary-500 text-white text-xs font-bold px-3 py-1 rounded-full">
                MOST POPULAR
              </div>
            )}

            <h3 className="text-xl font-bold text-gray-900 dark:text-white">{plan.name}</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{plan.description}</p>

            <div className="mt-6 flex items-baseline">
              <span className="text-4xl font-bold text-gray-900 dark:text-white">{plan.price}</span>
              <span className="text-gray-500 dark:text-gray-400 ml-1">{plan.period}</span>
            </div>

            <ul className="mt-8 space-y-3 flex-1">
              {plan.features.map((feature, i) => (
                <li key={i} className="flex items-start gap-3 text-sm text-gray-600 dark:text-gray-300">
                  <Check size={18} className="text-green-500 shrink-0 mt-0.5" />
                  {feature}
                </li>
              ))}
            </ul>

            <button
              onClick={() => handleCheckout(plan)}
              disabled={plan.disabled || loadingPlan === plan.plan_name}
              className={`mt-8 w-full py-3 rounded-xl font-semibold transition-all flex items-center justify-center gap-2 ${
                plan.popular
                  ? 'bg-primary-600 text-white hover:bg-primary-700 disabled:bg-primary-400'
                  : 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-white hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50'
              }`}
            >
              {loadingPlan === plan.plan_name ? (
                <><Loader2 className="animate-spin" size={18} /> Redirecting...</>
              ) : plan.disabled ? (
                'Current Plan'
              ) : (
                plan.cta
              )}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
