import { describe, expect, it } from 'vitest';
import { ApiError } from '../api/http';
import pl from '../locales/pl.json';
import ru from '../locales/ru.json';
import { documentErrorText } from './documentErrors';

const errors = pl.documents.errors as Record<string, string>;

describe('documentErrorText', () => {
  it('uses the text of the stable code, never the English message', () => {
    const error = new ApiError('The estimate is not final', 422, 'ESTIMATE_NOT_FINAL', {});
    expect(documentErrorText(errors, error)).toBe(errors.ESTIMATE_NOT_FINAL);
    expect(documentErrorText(errors, error)).not.toContain('estimate is not');
  });

  it('puts the counts of the backend details into the text', () => {
    const error = new ApiError('x', 422, 'PHOTO_LIMIT_EXCEEDED', { code: 'PHOTO_LIMIT_EXCEEDED', details: { count: 72, limit: 60 } });
    expect(documentErrorText(errors, error)).toBe('Zdjęć jest za dużo na jeden dokument (72 > 60). Wyślij raport w częściach.');
  });

  it('puts the list of works without a price into the refusal', () => {
    const error = new ApiError('x', 422, 'RECOMMENDED_WORK_UNPRICED', {
      code: 'RECOMMENDED_WORK_UNPRICED', details: { count: 1, works: 'Salon › Ściana A: Gruntowanie' } });
    const text = documentErrorText(errors, error);
    expect(text).toContain('Salon › Ściana A: Gruntowanie');
    expect(text).toContain('nie mają ceny w kosztorysie');
  });

  it('knows a bare code from the journal (a failed row) and falls back for anything else', () => {
    expect(documentErrorText(errors, 'TELEGRAM_CHAT_UNAVAILABLE')).toBe(errors.TELEGRAM_CHAT_UNAVAILABLE);
    expect(documentErrorText(errors, undefined)).toBe(errors.UNKNOWN);
    expect(documentErrorText(errors, 'SOMETHING_NEW')).toBe(errors.UNKNOWN);
    expect(documentErrorText(errors, new Error('network'))).toBe(errors.UNKNOWN);
    expect(documentErrorText(errors, new ApiError('x', 500, undefined))).toBe(errors.UNKNOWN);
  });

  it('leaves an unknown placeholder visible rather than printing "undefined"', () => {
    expect(documentErrorText({ UNKNOWN: 'a', X: 'b {nope}' }, 'X')).toBe('b {nope}');
  });

  it('speaks Russian when given the Russian dictionary', () => {
    expect(documentErrorText(ru.documents.errors as Record<string, string>, 'EXECUTOR_PROFILE_REQUIRED')).toContain('профиль исполнителя');
  });
});
