import React, { useEffect, useState, useCallback, useRef } from 'react';
import { ClientType, ClientCreatePayload, ClientUpdatePayload } from '../types/client';
import {
  fetchClients,
  createClient,
  updateClient,
  archiveClient,
  restoreClient,
} from '../api/clients';
import { useI18n } from '../hooks/useI18n';
import { copyTextToClipboard } from '../utils/clipboard';

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
    telegram_username: c.telegram_username ?? '',
    notes: c.notes ?? '',
  };
}

export const ClientList: React.FC = () => {
  const { t } = useI18n();
  const [clients, setClients] = useState<ClientType[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [includeArchived, setIncludeArchived] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editingClient, setEditingClient] = useState<ClientType | null>(null);
  const [form, setForm] = useState<ClientFormState>(DEFAULT_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // Tapping a client's e-mail copies it (never opens a mail composer as the
  // primary action) — small self-clearing inline confirmation, same pattern
  // as the existing Stage 8C CommunicationPanel copy-to-clipboard action.
  const [copiedEmail, setCopiedEmail] = useState<{ id: string; ok: boolean } | null>(null);
  const copyEmailTimerRef = useRef<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchClients({ search: search || undefined, include_archived: includeArchived });
      setClients(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : t.clients.error);
    } finally {
      setLoading(false);
    }
  }, [search, includeArchived, t.clients.error]);

  useEffect(() => {
    load();
  }, [load]);

  const handleArchive = async (id: string) => {
    await archiveClient(id);
    load();
  };

  const handleRestore = async (id: string) => {
    await restoreClient(id);
    load();
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

  const closeForm = () => {
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
          telegram_username: form.telegram_username || undefined,
          notes: form.notes || undefined,
        };
        await createClient(payload);
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

  return (
    <section aria-label="clients-section" className="w-full mt-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-bold text-[var(--tg-theme-text-color)]">{t.clients.title}</h2>
        <button
          aria-label="add-client"
          onClick={openCreate}
          className="px-3 py-1.5 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition"
        >
          {t.clients.add_client}
        </button>
      </div>

      {/* Search + filters */}
      <div className="flex gap-2 mb-3 flex-wrap">
        <input
          aria-label="search-clients"
          type="text"
          placeholder={t.clients.search_placeholder}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 min-w-0 border border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <label className="flex items-center gap-1.5 text-sm text-slate-600 cursor-pointer">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(e) => setIncludeArchived(e.target.checked)}
          />
          {t.clients.show_archived}
        </label>
      </div>

      {/* Add client form */}
      {showForm && (
        <form
          aria-label="client-form"
          onSubmit={handleSubmit}
          className="bg-white border border-slate-200 rounded-2xl p-4 mb-4 shadow-sm space-y-3"
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
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
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
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
              />
              <input
                aria-label="last-name"
                placeholder={t.clients.last_name}
                value={form.last_name}
                onChange={(e) => handleFormChange('last_name', e.target.value)}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
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
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
              />
              <input
                aria-label="nip"
                placeholder={t.clients.nip}
                value={form.nip}
                onChange={(e) => handleFormChange('nip', e.target.value)}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
              />
            </>
          )}

          <input
            aria-label="phone"
            placeholder={t.clients.phone}
            value={form.phone}
            onChange={(e) => handleFormChange('phone', e.target.value)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
          />
          <input
            aria-label="email"
            placeholder={t.clients.email}
            value={form.email}
            onChange={(e) => handleFormChange('email', e.target.value)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
          />
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1">{t.clients.telegram}</label>
            <input
              aria-label="telegram-username"
              placeholder={t.clients.telegram_placeholder}
              value={form.telegram_username}
              onChange={(e) => handleFormChange('telegram_username', e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
            />
          </div>

          {formError && (
            <p className="text-sm text-red-600 font-medium">{formError}</p>
          )}

          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={closeForm}
              className="px-3 py-1.5 text-sm rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50"
            >
              {t.clients.cancel}
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-3 py-1.5 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition disabled:opacity-50"
            >
              {t.clients.save}
            </button>
          </div>
        </form>
      )}

      {/* List */}
      {loading && (
        <p className="text-sm text-slate-500 text-center py-4">{t.clients.loading}</p>
      )}
      {!loading && error && (
        <p className="text-sm text-red-600 text-center py-4">{error}</p>
      )}
      {!loading && !error && clients.length === 0 && (
        <p aria-label="no-clients" className="text-sm text-slate-400 text-center py-6">{t.clients.no_clients}</p>
      )}
      {!loading && clients.length > 0 && (
        <ul className="space-y-2" aria-label="clients-list">
          {clients.map((c) => (
            <li
              key={c.id}
              aria-label={`client-item-${c.id}`}
              className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm flex items-start justify-between gap-3"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-semibold text-slate-900 text-sm break-words">{displayName(c)}</span>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-500 font-medium">
                    {c.client_type === 'COMPANY' ? t.clients.company : t.clients.private_person}
                  </span>
                  {c.is_archived && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-700 font-medium">
                      {t.clients.archived_badge}
                    </span>
                  )}
                </div>
                {(c.nip || c.phone || c.email || c.telegram_username) && (
                  <div aria-label={`client-contact-${c.id}`} className="mt-1 space-y-0.5 min-w-0">
                    {c.nip && (
                      <p className="text-xs text-slate-500 break-words min-w-0">
                        <span className="text-slate-400">{t.clients.card_nip_label}</span> {c.nip}
                      </p>
                    )}
                    {c.phone && (
                      <p className="text-xs text-slate-500 break-words min-w-0">
                        <span className="text-slate-400">{t.clients.card_phone_label}</span>{' '}
                        <a
                          href={toTelHref(c.phone)}
                          aria-label={`call-${c.id}`}
                          className="inline-block py-1.5 -my-1.5 text-blue-700 underline underline-offset-2"
                        >
                          {c.phone}
                        </a>
                      </p>
                    )}
                    {c.email && (
                      <p className="text-xs text-slate-500 break-words min-w-0">
                        <span className="text-slate-400">{t.clients.card_email_label}</span>{' '}
                        <button
                          type="button"
                          aria-label={`copy-email-${c.id}`}
                          onClick={() => handleCopyEmail(c)}
                          className="inline-block py-1.5 -my-1.5 text-blue-700 underline underline-offset-2 text-left"
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
                      <p className="text-xs text-slate-500 break-words min-w-0">
                        <span className="text-slate-400">{t.clients.card_telegram_label}</span>{' '}
                        <a
                          href={toTelegramHref(c.telegram_username)}
                          target="_blank"
                          rel="noopener noreferrer"
                          aria-label={`open-telegram-${c.id}`}
                          className="inline-block py-1.5 -my-1.5 text-blue-700 underline underline-offset-2"
                        >
                          {c.telegram_username}
                        </a>
                      </p>
                    )}
                  </div>
                )}
              </div>
              <div className="flex flex-col gap-1.5 flex-shrink-0 items-end">
                <button
                  aria-label={`edit-${c.id}`}
                  onClick={() => openEdit(c)}
                  className="text-xs px-2.5 py-1 rounded-lg bg-blue-50 text-blue-700 font-medium hover:bg-blue-100 transition"
                >
                  {t.clients.edit}
                </button>
                {c.is_archived ? (
                  <button
                    aria-label={`restore-${c.id}`}
                    onClick={() => handleRestore(c.id)}
                    className="text-xs px-2.5 py-1 rounded-lg bg-emerald-50 text-emerald-700 font-medium hover:bg-emerald-100 transition"
                  >
                    {t.clients.restore}
                  </button>
                ) : (
                  <button
                    aria-label={`archive-${c.id}`}
                    onClick={() => handleArchive(c.id)}
                    className="text-xs px-2.5 py-1 rounded-lg bg-slate-50 text-slate-600 font-medium hover:bg-slate-100 transition"
                  >
                    {t.clients.archive}
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-slate-400 text-right mt-2">
        {total > 0 ? `${total}` : ''}
      </p>
    </section>
  );
};
