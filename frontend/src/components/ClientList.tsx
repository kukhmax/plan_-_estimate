import React, { useEffect, useState, useCallback, useRef } from 'react';
import { ClientType, ClientCreatePayload, ClientUpdatePayload } from '../types/client';
import {
  fetchClients,
  createClient,
  updateClient,
  archiveClient,
  restoreClient,
} from '../api/clients';
import { fetchProjects } from '../api/projects';
import { ProjectType } from '../types/project';
import { useI18n } from '../hooks/useI18n';
import { useTelegramBackButton } from '../hooks/useTelegramWebApp';
import { copyTextToClipboard } from '../utils/clipboard';
import { Ico } from './Ico';
import { GettingStarted, useStartProgress } from './GettingStarted';

/** Digits and a single leading '+' only — a safe `tel:` href from a
 * human-readable stored phone value (spaces/dashes/parens stripped). */
function toTelHref(phone: string): string {
  const trimmed = phone.trim();
  const leadingPlus = trimmed.startsWith('+') ? '+' : '';
  return `tel:${leadingPlus}${trimmed.replace(/[^\d]/g, '')}`;
}

/** Stored value is canonicalized with exactly one leading '@' — the t.me
 * path must never include it. */
function toTelegramHref(username: string): string {
  return `https://t.me/${username.replace(/^@+/, '')}`;
}

interface ClientFormState {
  client_type: 'PRIVATE_PERSON' | 'COMPANY';
  first_name: string;
  last_name: string;
  company_name: string;
  phone: string;
  email: string;
  nip: string;
  street: string;
  postal_code: string;
  city: string;
  telegram_username: string;
  notes: string;
}

const DEFAULT_FORM: ClientFormState = {
  client_type: 'PRIVATE_PERSON',
  first_name: '',
  last_name: '',
  company_name: '',
  phone: '',
  email: '',
  nip: '',
  street: '',
  postal_code: '',
  city: '',
  telegram_username: '',
  notes: '',
};

function formFromClient(c: ClientType): ClientFormState {
  return {
    client_type: c.client_type,
    first_name: c.first_name ?? '',
    last_name: c.last_name ?? '',
    company_name: c.company_name ?? '',
    phone: c.phone ?? '',
    email: c.email ?? '',
    nip: c.nip ?? '',
    street: c.street ?? '',
    postal_code: c.postal_code ?? '',
    city: c.city ?? '',
    telegram_username: c.telegram_username ?? '',
    notes: c.notes ?? '',
  };
}

interface ClientListProps {
  /** "Смета" on the card of a client opens the estimate of that object. */
  onOpenEstimate?: (projectId: string) => void;
  /** Usability U-3: after a client was added through "Od czego zacząć", the form of his object opens at once. */
  onStartObject?: (clientId: string) => void;
  onOpenPricebook?: () => void;
  onOpenProjects?: () => void;
  /** The example object of the account was made on the empty list: open it (V2-3). */
  onOpenProject?: (projectId: string) => void;
  /** A new value opens the form of a client that leads on to the form of his object (the first step of "Od czego zacząć" from another screen). */
  autoCreateToken?: number;
  /** An overlay above the screen (the main menu, the account dialog) owns the Telegram BackButton while it is open. */
  backSuspended?: boolean;
}

