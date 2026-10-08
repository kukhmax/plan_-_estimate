import { FormEvent, useCallback, useEffect, useState } from 'react';
import { fetchExecutorProfile, profileFieldErrors, saveExecutorProfile } from '../api/executorProfile';
import { ApiError } from '../api/http';
import { useI18n } from '../hooks/useI18n';
import { ExecutorProfile, ExecutorProfileField, ExecutorProfilePayload } from '../types/executorProfile';

interface ExecutorProfileModalProps {
  onClose: () => void;
}

interface FieldSpec {
  name: ExecutorProfileField;
  type: 'text' | 'tel' | 'email';
  inputMode?: 'numeric' | 'tel' | 'email';
  autoComplete: string;
  placeholder?: boolean;
}

const FIELDS: FieldSpec[] = [
  { name: 'name', type: 'text', autoComplete: 'organization' },
  { name: 'nip', type: 'text', inputMode: 'numeric', autoComplete: 'off', placeholder: true },
  { name: 'street', type: 'text', autoComplete: 'street-address' },
  { name: 'postal_code', type: 'text', inputMode: 'numeric', autoComplete: 'postal-code', placeholder: true },
  { name: 'city', type: 'text', autoComplete: 'address-level2' },
  { name: 'phone', type: 'tel', inputMode: 'tel', autoComplete: 'tel' },
  { name: 'email', type: 'email', inputMode: 'email', autoComplete: 'email' },
  { name: 'bank_account', type: 'text', inputMode: 'numeric', autoComplete: 'off', placeholder: true },
];

const EMPTY: ExecutorProfilePayload = {
  name: '', nip: '', street: '', postal_code: '', city: '', phone: '', email: '', bank_account: '',
};

function toForm(profile: ExecutorProfile | null): ExecutorProfilePayload {
  if (!profile) return EMPTY;
  return {
    name: profile.name,
    nip: profile.nip ?? '',
    street: profile.street ?? '',
    postal_code: profile.postal_code ?? '',
    city: profile.city ?? '',
    phone: profile.phone ?? '',
    email: profile.email ?? '',
    bank_account: profile.bank_account ?? '',
  };
}

/**
 * Stage 15C — the executor profile (name, NIP, address, contacts, bank account) printed in the header of
 * every document. The backend owns validation and normalisation; this screen only shows what it returns.
 */
