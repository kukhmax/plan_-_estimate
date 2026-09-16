import { describe, expect, it } from 'vitest';
import pl from '../locales/pl.json';
import ru from '../locales/ru.json';
import { getSurfaceDisplayName } from './surfaceDisplayName';

describe('getSurfaceDisplayName', () => {
  it('localizes generated WALL numbering in Polish and Russian', () => {
    expect(getSurfaceDisplayName({ name: 'Wall 1', surface_type: 'WALL' }, pl.surfaces)).toBe('Ściana 1');
    expect(getSurfaceDisplayName({ name: 'Wall 1', surface_type: 'WALL' }, ru.surfaces)).toBe('Стена 1');
    expect(getSurfaceDisplayName({ name: 'Wall 2', surface_type: 'WALL' }, pl.surfaces)).toBe('Ściana 2');
    expect(getSurfaceDisplayName({ name: 'Wall 2', surface_type: 'WALL' }, ru.surfaces)).toBe('Стена 2');
  });

  it('re-localizes previously persisted generated WALL names', () => {
    expect(getSurfaceDisplayName({ name: 'Ściana 3', surface_type: 'WALL' }, ru.surfaces)).toBe('Стена 3');
    expect(getSurfaceDisplayName({ name: 'Стена 4', surface_type: 'WALL' }, pl.surfaces)).toBe('Ściana 4');
  });

  it('localizes canonical FLOOR and CEILING names in Polish and Russian', () => {
    expect(getSurfaceDisplayName({ name: 'Floor', surface_type: 'FLOOR' }, pl.surfaces)).toBe('Podłoga');
    expect(getSurfaceDisplayName({ name: 'Floor', surface_type: 'FLOOR' }, ru.surfaces)).toBe('Пол');
    expect(getSurfaceDisplayName({ name: 'Ceiling', surface_type: 'CEILING' }, pl.surfaces)).toBe('Sufit');
    expect(getSurfaceDisplayName({ name: 'Ceiling', surface_type: 'CEILING' }, ru.surfaces)).toBe('Потолок');
  });

  it('preserves arbitrary custom surface names', () => {
    expect(getSurfaceDisplayName({ name: 'Ściana północna', surface_type: 'WALL' }, ru.surfaces)).toBe('Ściana północna');
    expect(getSurfaceDisplayName({ name: 'Wall art feature', surface_type: 'WALL' }, pl.surfaces)).toBe('Wall art feature');
    expect(getSurfaceDisplayName({ name: 'Podłoga w salonie', surface_type: 'FLOOR' }, ru.surfaces)).toBe('Podłoga w salonie');
  });

  it('does not mutate Surface.id', () => {
    const surface = { id: 'surface-1', name: 'Wall 1', surface_type: 'WALL' as const };

    getSurfaceDisplayName(surface, ru.surfaces);

    expect(surface.id).toBe('surface-1');
  });
});
