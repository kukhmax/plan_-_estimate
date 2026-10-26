import type { TradesResponse } from '../types/trades';

/** A catalogue as the server sends it (the same six trades, in the order of the owner), every trade on. */
export const CATALOG: TradesResponse = {
  trades: [
    { key: 'FINISHING', price_categories: ['PREPARATION', 'SKIM_COAT', 'PAINTING'], material_packages: [], room_points: false },
    { key: 'DRYWALL', price_categories: ['DRYWALL'], material_packages: ['DRYWALL'], room_points: true },
    { key: 'MICROCEMENT', price_categories: ['MICROCEMENT'], material_packages: [], room_points: false },
    { key: 'TILE', price_categories: ['TILE'], material_packages: ['TILE'], room_points: true },
    { key: 'ELECTRIC', price_categories: ['ELECTRICAL'], material_packages: ['ELECTRIC'], room_points: true },
    { key: 'PLUMBING', price_categories: ['PLUMBING'], material_packages: ['PLUMBING'], room_points: true },
  ],
  always_categories: ['POINTS_ROUTES', 'MATERIAL', 'OTHER'],
  enabled: ['FINISHING', 'DRYWALL', 'MICROCEMENT', 'TILE', 'ELECTRIC', 'PLUMBING'],
};