export const ClientList: React.FC<ClientListProps> = ({ onOpenEstimate, onStartObject, onOpenPricebook, onOpenProjects, onOpenProject, autoCreateToken = 0, backSuspended = false }) => {
  const { t } = useI18n();
  const [clients, setClients] = useState<ClientType[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editingClient, setEditingClient] = useState<ClientType | null>(null);
  const [form, setForm] = useState<ClientFormState>(DEFAULT_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // The card of one client (name, details, his objects); the list shows only names.
  const [selected, setSelected] = useState<ClientType | null>(null);
  const [objects, setObjects] = useState<ProjectType[] | null>(null);
  const [objectsError, setObjectsError] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  // Tapping a client's e-mail copies it (never opens a mail composer as the
  // primary action) — small self-clearing inline confirmation, same pattern
  // as the existing Stage 8C CommunicationPanel copy-to-clipboard action.
  const [copiedEmail, setCopiedEmail] = useState<{ id: string; ok: boolean } | null>(null);
  // The client being added leads on to the form of his object (the first step of "Od czego zacząć").
  const [leadsToObject, setLeadsToObject] = useState(false);
  const copyEmailTimerRef = useRef<number | null>(null);

  const startProgress = useStartProgress(total > 0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchClients({ search: search || undefined });
      setClients(data.items);
      setTotal(data.total);
      setSelected((current) => (current ? data.items.find((c) => c.id === current.id) ?? current : current));
    } catch (err) {
      setError(err instanceof Error ? err.message : t.clients.error);
    } finally {
      setLoading(false);
    }
  }, [search, t.clients.error]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    setObjects(null);
    setObjectsError(false);
    fetchProjects(false)
      .then((data) => {
        if (!cancelled) setObjects(data.items.filter((project) => project.client_id === selected.id));
      })
      .catch(() => {
        if (!cancelled) setObjectsError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [selected?.id]);

  const closeCard = () => {
    setSelected(null);
    setShowForm(false);
    setEditingClient(null);
    setFormError(null);
  };

  useTelegramBackButton(selected !== null && !backSuspended, () => {
    if (showForm) closeForm();
    else closeCard();
  });

  // An archived client leaves the list (the archive restores him), so the card must not stay open on stale data: after
  // archiving the owner is taken back to the list and told where the client went.
  const handleArchive = async (id: string) => {
    setActionError(null);
    try {
      await archiveClient(id);
    } catch {
      setActionError(t.clients.error_archive);
      return;
    }
    closeCard();
    setNotice(t.clients.archived_notice);
    void load();
  };

  const handleRestore = async (id: string) => {
    setActionError(null);
    try {
      setSelected(await restoreClient(id));
    } catch {
      setActionError(t.clients.error_restore);
      return;
    }
    void load();
  };

  const handleCopyEmail = (client: ClientType) => {
    if (!client.email) return;
    if (copyEmailTimerRef.current !== null) window.clearTimeout(copyEmailTimerRef.current);
    void copyTextToClipboard(client.email).then((ok) => {
      setCopiedEmail({ id: client.id, ok });
      copyEmailTimerRef.current = window.setTimeout(() => setCopiedEmail(null), 2500);
    });
  };

  const handleFormChange = (field: keyof ClientFormState, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const openCreate = () => {
    if (showForm && editingClient === null) {
      setShowForm(false);
      setFormError(null);
      return;
    }
    setEditingClient(null);
    setForm(DEFAULT_FORM);
    setFormError(null);
    setShowForm(true);
  };

  const openEdit = (client: ClientType) => {
    setEditingClient(client);
    setForm(formFromClient(client));
    setFormError(null);
    setShowForm(true);
  };

  const startFirstClient = () => {
    setLeadsToObject(true);
    setEditingClient(null);
    setForm(DEFAULT_FORM);
    setFormError(null);
    setShowForm(true);
  };

  useEffect(() => {
    if (autoCreateToken > 0) startFirstClient();
  }, [autoCreateToken]);

  const closeForm = () => {
    setLeadsToObject(false);
    setShowForm(false);
    setEditingClient(null);
    setForm(DEFAULT_FORM);
    setFormError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    // Client-side validation mirrors backend rules
    if (form.client_type === 'PRIVATE_PERSON' && !form.first_name && !form.last_name) {
      setFormError(t.clients.validation_private_name);
      return;
    }
    if (form.client_type === 'COMPANY' && !form.company_name) {
      setFormError(t.clients.validation_company_name);
      return;
    }

    if (form.postal_code.trim() !== '' && !/^\d{2}[\s-]?\d{3}$/.test(form.postal_code.trim())) {
      setFormError(t.clients.validation_postal_code);
      return;
    }

    setSaving(true);
    try {
      if (editingClient) {
        const payload: ClientUpdatePayload = {
          client_type: form.client_type,
          first_name: form.first_name || undefined,
          last_name: form.last_name || undefined,
          company_name: form.company_name || undefined,
          phone: form.phone || undefined,
          email: form.email || undefined,
          nip: form.nip || undefined,
          // The address is cleared the same way (Stage 16B.1): an empty field means "remove it".
          street: form.street.trim() === '' ? null : form.street,
          postal_code: form.postal_code.trim() === '' ? null : form.postal_code,
          city: form.city.trim() === '' ? null : form.city,
          // Explicit clear-to-null: an empty field here means the owner
          // deliberately removed it, unlike the other fields above where
          // empty simply means "leave unchanged" (existing convention).
          telegram_username: form.telegram_username.trim() === '' ? null : form.telegram_username,
          notes: form.notes || undefined,
        };
        await updateClient(editingClient.id, payload);
      } else {
        const payload: ClientCreatePayload = {
          client_type: form.client_type,
          first_name: form.first_name || undefined,
          last_name: form.last_name || undefined,
          company_name: form.company_name || undefined,
          phone: form.phone || undefined,
          email: form.email || undefined,
          nip: form.nip || undefined,
          street: form.street || undefined,
          postal_code: form.postal_code || undefined,
          city: form.city || undefined,
          telegram_username: form.telegram_username || undefined,
          notes: form.notes || undefined,
        };
        const created = await createClient(payload);
        if (leadsToObject && onStartObject) {
          closeForm();
          onStartObject(created.id);
          return;
        }
      }
      closeForm();
      load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Error');
    } finally {
      setSaving(false);
    }
  };

  const displayName = (c: ClientType) => {
    if (c.client_type === 'COMPANY') return c.company_name ?? '—';
    return [c.first_name, c.last_name].filter(Boolean).join(' ') || '—';
  };

  const formBlock = showForm && (
        <form
          aria-label="client-form"
          onSubmit={handleSubmit}
          className="pe-card rounded-2xl p-4 mb-4 shadow-sm space-y-3"
        >
          <h3 className="font-semibold text-slate-900 text-sm">
            {editingClient ? t.clients.edit : t.clients.add_client}
          </h3>

          {/* Client type */}
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1">{t.clients.client_type}</label>
            <select
              aria-label="client-type-select"
              value={form.client_type}
              onChange={(e) => handleFormChange('client_type', e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 min-h-11 text-sm"
            >
              <option value="PRIVATE_PERSON">{t.clients.private_person}</option>
              <option value="COMPANY">{t.clients.company}</option>
            </select>
          </div>

          {form.client_type === 'PRIVATE_PERSON' && (
            <>
              <input
                aria-label="first-name"
                placeholder={t.clients.first_name}
                value={form.first_name}
                onChange={(e) => handleFormChange('first_name', e.target.value)}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 min-h-11 text-sm"
              />
              <input
                aria-label="last-name"
                placeholder={t.clients.last_name}
                value={form.last_name}
                onChange={(e) => handleFormChange('last_name', e.target.value)}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 min-h-11 text-sm"
              />
            </>
          )}

          {form.client_type === 'COMPANY' && (
            <>
              <input
                aria-label="company-name"
                placeholder={t.clients.company_name}
                value={form.company_name}
                onChange={(e) => handleFormChange('company_name', e.target.value)}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 min-h-11 text-sm"
              />
              <input
                aria-label="nip"
                placeholder={t.clients.nip}
                value={form.nip}
                onChange={(e) => handleFormChange('nip', e.target.value)}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 min-h-11 text-sm"
              />
            </>
          )}

          <input
            aria-label="phone"
            placeholder={t.clients.phone}
            value={form.phone}
            onChange={(e) => handleFormChange('phone', e.target.value)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 min-h-11 text-sm"
          />
          <input
            aria-label="email"
            placeholder={t.clients.email}
            value={form.email}
            onChange={(e) => handleFormChange('email', e.target.value)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 min-h-11 text-sm"
          />
          <input
            aria-label="street"
            placeholder={t.clients.street}
            autoComplete="street-address"
            value={form.street}
            onChange={(e) => handleFormChange('street', e.target.value)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 min-h-11 text-sm"
          />
          <div className="grid grid-cols-1 min-[400px]:grid-cols-[8rem_1fr] gap-2">
            <input
              aria-label="postal-code"
              placeholder={t.clients.postal_code}
              inputMode="numeric"
              autoComplete="postal-code"
              value={form.postal_code}
              onChange={(e) => handleFormChange('postal_code', e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 min-h-11 text-sm"
            />
            <input
              aria-label="city"
              placeholder={t.clients.city}
              autoComplete="address-level2"
              value={form.city}
              onChange={(e) => handleFormChange('city', e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 min-h-11 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1">{t.clients.telegram}</label>
            <input
              aria-label="telegram-username"
              placeholder={t.clients.telegram_placeholder}
              value={form.telegram_username}
              onChange={(e) => handleFormChange('telegram_username', e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 min-h-11 text-sm"
            />
          </div>

          {formError && (
            <p className="text-sm text-red-600 font-medium">{formError}</p>
          )}

          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={closeForm}
              className="px-4 min-h-11 text-sm rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50"
            >
              <Ico>✖️</Ico>{t.clients.cancel}
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-4 min-h-11 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition disabled:opacity-50"
            >
              <Ico>💾</Ico>{t.clients.save}
            </button>
          </div>
        </form>
      );

  const hasContact = (c: ClientType) =>
    Boolean(c.nip || c.phone || c.email || c.telegram_username || c.street || c.postal_code || c.city);

  const renderContact = (c: ClientType) => (
    <>
        {(c.nip || c.phone || c.email || c.telegram_username || c.street || c.postal_code || c.city) && (
          <div aria-label={`client-contact-${c.id}`} className="space-y-1 min-w-0">
            {c.nip && (
              <p className="text-sm text-slate-600 break-words min-w-0">
                <span className="text-slate-400">{t.clients.card_nip_label}</span> {c.nip}
              </p>
            )}
            {(c.street || c.postal_code || c.city) && (
              <p aria-label={`client-address-${c.id}`} className="text-sm text-slate-600 break-words min-w-0">
                <span className="text-slate-400">{t.clients.card_address_label}</span>{' '}
                {[c.street, [c.postal_code, c.city].filter(Boolean).join(' ')].filter(Boolean).join(', ')}
              </p>
            )}
            {c.phone && (
              <p className="text-sm text-slate-600 break-words min-w-0">
                <span className="text-slate-400">{t.clients.card_phone_label}</span>{' '}
                <a
                  href={toTelHref(c.phone)}
                  aria-label={`call-${c.id}`}
                  className="inline-block max-w-full py-3 -my-3 text-blue-700 underline underline-offset-2 [overflow-wrap:anywhere]"
                >
                  {c.phone}
                </a>
              </p>
            )}
            {c.email && (
              <p className="text-sm text-slate-600 break-words min-w-0">
                <span className="text-slate-400">{t.clients.card_email_label}</span>{' '}
                <button
                  type="button"
                  aria-label={`copy-email-${c.id}`}
                  onClick={() => handleCopyEmail(c)}
                  className="inline-block max-w-full py-3 -my-3 text-blue-700 underline underline-offset-2 [overflow-wrap:anywhere] text-left"
                >
                  {c.email}
                </button>
                {copiedEmail && copiedEmail.id === c.id && (
                  <span
                    role="status"
                    className={`ml-1.5 ${copiedEmail.ok ? 'text-emerald-700' : 'text-red-600'}`}
                  >
                    {copiedEmail.ok ? t.clients.email_copied : t.clients.email_copy_failed}
                  </span>
                )}
              </p>
            )}
            {c.telegram_username && (
              <p className="text-sm text-slate-600 break-words min-w-0">
                <span className="text-slate-400">{t.clients.card_telegram_label}</span>{' '}
                <a
                  href={toTelegramHref(c.telegram_username)}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={`open-telegram-${c.id}`}
                  className="inline-block max-w-full py-3 -my-3 text-blue-700 underline underline-offset-2 [overflow-wrap:anywhere]"
                >
                  {c.telegram_username}
                </a>
              </p>
            )}
          </div>
        )}
    </>
  );

  const statusLabel = (status: ProjectType['status']) =>
    ({ PLANNING: t.projects.planning, IN_PROGRESS: t.projects.in_progress, COMPLETED: t.projects.completed })[status];

  const cardView = selected && (
    <div aria-label="client-card" className="space-y-3">
      <button
        type="button"
        aria-label="back-to-clients"
        onClick={closeCard}
        className="min-h-11 px-1 -ml-1 text-sm font-semibold text-blue-700 hover:underline"
      >
        ‹ {t.clients.title}
      </button>

      <div className="flex items-start justify-between gap-3">
        <h2 aria-label="client-card-name" className="text-lg font-bold text-[var(--tg-theme-text-color)] break-words min-w-0">
          {displayName(selected)}
        </h2>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-500 font-medium">
            {selected.client_type === 'COMPANY' ? t.clients.company : t.clients.private_person}
          </span>
          {selected.is_archived && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-700 font-medium">
              {t.clients.archived_badge}
            </span>
          )}
        </div>
      </div>

      {formBlock}

      {actionError && <p role="alert" className="text-sm text-red-600 break-words">{actionError}</p>}

      {!showForm && (
        <>
          <div className="pe-card rounded-2xl p-4 shadow-sm space-y-2">
            {renderContact(selected)}
            {selected.notes && (
              <p aria-label={`client-notes-${selected.id}`} className="text-sm text-slate-600 whitespace-pre-wrap break-words">
                {selected.notes}
              </p>
            )}
            {!hasContact(selected) && !selected.notes && (
              <p className="text-sm text-slate-400">{t.clients.card_no_details}</p>
            )}
          </div>

          <div className="grid grid-cols-1 gap-2">
            <button
              type="button"
              aria-label={`edit-${selected.id}`}
              onClick={() => openEdit(selected)}
              className="min-h-11 px-3 text-sm rounded-xl bg-blue-50 text-blue-700 font-semibold hover:bg-blue-100 transition"
            >
              <Ico>✏️</Ico>{t.clients.edit}
            </button>
            {selected.is_archived ? (
              <button
                type="button"
                aria-label={`restore-${selected.id}`}
                onClick={() => handleRestore(selected.id)}
                className="min-h-11 px-3 text-sm rounded-xl bg-emerald-50 text-emerald-700 font-semibold hover:bg-emerald-100 transition"
              >
                <Ico>♻️</Ico>{t.clients.restore}
              </button>
            ) : (
              <button
                type="button"
                aria-label={`archive-${selected.id}`}
                onClick={() => handleArchive(selected.id)}
                className="min-h-11 px-3 text-sm rounded-xl bg-slate-50 border border-slate-200 text-slate-600 font-semibold hover:bg-slate-100 transition"
              >
                <Ico>🗃️</Ico>{t.clients.archive}
              </button>
            )}
          </div>
        </>
      )}

      <section aria-label="client-objects" className="pt-1">
        <h3 className="text-base font-bold text-[var(--tg-theme-text-color)] mb-2">{t.clients.objects_title}</h3>
        {objectsError && <p role="alert" className="text-sm text-red-600">{t.clients.objects_error}</p>}
        {!objectsError && objects === null && <p className="text-sm text-slate-500">{t.clients.loading}</p>}
        {!objectsError && objects !== null && objects.length === 0 && (
          <p aria-label="no-client-objects" className="text-sm text-slate-400">{t.clients.no_objects}</p>
        )}
        {objects !== null && objects.length > 0 && (
          <ul className="space-y-2" aria-label="client-objects-list">
            {objects.map((project) => (
              <li
                key={project.id}
                aria-label={`client-object-${project.id}`}
                className="pe-card rounded-2xl p-3 shadow-sm"
              >
                <p className="font-semibold text-slate-900 text-sm break-words">{project.name}</p>
                <p className="text-xs text-slate-500 break-words">{statusLabel(project.status)}</p>
                <button
                  type="button"
                  aria-label={`open-estimate-${project.id}`}
                  onClick={() => onOpenEstimate?.(project.id)}
                  className="mt-2 w-full min-h-11 px-3 text-sm font-semibold rounded-xl bg-amber-500 text-slate-950 hover:bg-amber-400 transition"
                >
                  {t.estimates.title}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );

  if (selected) {
    return (
      <section aria-label="clients-section" className="w-full mt-4">
        {cardView}
      </section>
    );
  }

  return (
    <section aria-label="clients-section" className="w-full mt-4">
      <div className="mb-3">
        <button
          aria-label="add-client"
          onClick={openCreate}
          className="w-full min-h-11 px-4 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition"
        >
          <Ico>➕</Ico>{t.clients.add_client}
        </button>
      </div>

      {/* Search + filters */}
      <div className="flex gap-2 mb-3">
        <input
          aria-label="search-clients"
          type="text"
          placeholder={t.clients.search_placeholder}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 min-w-0 min-h-11 border border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {notice && <p role="status" aria-label="client-notice" className="text-sm text-emerald-700 break-words mb-3">{notice}</p>}
      {actionError && <p role="alert" className="text-sm text-red-600 break-words mb-3">{actionError}</p>}

      {formBlock}

      {/* List: only the name; the details are on the card */}
      {loading && (
        <p className="text-sm text-slate-500 text-center py-4">{t.clients.loading}</p>
      )}
      {!loading && error && (
        <p className="text-sm text-red-600 text-center py-4">{error}</p>
      )}
      {!loading && !error && clients.length === 0 && (
        <div aria-label="no-clients">
          {search.trim() === '' ? (
            !showForm && (
              <GettingStarted
                progress={startProgress}
                onAddClient={startFirstClient}
                onOpenPricebook={() => onOpenPricebook?.()}
                onOpenProjects={() => onOpenProjects?.()}
                onOpenProject={onOpenProject}
              />
            )
          ) : (
            <p className="text-sm text-slate-400 text-center py-6">{t.clients.no_clients}</p>
          )}
        </div>
      )}
      {!loading && clients.length > 0 && (
        <ul className="space-y-2" aria-label="clients-list">
          {clients.map((c) => (
            <li key={c.id} aria-label={`client-item-${c.id}`}>
              <button
                type="button"
                aria-label={`client-open-${c.id}`}
                onClick={() => {
                  closeForm();
                  setNotice(null);
                  setActionError(null);
                  setSelected(c);
                }}
                className="w-full min-h-12 pe-card rounded-2xl px-4 py-2 shadow-sm flex items-center justify-between gap-3 text-left"
              >
                <span className="font-semibold text-slate-900 text-sm break-words min-w-0">{displayName(c)}</span>
                <span className="flex items-center gap-2 shrink-0">
                  {c.is_archived && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-700 font-medium">
                      {t.clients.archived_badge}
                    </span>
                  )}
                  <span aria-hidden="true" className="text-slate-400 text-lg leading-none">›</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <p aria-label="clients-count" className="text-xs text-slate-400 text-right mt-2">
        {total > 0 ? t.clients.count_label.replace('{count}', String(total)) : ''}
      </p>
    </section>
  );
};
