import { useCallback, useEffect, useState } from 'react';
import { fetchClients, restoreClient } from '../api/clients';
import { fetchProjects, restoreProject } from '../api/projects';
import { useI18n } from '../hooks/useI18n';
import { ClientType } from '../types/client';
import { ProjectType } from '../types/project';

type ArchiveTab = 'clients' | 'projects';

function clientName(client: ClientType): string {
  if (client.client_type === 'COMPANY') return client.company_name ?? '—';
  return [client.first_name, client.last_name].filter(Boolean).join(' ') || '—';
}

/**
 * The archive (Stage 16K.5): what the owner put away — clients and objects — in one place, with the way back. The lists of
 * clients and objects show only what is in work; "restore" is here.
 */
export function ArchiveScreen() {
  const { t } = useI18n();
  const text = t.archive;
  const [tab, setTab] = useState<ArchiveTab>('clients');
  const [clients, setClients] = useState<ClientType[] | null>(null);
  const [projects, setProjects] = useState<ProjectType[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoadFailed(false);
    try {
      const [clientData, projectData] = await Promise.all([fetchClients({ include_archived: true }), fetchProjects(true)]);
      setClients(clientData.items.filter((client) => client.is_archived));
      setProjects(projectData.items.filter((project) => project.is_archived));
    } catch {
      setLoadFailed(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const restore = async (kind: ArchiveTab, id: string) => {
    if (busyId) return;
    setBusyId(id);
    setError(null);
    setNotice(null);
    try {
      if (kind === 'clients') {
        await restoreClient(id);
        setClients((current) => (current ? current.filter((client) => client.id !== id) : current));
        setNotice(text.restored_client);
      } else {
        await restoreProject(id);
        setProjects((current) => (current ? current.filter((project) => project.id !== id) : current));
        setNotice(text.restored_project);
      }
    } catch {
      setError(text.error_restore);
    } finally {
      setBusyId(null);
    }
  };

  const tabButton = (value: ArchiveTab, label: string, count: number | undefined) => (
    <button
      key={value}
      type="button"
      role="tab"
      aria-selected={tab === value}
      aria-label={`archive-tab-${value}`}
      onClick={() => {
        setTab(value);
        setNotice(null);
        setError(null);
      }}
      className={`min-h-11 px-4 text-sm font-semibold rounded-xl transition ${
        tab === value ? 'bg-blue-600 text-white shadow-sm' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
      }`}
    >
      {label}
      {count !== undefined && <span aria-label={`archive-count-${value}`}> ({count})</span>}
    </button>
  );

  return (
    <section aria-label="archive-section" className="w-full mt-4 space-y-3">
      <h2 className="text-lg font-bold text-[var(--tg-theme-text-color)]">{text.title}</h2>
      <p className="text-sm text-[var(--tg-theme-hint-color)] break-words">{text.intro}</p>

      <div role="tablist" aria-label="archive-tabs" className="flex flex-wrap gap-2">
        {tabButton('clients', text.clients_tab, clients?.length)}
        {tabButton('projects', text.projects_tab, projects?.length)}
      </div>

      {notice && <p role="status" className="text-sm text-emerald-700 break-words">{notice}</p>}
      {error && <p role="alert" className="text-sm text-red-600 break-words">{error}</p>}

      {loadFailed && (
        <div className="space-y-2">
          <p role="alert" className="text-sm text-red-600 break-words">{text.error_load}</p>
          <button
            type="button"
            aria-label="archive-retry"
            onClick={() => void load()}
            className="w-full min-h-11 px-4 text-sm font-semibold rounded-xl bg-blue-600 text-white"
          >
            {text.retry}
          </button>
        </div>
      )}

      {!loadFailed && (tab === 'clients' ? clients : projects) === null && (
        <p className="text-sm text-slate-500">{t.clients.loading}</p>
      )}

      {!loadFailed && tab === 'clients' && clients !== null && (
        clients.length === 0 ? (
          <p aria-label="archive-empty-clients" className="text-sm text-slate-400 text-center py-6">{text.empty_clients}</p>
        ) : (
          <ul aria-label="archive-clients-list" className="space-y-2">
            {clients.map((client) => (
              <li key={client.id} aria-label={`archived-client-${client.id}`} className="bg-white border border-slate-200 rounded-2xl p-3 shadow-sm space-y-2">
                <p className="font-semibold text-slate-900 text-sm break-words">{clientName(client)}</p>
                <button
                  type="button"
                  aria-label={`restore-client-${client.id}`}
                  disabled={busyId !== null}
                  onClick={() => void restore('clients', client.id)}
                  className="w-full min-h-11 px-3 text-sm font-semibold rounded-xl bg-emerald-50 text-emerald-700 hover:bg-emerald-100 transition disabled:opacity-50"
                >
                  {busyId === client.id ? text.restoring : text.restore}
                </button>
              </li>
            ))}
          </ul>
        )
      )}

      {!loadFailed && tab === 'projects' && projects !== null && (
        projects.length === 0 ? (
          <p aria-label="archive-empty-projects" className="text-sm text-slate-400 text-center py-6">{text.empty_projects}</p>
        ) : (
          <ul aria-label="archive-projects-list" className="space-y-2">
            {projects.map((project) => (
              <li key={project.id} aria-label={`archived-project-${project.id}`} className="bg-white border border-slate-200 rounded-2xl p-3 shadow-sm space-y-2">
                <p className="font-semibold text-slate-900 text-sm break-words">{project.name}</p>
                <p className="text-xs text-slate-500 break-words">{[project.address, project.city].filter(Boolean).join(', ')}</p>
                <button
                  type="button"
                  aria-label={`restore-project-${project.id}`}
                  disabled={busyId !== null}
                  onClick={() => void restore('projects', project.id)}
                  className="w-full min-h-11 px-3 text-sm font-semibold rounded-xl bg-emerald-50 text-emerald-700 hover:bg-emerald-100 transition disabled:opacity-50"
                >
                  {busyId === project.id ? text.restoring : text.restore}
                </button>
              </li>
            ))}
          </ul>
        )
      )}
    </section>
  );
}
