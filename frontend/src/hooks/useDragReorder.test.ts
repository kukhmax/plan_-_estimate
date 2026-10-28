import { describe, expect, it } from 'vitest';
import { dropIndex, moveItem } from './useDragReorder';

describe('moveItem', () => {
  it('moves one item and keeps the order of the others', () => {
    expect(moveItem(['a', 'b', 'c', 'd'], 3, 0)).toEqual(['d', 'a', 'b', 'c']);
    expect(moveItem(['a', 'b', 'c', 'd'], 0, 3)).toEqual(['b', 'c', 'd', 'a']);
    expect(moveItem(['a', 'b', 'c'], 1, 1)).toEqual(['a', 'b', 'c']);
  });
  it('clamps a place beyond the ends', () => {
    expect(moveItem(['a', 'b', 'c'], 0, 99)).toEqual(['b', 'c', 'a']);
    expect(moveItem(['a', 'b', 'c'], 2, -5)).toEqual(['c', 'a', 'b']);
  });
});

describe('dropIndex', () => {
  const middles = [125, 175, 225, 275];
  it('counts the other rows above the finger', () => {
    expect(dropIndex(100, middles, 2)).toBe(0);
    expect(dropIndex(180, middles, 0)).toBe(1);
    expect(dropIndex(300, middles, 0)).toBe(3);
    expect(dropIndex(226, middles, 2)).toBe(2); // its own middle does not count
  });
});
