import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import {
  archiveRepresentative,
  createRepresentative,
  fetchRepresentatives,
  restoreRepresentative,
  updateRepresentative,
} from '../api/representatives';
import { useI18n } from '../hooks/useI18n';
import {
  ProjectRepresentative,
  REPRESENTATIVE_SIDES,
  RepresentativeSide,
} from '../types/representative';

interface ProjectRepresentativesProps {
  projectId: string;
}

interface FormState {
  side: RepresentativeSide;
  name: string;
  role_title: string;
  phone: string;
  email: string;
  may_accept_and_sign: boolean;
}

const EMPTY_FORM: FormState = { side: 'CUSTOMER_REPRESENTATIVE', name: '', role_title: '', phone: '', email: '', may_accept_and_sign: false };
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

function formFrom(person: ProjectRepresentative): FormState {
  return {
    side: person.side,
    name: person.name,
    role_title: person.role_title ?? '',
    phone: person.phone ?? '',
    email: person.email ?? '',
    may_accept_and_sign: person.may_accept_and_sign,
  };
}

function telHref(phone: string): string {
  return `tel:${phone.replace(/[^\d+]/g, '')}`;
}

const FIELD = 'w-full min-h-11 border border-slate-200 rounded-lg px-3 py-2 text-base bg-white text-slate-900';

/**
 * Stage 16B.2 — the persons of an object: who acts for each side and who may accept the work and sign the protocols. They are
 * named in the contract and the protocols (later sub-stages). A person is archived, never deleted.
 */
