import { describe, expect, it } from 'vitest';
import { makeItem } from '../test/photoFixtures';
import { attachmentTarget, targetIdOf } from './photoTarget';

describe('photoTarget helpers', () => {
  it('picks the leaf id that belongs to the context', () => {
    expect(targetIdOf({ context: 'PROJECT' })).toBeUndefined();
    expect(targetIdOf({ context: 'ROOM', roomId: 'r', surfaceId: 's', openingId: 'o' })).toBe('r');
    expect(targetIdOf({ context: 'SURFACE', roomId: 'r', surfaceId: 's', openingId: 'o' })).toBe('s');
    expect(targetIdOf({ context: 'OPENING', roomId: 'r', surfaceId: 's', openingId: 'o' })).toBe('o');
  });

  it('reads context and leaf id from an attachment', () => {
    const room = makeItem({ attachment: { context: 'ROOM', room_id: 'r1' } }).attachment;
    expect(attachmentTarget(room)).toEqual({ context: 'ROOM', targetId: 'r1' });
    const opening = makeItem({ attachment: { context: 'OPENING', room_id: null, surface_id: null, opening_id: 'o1' } }).attachment;
    expect(attachmentTarget(opening)).toEqual({ context: 'OPENING', targetId: 'o1' });
    const project = makeItem({ attachment: { context: 'PROJECT', room_id: null } }).attachment;
    expect(attachmentTarget(project)).toEqual({ context: 'PROJECT', targetId: undefined });
  });
});
