import React, { useEffect, useState, useCallback } from 'react';
import { ClientType, ClientCreatePayload } from '../types/client';
import {
  fetchClients,
  createClient,
  archiveClient,
  restoreClient,
} from '../api/clients';
import { useI18n } from '../hooks/useI18n';

interface ClientFormState {
  client_type: 'PRIVATE_PERSON' | 'COMPANY';
  first_name: string;
  last_name: string;
  company_name: string;
  phone: string;
  email: string;
  nip: string;
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
  notes: '',
};

export const ClientList: React.FC = () => {
  const { t } = useI18n();
  const [clients, setClients] = useState<ClientType[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [includeArchived, setIncludeArchived] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<ClientFormState>(DEFAULT_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

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

  const handleFormChange = (field: keyof ClientFormState, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
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
      const payload: ClientCreatePayload = {
        client_type: form.client_type,
        first_name: form.first_name || undefined,
        last_name: form.last_name || undefined,
        company_name: form.company_name || undefined,
        phone: form.phone || undefined,
        email: form.email || undefined,
        nip: form.nip || undefined,
        notes: form.notes || undefined,
      };
      await createClient(payload);
      setShowForm(false);
      setForm(DEFAULT_FORM);
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
        <h2 className="text-lg font-bold text-slate-900">{t.clients.title}</h2>
        <button
          aria-label="add-client"
          onClick={() => setShowForm((v) => !v)}
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

          {formError && (
            <p className="text-sm text-red-600 font-medium">{formError}</p>
          )}

          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={() => { setShowForm(false); setForm(DEFAULT_FORM); setFormError(null); }}
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
              className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm flex items-center justify-between gap-3"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-semibold text-slate-900 text-sm truncate">{displayName(c)}</span>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-500 font-medium">
                    {c.client_type === 'COMPANY' ? t.clients.company : t.clients.private_person}
                  </span>
                  {c.is_archived && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-700 font-medium">
                      {t.clients.archived_badge}
                    </span>
                  )}
                </div>
                {c.phone && <p className="text-xs text-slate-500 mt-0.5">{c.phone}</p>}
              </div>
              <div className="flex gap-1.5 flex-shrink-0">
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
