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
});
