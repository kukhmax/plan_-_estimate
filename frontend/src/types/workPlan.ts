import { QualityLevelValue, SubstrateValue } from './checklist';
import { PriceCategoryValue, PriceScopeValue, PriceUnitValue } from './priceItem';

export interface SurfacePriceItemSummaryRead {
  id: string;
  code: string;
  name_key: string | null;
  display_name: string | null;
  category: PriceCategoryValue;
  unit: PriceUnitValue;
  price_scope: PriceScopeValue;
  price: string | null;
  currency: string;
  is_archived: boolean;
  quality_level: QualityLevelValue | null;
}

export interface PlannedWorkCoefficientOptionRead {
  id: string;
  group_id: string;
  group_code: string;
  code: string;
  display_name: string | null;
  percentage: string;
  is_base: boolean;
}

export interface OrderedPriceItemSelection {
  price_item_id: string;
  coefficient_option_ids: string[];
}

export interface SurfacePlannedWorkRead {
  id: string;
  work_plan_id: string;
  price_item_id: string;
  position: number;
  price_item: SurfacePriceItemSummaryRead | null;
  coefficient_options?: PlannedWorkCoefficientOptionRead[];
}

export interface SurfaceWorkPlanRead {
  id: string;
  surface_id: string;
  substrate: SubstrateValue;
  quality_target: QualityLevelValue | null;
  planned_works: SurfacePlannedWorkRead[];
}

export interface SurfaceWorkPlanUpsert {
  substrate: SubstrateValue;
  quality_target: QualityLevelValue | null;
  price_item_ids?: string[];
  planned_works?: OrderedPriceItemSelection[];
}

export interface SurfaceWorkPlanApplyResult {
  source_surface_id: string;
  target_count: number;
  target_surface_ids: string[];
  targets: SurfaceWorkPlanRead[];
}
