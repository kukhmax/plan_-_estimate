import { describe, expect, it } from 'vitest';
import { isCacheablePath } from './cacheRules';

const P = '11111111-1111-1111-1111-111111111111';
const R = '22222222-2222-2222-2222-222222222222';

describe('isCacheablePath (Stage 19B)', () => {
  it.each([
    '/api/projects',
    '/api/projects?include_archived=true',
    `/api/projects/${P}`,
    `/api/projects/${P}/summary`,
    `/api/projects/${P}/notes`,
    `/api/projects/${P}/payments`, // IA-4: the settlements of the object, with and without the archived ones
    `/api/projects/${P}/payments?include_archived=true`,
    `/api/projects/${P}/rooms`,
    `/api/projects/${P}/rooms?include_archived=true`,
    `/api/projects/${P}/rooms/${R}`,
    `/api/projects/${P}/rooms/${R}/surfaces`,
    `/api/projects/${P}/rooms/${R}/surfaces/${R}/openings`,
    `/api/projects/${P}/rooms/${R}/area-segments`,
    `/api/projects/${P}/rooms/${R}/inspections/${R}/answers`,
    `/api/projects/${P}/rooms/${R}/surfaces/${R}/work-plan`,
    '/api/clients',
    '/api/clients?search=kow',
    '/api/clients/33333333-3333-3333-3333-333333333333',
    '/api/checklist-templates',
    `/api/checklist-templates/${R}`,
  ])('keeps %s', (path) => expect(isCacheablePath(path)).toBe(true));

  it.each([
    `/api/projects/${P}/photos`,
    `/api/projects/${P}/photos/counts`,
    `/api/projects/${P}/finance`, // the agreed amount needs the server
    `/api/projects/${P}/payments/${R}`,
    `/api/projects/${P}/documents`,
    `/api/projects/${P}/estimates`,
    `/api/projects/${P}/contracts`,
    `/api/projects/${P}/handovers`,
    `/api/projects/${P}/representatives`,
    `/api/projects/${P}/schedule`,
    '/api/calendar',
    '/api/calendar/settings',
    '/api/documents',
    '/api/photo-storage',
    '/api/knowledge/entries',
    '/api/price-coefficient-groups',
    '/api/pricebook/items',
    '/api/auth/telegram',
    '/api/health',
    '/api/projects/not-a-uuid/rooms',
    `/api/projects/${P}/archive`,
    `/api/projectsX`,
  ])('does not keep %s', (path) => expect(isCacheablePath(path)).toBe(false));
});
