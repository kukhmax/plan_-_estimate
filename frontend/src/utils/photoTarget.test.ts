import { describe, expect, it } from 'vitest';
import { makeItem } from '../test/photoFixtures';
import { attachmentTarget, targetIdOf } from './photoTarget';

describe('photoTarget helpers', () => {
  it('picks the leaf id that belongs to the context', () => {
    expect(targetIdOf({ context: 'PROJECT' })).toBeUndefined();
    expect(targetIdOf({ context: 'ROOM', roomId: 'r', surfaceId: 's', openingId: 'o' })).toBe('r');
    expect(targetIdOf({ context: 'SURFACE', roomId: 'r', surfaceId: 's', openingId: 'o' })).toBe('s');
    expect(targetIdOf({ context: 'OPENING', roomId: 'r', surfaceId: 's', openingId: 'o' })).toBe('o');
    expect(targetIdOf({ context: 'INSPECTION', inspectionId: 'i', findingId: 'f' })).toBe('i');
    expect(targetIdOf({ context: 'FINDING', inspectionId: 'i', findingId: 'f' })).toBe('f');
  });

  it('reads context and leaf id from an attachment', () => {
    const room = makeItem({ attachment: { context: 'ROOM', room_id: 'r1' } }).attachment;
    expect(attachmentTarget(room)).toEqual({ context: 'ROOM', targetId: 'r1', questionId: undefined });
    const opening = makeItem({ attachment: { context: 'OPENING', room_id: null, surface_id: null, opening_id: 'o1' } }).attachment;
    expect(attachmentTarget(opening)).toEqual({ context: 'OPENING', targetId: 'o1', questionId: undefined });
    const project = makeItem({ attachment: { context: 'PROJECT', room_id: null } }).attachment;
    expect(attachmentTarget(project)).toEqual({ context: 'PROJECT', targetId: undefined, questionId: undefined });
  });

  it('reads the inspection, the question and the finding of evidence attachments', () => {
    const inspection = makeItem({ attachment: { context: 'INSPECTION', room_id: null, inspection_id: 'i1' } }).attachment;
    expect(attachmentTarget(inspection)).toEqual({ context: 'INSPECTION', targetId: 'i1', questionId: undefined });
    const question = makeItem({ attachment: { context: 'INSPECTION', room_id: null, inspection_id: 'i1', question_id: 'q1' } }).attachment;
    expect(attachmentTarget(question)).toEqual({ context: 'INSPECTION', targetId: 'i1', questionId: 'q1' });
    const finding = makeItem({ attachment: { context: 'FINDING', room_id: null, finding_id: 'f1' } }).attachment;
    expect(attachmentTarget(finding)).toEqual({ context: 'FINDING', targetId: 'f1', questionId: undefined });
  });
});
