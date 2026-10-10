/** Catalogues of the contract and the protocols (Stage 16B.3). The server owns the content; a screen only draws it. A number is
 * never part of a catalogue: it is an answer of the owner in the questionnaire. */

export type RequirementGroup = 'LIGHTING' | 'GLAZING' | 'CLIMATE' | 'UTILITIES' | 'ACCESS' | 'CLEANLINESS' | 'SUBSTRATE';
export type RequirementValueKind = 'YES_NO' | 'NUMBER' | 'NUMBER_RANGE';
export type CatalogUnit = 'lx' | '°C' | '%' | 'days' | 'months' | 'working_days' | 'PLN' | 'mm' | 'mm/m';

export interface PremisesRequirement {
  key: string;
  group: RequirementGroup;
  value_kind: RequirementValueKind;
  unit: CatalogUnit | null;
  label_key: string;
  text_pl: string;
}

export type AssessmentMeasure =
  | 'FLATNESS'
  | 'VERTICALITY'
  | 'HORIZONTALITY'
  | 'DIMENSIONS'
  | 'MOISTURE'
  | 'SURFACE_APPEARANCE'
  | 'ADHESION';

export interface AssessmentInstrument {
  key: string;
  measures: AssessmentMeasure[];
  label_key: string;
  text_pl: string;
}

export type QualityClass = 'S1' | 'S2' | 'S3' | 'S4' | 'Q1' | 'Q2' | 'Q3' | 'Q4';
export type LightingKind = 'NONE_SPECIFIED' | 'DIFFUSE' | 'DEMANDING' | 'AGREED_BEFORE_WORK' | 'RAKING_LIGHT';

export interface EvaluationCondition {
  key: QualityClass;
  lighting: LightingKind;
  requires_agreement: boolean;
  label_key: string;
  text_pl: string;
}

export type DefectOutcome = 'ACCEPTED_WITH_REMARKS' | 'NOT_ACCEPTED';

export interface DefectClass {
  key: 'REMOVABLE' | 'SIGNIFICANT';
  outcome: DefectOutcome;
  label_key: string;
  text_pl: string;
  /** null until the owner and the lawyer approve the criteria. */
  criteria_pl: string | null;
}

export interface Tolerance {
  key: string;
  parameter: AssessmentMeasure;
  instrument_keys: string[];
  limit_value: string;
  unit: 'mm' | 'mm/m';
  norm_ref: string;
  applies_to: QualityClass[];
  label_key: string;
  text_pl: string;
}

export type QuestionGroup = 'PARTIES' | 'DATES' | 'PRICE' | 'PAYMENT' | 'WORK' | 'WARRANTY' | 'PENALTY' | 'DOWNTIME' | 'ACCEPTANCE' | 'PREMISES';
export type QuestionKind =
  | 'TEXT'
  | 'DATE'
  | 'NUMBER'
  | 'MONEY_PLN'
  | 'PERCENT'
  | 'DAYS'
  | 'MONTHS'
  | 'YES_NO'
  | 'CHOICE'
  | 'PERSON_LIST'
  | 'REQUIREMENT_VALUES';

export interface ContractQuestion {
  key: string;
  group: QuestionGroup;
  kind: QuestionKind;
  /** OPEN: may stay empty — the document prints a field to fill in by hand ("......"). */
  requirement: 'REQUIRED' | 'OPEN';
  default: number | boolean | null;
  options: string[] | null;
  unit: CatalogUnit | null;
  label_key: string;
  hint_key: string | null;
}

interface Catalog<T> {
  version: number;
  items: T[];
}

export interface WorkKind {
  key: string;
  label_key: string;
  text_pl: string;
}

/** A cause of a downtime on the customer's side (the notice and the protocol of downtime, Stage 16I). */
export interface DowntimeCause {
  key: string;
  label_key: string;
  text_pl: string;
}

export interface ContractCatalog {
  requirements: Catalog<PremisesRequirement>;
  instruments: Catalog<AssessmentInstrument>;
  evaluation: Catalog<EvaluationCondition>;
  defects: Catalog<DefectClass>;
  tolerances: Catalog<Tolerance>;
  questionnaire: Catalog<ContractQuestion>;
  /** The kinds of work that are covered by the next layers (the protocol of concealed works, Stage 16G). */
  work_kinds: Catalog<WorkKind>;
  /** The causes of a downtime (contract § 10 ust. 1). */
  downtime_causes: Catalog<DowntimeCause>;
}
