export type ThemeColor =
  | 'amber'
  | 'blue'
  | 'cyan'
  | 'emerald'
  | 'green'
  | 'gray'
  | 'indigo'
  | 'orange'
  | 'pink'
  | 'purple'
  | 'red'
  | 'slate'
  | 'teal'
  | 'yellow';

export interface ThemeClasses {
  panel: string;
  icon: string;
  text: string;
  border: string;
  fill: string;
}

const DEFAULT_CLASSES: ThemeClasses = {
  panel: 'bg-gray-50 dark:bg-gray-900/20',
  icon: 'text-gray-600 dark:text-gray-400',
  text: 'text-gray-700 dark:text-gray-300',
  border: 'border-gray-200 dark:border-gray-700',
  fill: 'bg-gray-500',
};

export const COLOR_CLASSES: Record<ThemeColor, ThemeClasses> = {
  amber: {
    panel: 'bg-amber-50 dark:bg-amber-900/20',
    icon: 'text-amber-600 dark:text-amber-400',
    text: 'text-amber-700 dark:text-amber-300',
    border: 'border-amber-200 dark:border-amber-800',
    fill: 'bg-amber-500',
  },
  blue: {
    panel: 'bg-blue-50 dark:bg-blue-900/20',
    icon: 'text-blue-600 dark:text-blue-400',
    text: 'text-blue-700 dark:text-blue-300',
    border: 'border-blue-200 dark:border-blue-800',
    fill: 'bg-blue-500',
  },
  cyan: {
    panel: 'bg-cyan-50 dark:bg-cyan-900/20',
    icon: 'text-cyan-600 dark:text-cyan-400',
    text: 'text-cyan-700 dark:text-cyan-300',
    border: 'border-cyan-200 dark:border-cyan-800',
    fill: 'bg-cyan-500',
  },
  emerald: {
    panel: 'bg-emerald-50 dark:bg-emerald-900/20',
    icon: 'text-emerald-600 dark:text-emerald-400',
    text: 'text-emerald-700 dark:text-emerald-300',
    border: 'border-emerald-200 dark:border-emerald-800',
    fill: 'bg-emerald-500',
  },
  green: {
    panel: 'bg-green-50 dark:bg-green-900/20',
    icon: 'text-green-600 dark:text-green-400',
    text: 'text-green-700 dark:text-green-300',
    border: 'border-green-200 dark:border-green-800',
    fill: 'bg-green-500',
  },
  gray: DEFAULT_CLASSES,
  indigo: {
    panel: 'bg-indigo-50 dark:bg-indigo-900/20',
    icon: 'text-indigo-600 dark:text-indigo-400',
    text: 'text-indigo-700 dark:text-indigo-300',
    border: 'border-indigo-200 dark:border-indigo-800',
    fill: 'bg-indigo-500',
  },
  orange: {
    panel: 'bg-orange-50 dark:bg-orange-900/20',
    icon: 'text-orange-600 dark:text-orange-400',
    text: 'text-orange-700 dark:text-orange-300',
    border: 'border-orange-200 dark:border-orange-800',
    fill: 'bg-orange-500',
  },
  pink: {
    panel: 'bg-pink-50 dark:bg-pink-900/20',
    icon: 'text-pink-600 dark:text-pink-400',
    text: 'text-pink-700 dark:text-pink-300',
    border: 'border-pink-200 dark:border-pink-800',
    fill: 'bg-pink-500',
  },
  purple: {
    panel: 'bg-purple-50 dark:bg-purple-900/20',
    icon: 'text-purple-600 dark:text-purple-400',
    text: 'text-purple-700 dark:text-purple-300',
    border: 'border-purple-200 dark:border-purple-800',
    fill: 'bg-purple-500',
  },
  red: {
    panel: 'bg-red-50 dark:bg-red-900/20',
    icon: 'text-red-600 dark:text-red-400',
    text: 'text-red-700 dark:text-red-300',
    border: 'border-red-200 dark:border-red-800',
    fill: 'bg-red-500',
  },
  slate: {
    panel: 'bg-slate-50 dark:bg-slate-900/20',
    icon: 'text-slate-600 dark:text-slate-400',
    text: 'text-slate-700 dark:text-slate-300',
    border: 'border-slate-200 dark:border-slate-700',
    fill: 'bg-slate-500',
  },
  teal: {
    panel: 'bg-teal-50 dark:bg-teal-900/20',
    icon: 'text-teal-600 dark:text-teal-400',
    text: 'text-teal-700 dark:text-teal-300',
    border: 'border-teal-200 dark:border-teal-800',
    fill: 'bg-teal-500',
  },
  yellow: {
    panel: 'bg-yellow-50 dark:bg-yellow-900/20',
    icon: 'text-yellow-600 dark:text-yellow-400',
    text: 'text-yellow-700 dark:text-yellow-300',
    border: 'border-yellow-200 dark:border-yellow-800',
    fill: 'bg-yellow-500',
  },
};

export function getThemeClasses(color?: string | null): ThemeClasses {
  if (!color) return DEFAULT_CLASSES;
  return COLOR_CLASSES[color.toLowerCase() as ThemeColor] || DEFAULT_CLASSES;
}