export function ProjectRepresentatives({ projectId }: ProjectRepresentativesProps) {
  const { t } = useI18n();
  const text = t.representatives;
  const [items, setItems] = useState<ProjectRepresentative[]>([]);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [editing, setEditing] = useState<ProjectRepresentative | 'new' | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadFailed(false);
    try {
      const response = await fetchRepresentatives(projectId, includeArchived);
      if (alive.current) setItems(response.items);
    } catch {
      if (alive.current) setLoadFailed(true);
    } finally {
      if (alive.current) setLoading(false);
    }
  }, [projectId, includeArchived]);

  useEffect(() => {
    void load();
  }, [load]);

  const openForm = (target: ProjectRepresentative | 'new') => {
    setEditing(target);
    setForm(target === 'new' ? EMPTY_FORM : formFrom(target));
    setFormError(null);
  };

  const closeForm = () => {
    setEditing(null);
    setFormError(null);
  };

  const change = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((current) => ({ ...current, [key]: value }));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (saving || editing === null) return;
    const name = form.name.trim();
    const phone = form.phone.trim();
    const email = form.email.trim();
    if (name === '') return setFormError(text.validation_name);
    if (phone !== '' && phone.replace(/\D/g, '').length < 7) return setFormError(text.validation_phone);
    if (email !== '' && !EMAIL.test(email)) return setFormError(text.validation_email);
    setSaving(true);
    setFormError(null);
    try {
      if (editing === 'new') {
        await createRepresentative(projectId, {
          side: form.side,
          name,
          role_title: form.role_title.trim() || undefined,
          phone: phone || undefined,
          email: email || undefined,
          may_accept_and_sign: form.may_accept_and_sign,
        });
      } else {
        // an emptied optional field is removed (null), like the address of a client
        await updateRepresentative(projectId, editing.id, {
          side: form.side,
          name,
          role_title: form.role_title.trim() || null,
          phone: phone || null,
          email: email || null,
          may_accept_and_sign: form.may_accept_and_sign,
        });
      }
      if (!alive.current) return;
      closeForm();
      await load();
    } catch (err) {
      if (alive.current) setFormError(err instanceof Error && err.message ? err.message : text.save_failed);
    } finally {
      if (alive.current) setSaving(false);
    }
  };

  const toggleArchive = async (person: ProjectRepresentative) => {
    if (busyId) return;
    setBusyId(person.id);
    try {
      if (person.is_archived) await restoreRepresentative(projectId, person.id);
      else await archiveRepresentative(projectId, person.id);
      if (alive.current) await load();
    } catch {
      if (alive.current) setLoadFailed(true);
    } finally {
      if (alive.current) setBusyId(null);
    }
  };

  return (
    <article aria-label="project-representatives" className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h3 className="min-w-0 break-words text-sm font-semibold text-slate-900">{text.title}</h3>
        {editing === null && (
          <button
            type="button"
            aria-label="add-representative"
            onClick={() => openForm('new')}
            className="min-h-11 px-4 shrink-0 text-sm font-semibold text-white bg-blue-600 rounded-xl hover:bg-blue-700 transition"
          >
            {text.add}
          </button>
        )}
      </div>
      <p className="text-xs text-slate-600 break-words">{text.intro}</p>

      {editing !== null && (
        <form aria-label="representative-form" onSubmit={submit} className="space-y-2 border border-slate-200 rounded-xl p-3 bg-slate-50">
          <h4 className="text-sm font-semibold text-slate-900 break-words">
            {editing === 'new' ? text.form_title_add : text.form_title_edit}
          </h4>
          <label className="block text-xs font-medium text-slate-600">
            {text.side}
            <select
              aria-label="representative-side"
              value={form.side}
              onChange={(e) => change('side', e.target.value as RepresentativeSide)}
              className={`${FIELD} mt-1`}
            >
              {REPRESENTATIVE_SIDES.map((side) => (
                <option key={side} value={side}>
                  {text[`side_${side}`]}
                </option>
              ))}
            </select>
          </label>
          <input aria-label="representative-name" placeholder={text.name} value={form.name} autoComplete="name" onChange={(e) => change('name', e.target.value)} className={FIELD} />
          <input aria-label="representative-role" placeholder={text.role_title} value={form.role_title} onChange={(e) => change('role_title', e.target.value)} className={FIELD} />
          <input aria-label="representative-phone" placeholder={text.phone} value={form.phone} type="tel" inputMode="tel" autoComplete="tel" onChange={(e) => change('phone', e.target.value)} className={FIELD} />
          <input aria-label="representative-email" placeholder={text.email} value={form.email} type="email" inputMode="email" autoComplete="email" onChange={(e) => change('email', e.target.value)} className={FIELD} />
          <label className="flex items-start gap-3 min-h-11 text-sm text-slate-900">
            <input
              type="checkbox"
              aria-label="representative-may-sign"
              className="mt-0.5 h-5 w-5 shrink-0"
              checked={form.may_accept_and_sign}
              onChange={(e) => change('may_accept_and_sign', e.target.checked)}
            />
            <span className="min-w-0 break-words">{text.may_accept_and_sign}</span>
          </label>
          {formError && (
            <p role="alert" aria-label="representative-error" className="text-sm text-red-700 break-words">
              {formError}
            </p>
          )}
          <button
            type="submit"
            disabled={saving}
            className="w-full min-h-11 px-3 text-sm font-semibold text-white bg-blue-600 rounded-xl hover:bg-blue-700 disabled:opacity-60 transition"
          >
            {text.save}
          </button>
          <button
            type="button"
            onClick={closeForm}
            disabled={saving}
            className="w-full min-h-11 px-3 text-sm font-semibold text-slate-800 bg-white border border-slate-300 rounded-xl hover:bg-slate-100 disabled:opacity-60 transition"
          >
            {text.cancel}
          </button>
        </form>
      )}

      {loading && items.length === 0 && <p role="status" className="text-sm text-slate-600">{text.loading}</p>}
      {loadFailed && (
        <div className="space-y-2">
          <p role="alert" className="text-sm text-red-700 break-words">{text.load_failed}</p>
          <button type="button" onClick={() => void load()} className="w-full min-h-11 text-sm font-semibold text-slate-800 bg-slate-100 border border-slate-200 rounded-xl">
            {text.retry}
          </button>
        </div>
      )}
      {!loading && !loadFailed && items.length === 0 && <p className="text-sm text-slate-600 break-words">{text.empty}</p>}

      {items.length > 0 && (
        <ul className="space-y-2">
          {items.map((person) => (
            <li key={person.id} aria-label={`representative-${person.id}`} className="border border-slate-200 rounded-xl p-3 space-y-1">
              <div className="flex items-start justify-between gap-2">
                <span className="min-w-0 break-words text-sm font-semibold text-slate-900">{person.name}</span>
                {person.is_archived && (
                  <span className="shrink-0 text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-800 font-medium">{text.archived_badge}</span>
                )}
              </div>
              <p className="text-xs text-slate-700 break-words">
                {text[`side_${person.side}`]}
                {person.role_title ? ` · ${person.role_title}` : ''}
              </p>
              {person.may_accept_and_sign && (
                <p className="inline-block text-xs px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 font-medium break-words">
                  {text.may_accept_and_sign_badge}
                </p>
              )}
              {person.phone && (
                <p className="text-xs text-slate-600 break-words">
                  <a href={telHref(person.phone)} aria-label={`call-${person.id}`} className="inline-block py-1.5 -my-1.5 text-blue-700 underline underline-offset-2">
                    {person.phone}
                  </a>
                </p>
              )}
              {person.email && <p className="text-xs text-slate-600 break-all">{person.email}</p>}
              <div className="flex flex-wrap gap-2 pt-1">
                {!person.is_archived && (
                  <button
                    type="button"
                    aria-label={`edit-representative-${person.id}`}
                    onClick={() => openForm(person)}
                    className="min-h-11 px-4 text-sm font-semibold text-slate-800 bg-slate-100 border border-slate-200 rounded-xl hover:bg-slate-200 transition"
                  >
                    {text.edit}
                  </button>
                )}
                <button
                  type="button"
                  aria-label={`${person.is_archived ? 'restore' : 'archive'}-representative-${person.id}`}
                  disabled={busyId === person.id}
                  onClick={() => void toggleArchive(person)}
                  className="min-h-11 px-4 text-sm font-semibold text-slate-800 bg-white border border-slate-300 rounded-xl hover:bg-slate-100 disabled:opacity-60 transition"
                >
                  {person.is_archived ? text.restore : text.archive}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <label className="flex items-center gap-3 min-h-11 text-sm text-slate-700">
        <input
          type="checkbox"
          aria-label="show-archived-representatives"
          className="h-5 w-5 shrink-0"
          checked={includeArchived}
          onChange={(e) => setIncludeArchived(e.target.checked)}
        />
        <span className="min-w-0 break-words">{text.show_archived}</span>
      </label>
    </article>
  );
}
