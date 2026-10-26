/** The norms, the calculations and the statement of materials (V2-11, V2-12); mirrors backend `schemas/material.py`. Quantities arrive as strings; the server counts everything. */
import type { PointItem } from './roomPoints';

export type MaterialPackage = 'TILE' | 'DRYWALL' | 'ELECTRIC' | 'PLUMBING';

export interface TileParams {
  area_m2: string;
  length_cm: string;
  width_cm: string;
  thickness_mm: string;
  joint_mm: string;
  layout: 'STRAIGHT' | 'DIAGONAL';
  waterproof: boolean;
  waterproof_area_m2: string | null;
  tape_m: string | null;
}

export interface DrywallParams {
  kind: 'WALL' | 'CEILING';
  area_m2: string;
  layers: 1 | 2;
  height_m: string | null;
  perimeter_m: string | null;
}

export interface ElectricParams {
  sockets: number;
  switches: number;
  lights: number;
  circuits: number;
  route_m: string | null;
}

export interface PlumbingParams {
  water_points: number;
  drain_points: number;
  manifold_outlets: number;
  pipe_m: string | null;
}

/** The metres of the routes the owner listed in a room, by trade. */
export interface RouteTotals {
  electrical_m: string;
  plumbing_m: string;
}

export interface MaterialLine {
  code: string;
  name: string;
  /** The exact need in `unit_text`. */
  quantity: string;
  unit_text: string;
  pack_size: string | null;
  packs: number | null;
  pieces: number | null;
  /** The unit and the quantity of a line of an estimate: M2 for the tile, whole packs (PCS) for the rest. */
  billing_unit: string;
  billing_quantity: string;
}

export interface MaterialCalc {
  id: string;
  room_id: string;
  package: MaterialPackage;
  title: string | null;
  params: Partial<TileParams> & Partial<DrywallParams> & Partial<ElectricParams> & Partial<PlumbingParams>;
  materials: MaterialLine[];
  created_at: string;
  updated_at: string;
}

export type CalcFields =
  | { package: 'TILE'; title: string | null; params: TileParams }
  | { package: 'DRYWALL'; title: string | null; params: DrywallParams }
  | { package: 'ELECTRIC'; title: string | null; params: ElectricParams }
  | { package: 'PLUMBING'; title: string | null; params: PlumbingParams };

export interface MaterialTotal extends MaterialLine {
  package: MaterialPackage;
  price_item_id: string | null;
  unit_price: string | null;
  amount: string | null;
}

export interface StatementCalc extends MaterialCalc {
  room_name: string;
}

export interface Statement {
  calcs: StatementCalc[];
  totals: MaterialTotal[];
  amount: string | null;
  unpriced: number;
}

export interface MaterialNorm {
  id: string;
  code: string;
  package: MaterialPackage;
  kind: 'PARAM' | 'MATERIAL';
  name: string;
  default_name: string;
  unit_text: string;
  value: string | null;
  default_value: string | null;
  minimum: string | null;
  maximum: string | null;
  billing_unit: string | null;
  price_item: PointItem | null;
}

export interface NormChanges {
  value?: string;
  name?: string;
  price_item_id?: string | null;
  reset?: boolean;
}

export interface AddMaterialsResult {
  added: number;
  already: number;
  skipped: string[];
}
