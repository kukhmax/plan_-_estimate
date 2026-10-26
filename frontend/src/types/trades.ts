/** The packages of professions of an owner (V2-13; mirrors backend `schemas/trades.py`). */
export type TradeKey = 'FINISHING' | 'DRYWALL' | 'MICROCEMENT' | 'TILE' | 'ELECTRIC' | 'PLUMBING';

export interface Trade {
  key: TradeKey;
  /** The categories of the price book (and so the works and the points) this trade owns. */
  price_categories: string[];
  /** The packages of the materials of a room this trade owns. */
  material_packages: string[];
}

export interface TradesResponse {
  trades: Trade[];
  /** The categories no trade owns: always offered. */
  always_categories: string[];
  enabled: TradeKey[];
}
