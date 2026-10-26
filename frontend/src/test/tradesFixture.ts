import type { TradesResponse } from '../types/trades';

/** A catalogue as the server sends it (the same six trades, in the order of the owner), every trade on. */
export const CATALOG: TradesResponse = {
  trades: [
    { key: 'FINISHING', price_categories: ['PREPARATION', 'SKIM_COAT', 'PAINTING'], material_packages: [] },
    { key: 'DRYWALL', price_categories: ['DRYWALL'], material_packages: ['DRYWALL'] },
    { key: 'MICROCEMENT', price_categories: ['MICROCEMENT'], material_packages: [] },
    { key: 'TILE', price_categories: ['TILE'], material_packages: ['TILE'] },
    { key: 'ELECTRIC', price_categories: ['ELECTRICAL'], material_packages: ['ELECTRIC'] },
    { key: 'PLUMBING', price_categories: ['PLUMBING'], material_packages: ['PLUMBING'] },
  ],
  always_categories: ['POINTS_ROUTES', 'MATERIAL', 'OTHER'],
  enabled: ['FINISHING', 'DRYWALL', 'MICROCEMENT', 'TILE', 'ELECTRIC', 'PLUMBING'],
};
