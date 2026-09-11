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
