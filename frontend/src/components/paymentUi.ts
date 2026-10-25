/** The classes the money screens share (V2-9: the schedule, the hours, the margin); the same look as "Faktury i zaliczki". */
export const primaryButton = 'w-full min-h-11 px-4 py-2 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition disabled:opacity-50';
export const secondaryButton = 'w-full min-h-11 px-3 py-2 text-sm rounded-xl border border-slate-200 pe-surface text-slate-700 font-medium hover:bg-slate-50 disabled:opacity-50';
export const dangerButton = 'w-full min-h-11 px-3 py-2 text-sm rounded-xl border border-red-200 bg-red-50 text-red-800 font-semibold hover:bg-red-100 disabled:opacity-50';
export const fieldClass = 'w-full min-h-11 border border-slate-200 rounded-xl px-3 py-2 text-base text-slate-900 pe-surface';
export const labelClass = 'block text-xs font-semibold text-slate-600 mb-1';
export const segmentClass = (active: boolean) =>
  `flex-1 min-h-11 px-3 py-2 text-sm rounded-xl border font-semibold break-words ${
    active ? 'bg-blue-600 border-blue-600 text-white' : 'pe-surface border-slate-200 text-slate-700'
  }`;