export function ExecutorProfileModal({ onClose }: ExecutorProfileModalProps) {
  const { t } = useI18n();
  const text = t.executor_profile;
  const [form, setForm] = useState<ExecutorProfilePayload>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadFailed(false);
    try {
      setForm(toForm(await fetchExecutorProfile()));
    } catch {
      setLoadFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const change = (field: ExecutorProfileField, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
    setSaved(false);
    setFieldErrors((current) => {
      if (!(field in current)) return current;
      const { [field]: _removed, ...rest } = current;
      return rest;
    });
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    setSaveError(null);
    setSaved(false);
    try {
      const profile = await saveExecutorProfile(form);
      setForm(toForm(profile));
      setFieldErrors({});
      setSaved(true);
    } catch (error) {
      const fields = error instanceof ApiError ? profileFieldErrors(error.detail) : {};
      if (Object.keys(fields).length > 0) {
        setFieldErrors(fields);
        setSaveError(text.invalid_summary);
      } else {
        setFieldErrors({});
        setSaveError(text.save_failed);
      }
    } finally {
      setSaving(false);
    }
  };

  const errorText = (field: string): string | null => {
    const code = fieldErrors[field];
    if (!code) return null;
    const known = text.errors as Record<string, string>;
    return known[code] ?? text.invalid_summary;
  };

  return (
    <div
      className="fixed inset-0 z-[60] overflow-y-auto"
      style={{ backgroundColor: 'var(--tg-theme-bg-color)', color: 'var(--tg-theme-text-color)' }}
      role="dialog"
      aria-modal="true"
      aria-label={text.title}
    >
      <div className="mx-auto w-full max-w-md px-4 py-4">
        <div className="flex items-start justify-between gap-3">
          <h2 className="min-w-0 text-lg font-bold break-words">{text.title}</h2>
          <button
            type="button"
            aria-label="close-executor-profile"
            onClick={onClose}
            className="min-h-11 min-w-11 shrink-0 flex items-center justify-center rounded-xl border text-xl font-semibold"
            style={{
              backgroundColor: 'var(--tg-theme-secondary-bg-color)',
              color: 'var(--tg-theme-hint-color)',
              borderColor: 'var(--tg-control-border-color, var(--tg-theme-hint-color))',
            }}
          >
            ×
          </button>
        </div>
        <p className="mt-1 text-sm break-words" style={{ color: 'var(--tg-theme-hint-color)' }}>{text.intro}</p>

        {loading && (
          <p role="status" className="mt-6 text-sm" style={{ color: 'var(--tg-theme-hint-color)' }}>
            {text.loading}
          </p>
        )}

        {!loading && loadFailed && (
          <div className="mt-6 space-y-3">
            <p role="alert" className="text-sm font-medium text-red-700 break-words">{text.load_failed}</p>
            <button
              type="button"
              onClick={() => void load()}
              className="min-h-11 w-full text-sm font-semibold rounded-xl"
              style={{
                backgroundColor: 'var(--tg-theme-button-color)',
                color: 'var(--tg-theme-button-text-color)',
              }}
            >
              {text.retry}
            </button>
          </div>
        )}

        {!loading && !loadFailed && (
          <form onSubmit={submit} noValidate className="mt-4 space-y-4">
            {FIELDS.map((spec) => {
              const id = `executor-profile-${spec.name}`;
              const error = errorText(spec.name);
              const placeholders = text.placeholders as Record<string, string>;
              return (
                <div key={spec.name} className="flex flex-col gap-1">
                  <label htmlFor={id} className="text-xs font-medium break-words" style={{ color: 'var(--tg-theme-hint-color)' }}>
                    {text.fields[spec.name]}
                  </label>
                  <input
                    id={id}
                    name={spec.name}
                    type={spec.type}
                    inputMode={spec.inputMode}
                    autoComplete={spec.autoComplete}
                    placeholder={spec.placeholder ? placeholders[spec.name] : undefined}
                    value={form[spec.name]}
                    onChange={(event) => change(spec.name, event.target.value)}
                    aria-invalid={error ? true : undefined}
                    aria-describedby={error ? `${id}-error` : undefined}
                    className={`min-h-11 w-full rounded-lg border px-3 text-base ${error ? 'border-red-500' : 'border-slate-200'}`}
                    style={{
                      backgroundColor: 'var(--tg-theme-secondary-bg-color)',
                      color: 'var(--tg-theme-text-color)',
                    }}
                  />
                  {error && (
                    <p id={`${id}-error`} className="text-xs font-medium text-red-700 break-words">{error}</p>
                  )}
                </div>
              );
            })}

            {saveError && <p role="alert" className="text-sm font-medium text-red-700 break-words">{saveError}</p>}
            {saved && <p role="status" className="text-sm font-medium text-emerald-700 break-words">{text.saved}</p>}

            <div className="flex flex-col gap-2 pb-4">
              <button
                type="submit"
                disabled={saving}
                className="min-h-11 w-full text-sm font-semibold rounded-xl disabled:opacity-60"
                style={{
                  backgroundColor: 'var(--tg-theme-button-color)',
                  color: 'var(--tg-theme-button-text-color)',
                }}
              >
                {saving ? t.common.saving : t.common.save}
              </button>
              <button
                type="button"
                onClick={onClose}
                className="min-h-11 w-full text-sm font-semibold rounded-xl border"
                style={{
                  backgroundColor: 'var(--tg-theme-secondary-bg-color)',
                  color: 'var(--tg-theme-text-color)',
                  borderColor: 'var(--tg-control-border-color, var(--tg-theme-hint-color))',
                }}
              >
                {t.common.close}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
