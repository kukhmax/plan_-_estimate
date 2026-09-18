import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiRequest } from './http';

describe('apiRequest error detail parsing', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('extracts a readable Pydantic array-detail 422 message', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 422,
      json: vi.fn().mockResolvedValue({
        detail: [
          {
            type: 'decimal_max_places',
            loc: ['body', 'height'],
            msg: 'Decimal input should have no more than 3 decimal places',
          },
        ],
      }),
    } as unknown as Response);

    const error = await apiRequest('/test').catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 422,
      message: 'body.height: Decimal input should have no more than 3 decimal places',
    });
  });

  it('assigns a stable code to the opening-deduction domain 422', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 422,
      json: vi.fn().mockResolvedValue({
        detail: 'Total opening deductions (20.513 m²) would exceed wall gross area (9.000 m²)',
      }),
    } as unknown as Response);

    const error = await apiRequest('/test').catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 422,
      code: 'openings_deductions_exceed_gross',
      message: 'Total opening deductions (20.513 m²) would exceed wall gross area (9.000 m²)',
    });
  });

  it('uses the generic fallback only when no structured detail is available', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 422,
      json: vi.fn().mockResolvedValue({ detail: [] }),
    } as unknown as Response);

    const error = await apiRequest('/test').catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 422, message: 'Request failed (422)' });
  });

  it('preserves an unknown structured validation message instead of replacing it', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 422,
      json: vi.fn().mockResolvedValue({
        detail: [{ loc: ['body', 'custom'], msg: 'Custom validator detail' }],
      }),
    } as unknown as Response);

    const error = await apiRequest('/test').catch((caught: unknown) => caught);

    expect(error).toMatchObject({
      status: 422,
      message: 'body.custom: Custom validator detail',
    });
  });

  it('resolves with undefined for a 204 No Content response (e.g. DELETE) without parsing a body', async () => {
    const json = vi.fn().mockRejectedValue(new Error('no body to parse'));
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      status: 204,
      json,
    } as unknown as Response);

    const result = await apiRequest('/test', { method: 'DELETE' });

    expect(result).toBeUndefined();
    expect(json).not.toHaveBeenCalled();
  });
});
