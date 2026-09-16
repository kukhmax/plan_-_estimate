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

export interface SurfacePlannedWorkRead {
  id: string;
  work_plan_id: string;
  price_item_id: string;
  position: number;
  price_item: SurfacePriceItemSummaryRead | null;
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
  price_item_ids: string[];
}
