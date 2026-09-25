import { describe, expect, it } from 'vitest';
import pl from './pl.json';
import ru from './ru.json';

type Dict = Record<string, unknown>;

function keySet(node: unknown, prefix = ''): Set<string> {
  const keys = new Set<string>();
  if (node && typeof node === 'object') {
    for (const [key, value] of Object.entries(node as Dict)) {
      const path = prefix ? `${prefix}.${key}` : key;
      keys.add(path);
      if (value && typeof value === 'object') {
        for (const child of keySet(value, path)) keys.add(child);
      }
    }
  }
  return keys;
}

describe('PL/RU locale parity (LOCALIZATION)', () => {
  it('has identical app-shell and auth key structure in PL and RU (Stage 9D.1)', () => {
    const plApp = keySet(pl.app);
    const ruApp = keySet(ru.app);
    expect(plApp).toEqual(ruApp);

    const plAuth = keySet(pl.auth);
    const ruAuth = keySet(ru.auth);
    expect(plAuth).toEqual(ruAuth);

    const plCommon = keySet(pl.common);
    const ruCommon = keySet(ru.common);
    expect(plCommon).toEqual(ruCommon);

    // The compact account control + modal labels required by the 9D.1 spec.
    for (const key of [
      'account',
      'account_title',
      'telegram_verified',
      'telegram_user_id',
      'username',
      'uuid',
    ]) {
      expect(plAuth.has(key)).toBe(true);
    }
  });

  it('has identical inspection and checklist key structure in PL and RU', () => {
    const plKeys = keySet(pl.inspections);
    const ruKeys = keySet(ru.inspections);
    expect(plKeys).toEqual(ruKeys);

    const plChecklist = keySet(pl.checklist);
    const ruChecklist = keySet(ru.checklist);
    expect(plChecklist).toEqual(ruChecklist);

    const plRisk = keySet(pl.risk);
    const ruRisk = keySet(ru.risk);
    expect(plRisk).toEqual(ruRisk);

    const plSurfaces = keySet(pl.surfaces);
    const ruSurfaces = keySet(ru.surfaces);
    expect(plSurfaces).toEqual(ruSurfaces);
    // The Stage 10C.1 progressive-disclosure controls on the surface card.
    for (const key of ['options', 'hide_options', 'work_types_quality']) {
      expect(plSurfaces.has(key)).toBe(true);
    }

    const plComm = keySet(pl.communication);
    const ruComm = keySet(ru.communication);
    expect(plComm).toEqual(ruComm);
  });

  it('contains every backend communication phrase and category key (Stage 8)', () => {
    const plComm = keySet(pl.communication);
    // Every category the backend CommunicationCategory enum can emit.
    for (const category of [
      'explain_condition',
      'explain_consequence',
      'recommend_preparation',
      'require_client_decision',
      'scope_clarification',
      'quality_expectation',
      'document_agreement',
      'general',
    ]) {
      expect(plComm.has(`category.${category}`)).toBe(true);
    }
    // Every finding-only / quality phrase slug materialized by the backend catalog.
    for (const slug of [
      'comm_find_unevenness',
      'comm_find_unevenness_gypsum_plaster',
      'comm_find_unevenness_gypsum_plaster_s3',
      'comm_find_board_movement',
      'comm_find_joint_gap',
      'comm_quality_gypsum_plaster_s3',
      'comm_quality_gypsum_board_q2',
      'comm_quality_concrete_s4',
      'comm_quality_painted_s2',
      'comm_quality_cement_lime_plaster_s1',
      'comm_quality_cement_lime_plaster_s2',
      'comm_quality_cement_lime_plaster_s3',
      'comm_quality_cement_lime_plaster_s4',
      'comm_quality_concrete_s1',
      'comm_quality_concrete_s2',
      'comm_quality_concrete_s3',
      'comm_quality_gypsum_board_q1',
      'comm_quality_gypsum_board_q3',
      'comm_quality_gypsum_board_q4',
      'comm_quality_gypsum_plaster_s1',
      'comm_quality_gypsum_plaster_s2',
      'comm_quality_gypsum_plaster_s4',
    ]) {
      expect(plComm.has(`${slug}.phrase`)).toBe(true);
      expect(plComm.has(`${slug}.why`)).toBe(true);
    }
  });

  it('contains every backend risk dotted key and source-finding label', () => {
    const plRisk = keySet(pl.risk);
    const ruleSlugs = [
      'crack_recurrence',
      'board_movement_crack',
      'moisture_block_finishing',
      'weak_adhesion_prep',
      'loose_substrate_removal',
      'dusty_substrate_prime',
      'oily_substrate_degrease',
      'mold_treatment_before_finish',
      'delamination_repair',
      'unevenness_prep_increased',
      'joint_tape_missing_rework',
      'fastener_corrosion_fix',
      'joint_gap_filling',
      'efflorescence_cause_check',
      'blow_holes_filling',
    ];
    for (const slug of ruleSlugs) {
      for (const field of ['title', 'explanation', 'consequence', 'mitigation', 'communication']) {
        expect(plRisk.has(`${slug}.${field}`)).toBe(true);
      }
    }
    const findingKeys = [
      'crack',
      'board_movement',
      'high_moisture',
      'weak_adhesion',
      'loose_substrate',
      'dusty_substrate',
      'oily_substrate',
      'mold',
      'delamination',
      'unevenness',
      'joint_tape_missing',
      'fastener_corrosion',
      'joint_gap',
      'efflorescence',
      'blow_holes',
    ];
    for (const key of findingKeys) {
      expect(plRisk.has(`finding.${key}`)).toBe(true);
    }
  });

  it('has identical WorkPlan key structure in PL and RU (Stage 10C.2A)', () => {
    const plWorkPlan = keySet(pl.work_plan);
    const ruWorkPlan = keySet(ru.work_plan);
    expect(plWorkPlan).toEqual(ruWorkPlan);

    for (const key of [
      'title',
      'loading',
      'error_load',
      'error_save',
      'retry',
      'no_plan',
      'planned_works',
      'no_works',
      'preview_read_only',
      'unavailable_item',
      'saved',
    ]) {
      expect(plWorkPlan.has(key)).toBe(true);
    }
  });

  it('has identical pricebook key structure in PL and RU (Stage 9D)', () => {
    const plPricebook = keySet(pl.pricebook);
    const ruPricebook = keySet(ru.pricebook);
    expect(plPricebook).toEqual(ruPricebook);

    // Every backend machine enum member that the UI must be able to label.
    for (const category of [
      'PREPARATION',
      'SKIM_COAT',
      'PLASTER',
      'DRYWALL',
      'PAINTING',
      'GLASS_FIBER',
      'MICROCEMENT',
      'DECORATIVE',
      'REVEAL',
      'MATERIAL',
      'OTHER',
    ]) {
      expect(plPricebook.has(`categories.${category}`)).toBe(true);
    }
    for (const unit of ['M2', 'LM', 'PCS', 'HOUR', 'DAY', 'FLAT']) {
      expect(plPricebook.has(`units.${unit}`)).toBe(true);
    }
    for (const scope of ['LABOR', 'MATERIAL', 'LABOR_AND_MATERIAL']) {
      expect(plPricebook.has(`scopes.${scope}`)).toBe(true);
    }
    for (const quality of ['S1', 'S2', 'S3', 'S4', 'Q1', 'Q2', 'Q3', 'Q4']) {
      expect(plPricebook.has(`quality.${quality}`)).toBe(true);
    }
    // Every name_key of the approved 44-row catalog (28 MS / 16 OWN_PRICE).
    for (const seedKey of [
      'prep_prot',
      'prep_wallp',
      'prep_scrape',
      'prep_fleece',
      'prep_degr',
      'prep_mold',
      'prep_clean',
      'prim_std',
      'prim_adh',
      'prim_high',
      'prim_paint',
      'skim_1l',
      'skim_2l',
      'skim_sand',
      'skim_crack',
      'skim_corner',
      'skim_local',
      'skim_sq',
      'gk_joint',
      'gk_full',
      'gk_screw',
      'gk_corner',
      'gk_q4',
      'gf_fliz_l',
      'gf_fliz_m',
      'gf_mesh',
      'paint_2k',
      'paint_1k',
      'paint_3k',
      'paint_ceil',
      'paint_col',
      'paint_mask',
      'paint_multi',
      'rev_work_lm',
      'mc_wall_l',
      'mc_wall_s',
      'mc_floor_l',
      'mc_floor_s',
      'mc_shower',
      'mc_stairs',
      'dec_ven',
      'dec_ven_mar',
      'dec_conc',
      'dec_generic',
    ]) {
      expect(plPricebook.has(`seed.${seedKey}`)).toBe(true);
    }
  });

  it('has identical reveals key structure in PL and RU (Stage 5F)', () => {
    const plReveals = keySet(pl.reveals);
    const ruReveals = keySet(ru.reveals);
    expect(plReveals).toEqual(ruReveals);

    for (const key of [
      'toggle',
      'depth',
      'sides',
      'side_left',
      'side_right',
      'side_top',
      'side_bottom',
      'length',
      'area',
      'per_opening',
      'total',
      'summary_title',
      'summary_windows',
      'summary_doors',
      'summary_combined',
    ]) {
      expect(plReveals.has(key)).toBe(true);
    }
  });

  it('contains every backend checklist dotted key used by templates', () => {
    const plChecklist = keySet(pl.checklist);
    const backendKeys = [
      'checklist.template.concrete.title',
      'checklist.template.gypsum_plaster.title',
      'checklist.template.cement_lime_plaster.title',
      'checklist.template.gypsum_board.title',
      'checklist.template.painted.title',
      'checklist.template.other.title',
      'checklist.section.general_conditions',
      'checklist.section.drywall_joints',
      'checklist.question.cracks_present',
      'checklist.question.unevenness_mm',
      'checklist.question.substrate_condition',
      'checklist.question.present_defects',
      'checklist.question.moisture_high',
      'checklist.question.adhesion_weak',
      'checklist.question.notes',
      'checklist.question.joint_tape_missing',
      'checklist.question.board_movement',
      'checklist.question.fastener_corrosion',
      'checklist.question.joint_gap_mm',
      'checklist.option.substrate_solid',
      'checklist.option.substrate_loose',
      'checklist.option.substrate_dusty',
      'checklist.option.substrate_oily',
      'checklist.option.defect_delamination',
      'checklist.option.defect_blow_holes',
      'checklist.option.defect_efflorescence',
      'checklist.option.defect_mold',
    ];
    for (const key of backendKeys) {
      const bare = key.replace('checklist.', '');
      expect(plChecklist.has(bare)).toBe(true);
    }
  });

  it('has identical coefficients key structure in PL and RU (Stage 12F)', () => {
    const plCoefficients = keySet(pl.coefficients);
    const ruCoefficients = keySet(ru.coefficients);
    expect(plCoefficients).toEqual(ruCoefficients);

    for (const key of [
      'title',
      'modal_title',
      'base_price',
      'adjustment',
      'effective_price',
      'unresolved_price',
      'none_option',
      'base_badge',
      'apply',
      'cancel',
      'close',
      'save',
      'saving',
      'edit',
      'archive',
      'restore',
      'no_groups',
      'add_group',
      'add_option',
      'group_name',
      'group_name_placeholder',
      'option_name',
      'option_name_placeholder',
      'percentage',
      'is_base_label',
      'archived_badge',
      'active_tab',
      'archived_tab',
      'tab_items',
      'tab_coefficients',
      'loading',
      'error_load',
      'error_save',
      'validation_name_required',
      'validation_percentage_required',
      'description',
      'description_placeholder',
      'description_optional',
      'show_description',
      'high_total_warning',
      'option_count',
      'base_summary',
      'no_base_summary',
    ]) {
      expect(plCoefficients.has(key)).toBe(true);
    }

    expect((pl.work_plan as Dict).coefficient_action).toBeDefined();
    expect((ru.work_plan as Dict).coefficient_action).toBeDefined();
    expect((pl.reveals as Dict).work_coefficient_action).toBeDefined();
    expect((ru.reveals as Dict).work_coefficient_action).toBeDefined();
    expect((pl.estimates as Dict).base_unit_price).toBeDefined();
    expect((ru.estimates as Dict).base_unit_price).toBeDefined();
    expect((pl.estimates as Dict).coefficients_applied).toBeDefined();
    expect((ru.estimates as Dict).coefficients_applied).toBeDefined();
    expect((pl.estimates as Dict).price_override_badge).toBeDefined();
    expect((ru.estimates as Dict).price_override_badge).toBeDefined();
  });
});
