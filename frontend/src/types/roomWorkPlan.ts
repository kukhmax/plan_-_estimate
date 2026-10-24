import { QualityLevelValue, SubstrateValue } from './checklist';

/** The plan of the works of a whole room (V2-5): the ordered price rows of the walls and of the ceiling. */
export interface RoomWorkPlan {
  id: string;
  room_id: string;
  substrate: SubstrateValue;
  quality_target: QualityLevelValue | null;
  walls: string[];
  ceiling: string[];
  updated_at: string | null;
}

export type SurfacePlanStateValue = 'NONE' | 'FOLLOWS' | 'OWN';
export type RoomPlanOutcomeValue = 'CREATED' | 'UPDATED' | 'SKIPPED_OWN' | 'SKIPPED_STARTED' | 'SKIPPED_EMPTY';

export interface SurfacePlanState {
  surface_id: string;
  name: string;
  surface_type: 'WALL' | 'CEILING' | 'FLOOR' | 'OTHER';
  state: SurfacePlanStateValue;
  started: boolean;
}

export interface SurfacePlanOutcome {
  surface_id: string;
  name: string;
  surface_type: 'WALL' | 'CEILING' | 'FLOOR' | 'OTHER';
  outcome: RoomPlanOutcomeValue;
}

export interface RoomWorkPlanResponse {
  plan: RoomWorkPlan | null;
  surfaces: SurfacePlanState[];
  results: SurfacePlanOutcome[];
}

export interface RoomWorkPlanWritePayload {
  substrate: SubstrateValue;
  quality_target: QualityLevelValue | null;
  walls: string[];
  ceiling: string[];
}
