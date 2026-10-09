import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  fetchPhotoReportSummary,
  getDocument,
  issueEstimateDocument,
  issuePhotoReport,
  issueProductionPlan,
  issueTechCard,
  listDocuments,
  previewEstimatePdf,
  previewProductionPlanPdf,
  previewTechCardPdf,
} from './documents';

function respond(status: number, body: unknown) {
  vi.mocked(fetch).mockResolvedValueOnce({ ok: status < 400, status, json: vi.fn().mockResolvedValue(body) } as unknown as Response);
}

describe('documents API', () => {
  beforeEach(() => {
    localStorage.setItem('access_token', 'tok');
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  function lastCall() {
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    return { url: String(url), init: init as RequestInit };
  }

  it('issues an estimate by its id', async () => {
    respond(202, { id: 'd1' });
    await issueEstimateDocument('p1', 'e1');
    const { url, init } = lastCall();
    expect(url).toBe('/api/projects/p1/documents');
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({ kind: 'ESTIMATE', estimate_id: 'e1' });
  });

  it('issues the whole photo report with no rooms, or a part with its rooms', async () => {
    respond(202, {});
    await issuePhotoReport('p1');
    expect(JSON.parse(String(lastCall().init.body))).toEqual({ kind: 'PHOTO_REPORT' });
    vi.mocked(fetch).mockClear();
    respond(202, {});
    await issuePhotoReport('p1', { room_ids: ['r1', 'r2'], include_project_photos: true });
    expect(JSON.parse(String(lastCall().init.body))).toEqual({ kind: 'PHOTO_REPORT', room_ids: ['r1', 'r2'], include_project_photos: true });
  });

  it('reads the journal, one document, the summary and sends a preview', async () => {
    respond(200, { items: [], total: 0 });
    await listDocuments('p1');
    expect(lastCall().url).toBe('/api/projects/p1/documents');
    vi.mocked(fetch).mockClear();
    respond(200, {});
    await getDocument('p1', 'd9');
    expect(lastCall().url).toBe('/api/projects/p1/documents/d9');
    vi.mocked(fetch).mockClear();
    respond(200, {});
    await fetchPhotoReportSummary('p1');
    expect(lastCall().url).toBe('/api/projects/p1/photo-report/summary');
    vi.mocked(fetch).mockClear();
    respond(200, { sent: true, pages: 1, byte_size: 10 });
    await previewEstimatePdf('p1', 'e1');
    expect(lastCall().url).toBe('/api/projects/p1/estimates/e1/preview-pdf');
    expect(lastCall().init.method).toBe('POST');
  });

  it('issues the technological card of the whole object and previews its working version', async () => {
    respond(202, {});
    await issueTechCard('p1');
    let call = lastCall();
    expect(call.url).toBe('/api/projects/p1/documents');
    expect(JSON.parse(String(call.init.body))).toEqual({ kind: 'TECH_CARD' });
    vi.mocked(fetch).mockClear();
    respond(200, { sent: true, pages: 1, byte_size: 10 });
    await previewTechCardPdf('p1');
    call = lastCall();
    expect(call.url).toBe('/api/projects/p1/documents/tech-card/preview');
    expect(call.init.method).toBe('POST');
  });

  it('issues the production plan of the whole object and previews its working version', async () => {
    respond(202, {});
    await issueProductionPlan('p1');
    let call = lastCall();
    expect(call.url).toBe('/api/projects/p1/documents');
    expect(JSON.parse(String(call.init.body))).toEqual({ kind: 'PRODUCTION_PLAN' });
    vi.mocked(fetch).mockClear();
    respond(200, { sent: true, pages: 1, byte_size: 10 });
    await previewProductionPlanPdf('p1');
    call = lastCall();
    expect(call.url).toBe('/api/projects/p1/documents/production-plan/preview');
    expect(call.init.method).toBe('POST');
  });
});
