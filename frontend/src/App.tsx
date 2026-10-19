import React, { useCallback, useEffect, useState } from 'react';
import { useAuth } from './hooks/useAuth';
import { I18nProvider, useI18n } from './hooks/useI18n';
import { AccessScreen } from './components/AccessScreen';
import { ArchiveScreen } from './components/ArchiveScreen';
import { ClientList } from './components/ClientList';
import { PriceBook } from './components/PriceBook';
import { SentDocuments } from './components/SentDocuments';
import { SecurityProbe } from './components/SecurityProbe';
import { CalendarScreen } from './components/CalendarScreen';
import { KnowledgeBase } from './components/KnowledgeBase';
import { ProjectOpenRequest, ProjectWorkspace } from './components/ProjectWorkspace';
import { AccountModal } from './components/AccountModal';
import { AppMenu, AppMenuItem } from './components/AppMenu';
import { ConnectionBanner } from './components/ConnectionBanner';
import { SyncScreen } from './components/SyncScreen';
import { SyncStrip } from './components/SyncStrip';
import { purgeStaleReads } from './offline/readCache';
import { requestPersistentStorage } from './offline/persist';
import { startSync } from './offline/sync';
import { startConnectionWatch } from './offline/watch';

type Section = 'clients' | 'projects' | 'calendar' | 'pricebook' | 'archive' | 'documents' | 'knowledge' | 'access' | 'security';

/** The button of a reminder message opens the Mini App with `?open=calendar` or `?open=project:<id>` (Stage 18D / 18E). */
function openTarget(search: string): { section: Section; projectId?: string } | null {
  const value = new URLSearchParams(search).get('open');
  if (value === 'calendar') return { section: 'calendar' };
  const match = value?.match(/^project:([0-9a-f-]{36})$/i);
  return match ? { section: 'projects', projectId: match[1] } : null;
}

const AppContent: React.FC = () => {
  const { user, isDevAuth, isLoading, error, accessContact, retry } = useAuth();
  const { t, locale, setLocale } = useI18n();
  const [target] = useState(() => openTarget(typeof window === 'undefined' ? '' : window.location.search));
  const [activeSection, setActiveSection] = useState<Section>(target?.section ?? 'clients');
  const [projectsNavToken, setProjectsNavToken] = useState(0);
  const [showAccount, setShowAccount] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [showSync, setShowSync] = useState(false); // Stage 19E: the screen of what waits on the phone
  const [priceNavToken, setPriceNavToken] = useState(0);
  const [openRequest, setOpenRequest] = useState<ProjectOpenRequest | null>(
    target?.projectId ? { token: 1, projectId: target.projectId, view: 'project' } : null,
  );
  const closeMenu = useCallback(() => setMenuOpen(false), []);
  // Stage 19B: the connection is watched while the application is open; copies not refreshed for 30 days are dropped
  useEffect(() => {
    void purgeStaleReads();
    const stopWatch = startConnectionWatch();
    const stopSync = startSync(); // Stage 19C: what was changed without a signal is sent when it returns
    void requestPersistentStorage(); // Stage 19F: ask the browser not to clear what waits on the phone
    return () => {
      stopWatch();
      stopSync();
    };
  }, []);

  const choose = (section: Section) => {
    setActiveSection(section);
    setOpenRequest(null);
    // Choosing "Obiekty" always leads back to the list of objects, even when it is already the open section.
    if (section === 'projects') setProjectsNavToken((n) => n + 1);
    if (section === 'pricebook') setPriceNavToken((n) => n + 1);
    setMenuOpen(false);
  };
  // "Смета" on the card of a client: the section of objects opens straight on the estimates of that object.
  const openEstimatesOf = (projectId: string) => {
    setOpenRequest((previous) => ({ token: (previous?.token ?? 0) + 1, projectId, view: 'estimates' }));
    setActiveSection('projects');
  };
  // A line of the calendar leads to the screen of its object.
  const openProjectOf = (projectId: string) => {
    setOpenRequest((previous) => ({ token: (previous?.token ?? 0) + 1, projectId, view: 'project' }));
    setActiveSection('projects');
  };
  const menuItems: AppMenuItem[] = [
    { id: 'show-clients', label: t.navigation.clients, active: activeSection === 'clients', onSelect: () => choose('clients') },
    { id: 'show-projects', label: t.navigation.projects, active: activeSection === 'projects', onSelect: () => choose('projects') },
    { id: 'show-calendar', label: t.navigation.calendar, active: activeSection === 'calendar', onSelect: () => choose('calendar') },
    { id: 'show-pricebook', label: t.navigation.pricebook, active: activeSection === 'pricebook', onSelect: () => choose('pricebook') },
    { id: 'show-archive', label: t.navigation.archive, active: activeSection === 'archive', onSelect: () => choose('archive') },
    { id: 'show-documents', label: t.navigation.documents, active: activeSection === 'documents', onSelect: () => choose('documents') },
    { id: 'show-knowledge', label: t.navigation.knowledge, active: activeSection === 'knowledge', onSelect: () => choose('knowledge') },
    ...(user?.is_admin
      ? [{ id: 'show-access', label: t.navigation.access, active: activeSection === 'access', onSelect: () => choose('access') }]
      : []),
    { id: 'show-security', label: t.navigation.security, active: activeSection === 'security', onSelect: () => choose('security') },
  ];

  return (
    // overflow-x-clip, not -hidden: "hidden" makes this block a scroll container, the sticky header then sticks to it (it never
    // scrolls) and not to the screen -- the header scrolled away on the phone (Stage 17). Guarded by App.test.tsx.
    <div
      className="min-h-screen flex flex-col items-center justify-start w-full overflow-x-clip transition-colors"
      style={{
        backgroundColor: 'var(--tg-theme-bg-color)',
        color: 'var(--tg-theme-text-color)',
        minHeight: 'var(--tg-viewport-stable-height, 100vh)',
      }}
    >
      {/* Dev Auth Warning Banner */}
      {isDevAuth && (
        <aside
          role="alert"
          aria-label="dev-auth-banner"
          className="w-full bg-amber-500 text-slate-950 px-4 py-2.5 text-center font-bold text-xs sm:text-sm tracking-wide shadow-sm flex items-center justify-center gap-2"
        >
          <span className="text-base leading-none">⚠️</span>
          <span>{t.auth.dev_banner}</span>
        </aside>
      )}

      <main className="w-full max-w-lg p-4 sm:p-6 flex-1 flex flex-col items-center">
        <header
          aria-label="app-header"
          className="sticky top-0 z-30 w-[calc(100%+2rem)] sm:w-[calc(100%+3rem)] -mx-4 -mt-4 sm:-mx-6 sm:-mt-6 mb-4 px-4 sm:px-6 py-1 flex items-center justify-between gap-2 min-h-14"
          // a hairline under the pinned header, so scrolled content does not look cut off beneath it
          style={{ backgroundColor: 'var(--tg-theme-bg-color)', borderBottom: '1px solid var(--tg-theme-secondary-bg-color)' }}
        >
          <div className="flex items-center gap-1 min-w-0">
            <h1 className="text-lg font-bold tracking-tight truncate" style={{ color: 'var(--tg-theme-text-color)' }}>
              {t.app.title}
            </h1>
          </div>
          {/* Language switcher (small, by the owner's request) and the menu button: both in the right corner, the menu button last */}
          <div className="flex items-center gap-2 shrink-0">
            <div className="flex gap-0.5 shrink-0 rounded-lg p-0.5" style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color)' }}>
              {(['pl', 'ru'] as const).map((lang) => (
                <button
                  key={lang}
                  aria-label={`lang-${lang}`}
                  onClick={() => setLocale(lang)}
                  className="min-h-9 min-w-9 text-xs px-2 rounded-md font-semibold uppercase transition"
                  style={
                    locale === lang
                      ? { backgroundColor: 'var(--tg-theme-button-color)', color: 'var(--tg-theme-button-text-color)' }
                      : { color: 'var(--tg-theme-hint-color)' }
                  }
                >
                  {lang}
                </button>
              ))}
            </div>
            {!isLoading && user && (
              <button
                type="button"
                aria-label="open-menu"
                aria-expanded={menuOpen}
                onClick={() => setMenuOpen(true)}
                className="min-h-11 min-w-11 -mr-2.5 shrink-0 flex items-center justify-center rounded-xl"
                style={{ color: 'var(--tg-theme-text-color)' }}
              >
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true">
                  <path d="M4 7h16M4 12h16M4 17h16" />
                </svg>
              </button>
            )}
          </div>
        </header>

        {!isLoading && user && <ConnectionBanner />}
        {!isLoading && user && <SyncStrip onOpen={() => setShowSync(true)} />}

        {isLoading && (
          <div
            className="w-full rounded-2xl p-8 border border-slate-200 shadow-sm text-center"
            style={{
              backgroundColor: 'var(--tg-theme-secondary-bg-color)',
              color: 'var(--tg-theme-text-color)',
            }}
          >
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-slate-200 border-t-blue-600 mb-4" />
            <p className="font-medium text-sm" style={{ color: 'var(--tg-theme-hint-color)' }}>
              {t.auth.loading}
            </p>
          </div>
        )}

        {!isLoading && (error === 'access_denied' || error === 'access_blocked') && (
          <div
            role="alert"
            aria-label="access-denied"
            className="w-full rounded-2xl p-6 border border-amber-200 shadow-sm text-center space-y-3"
            style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color)' }}
          >
            <h2 className="text-lg font-semibold break-words">
              {error === 'access_blocked' ? t.access.blocked_title : t.access.denied_title}
            </h2>
            <p className="text-sm break-words" style={{ color: 'var(--tg-theme-hint-color)' }}>
              {error === 'access_blocked' ? t.access.blocked_text : t.access.denied_text}
            </p>
            {accessContact && (
              <p aria-label="access-contact-text" className="text-sm font-semibold break-words">
                {t.access.contact_intro}: {accessContact}
              </p>
            )}
            <button
              onClick={retry}
              className="w-full min-h-11 px-4 py-2 text-sm font-medium rounded-xl transition"
              style={{ backgroundColor: 'var(--tg-theme-button-color)', color: 'var(--tg-theme-button-text-color)' }}
            >
              {t.access.try_again}
            </button>
          </div>
        )}

        {!isLoading && error && error !== 'access_denied' && error !== 'access_blocked' && (
          <div
            className="w-full rounded-2xl p-6 border border-red-100 shadow-sm text-center"
            style={{
              backgroundColor: 'var(--tg-theme-secondary-bg-color)',
            }}
          >
            <div className="w-12 h-12 bg-red-50 text-red-500 rounded-full flex items-center justify-center mx-auto mb-3 text-xl font-bold">
              !
            </div>
            <h2 className="text-lg font-semibold text-red-600 mb-1">
              {t.auth.error_title}
            </h2>
            <p className="text-sm mb-4" style={{ color: 'var(--tg-theme-hint-color)' }}>
              {t.auth.errors[error]}
            </p>
            <button
              onClick={retry}
              className="px-4 py-2 text-sm font-medium rounded-xl transition"
              style={{
                backgroundColor: 'var(--tg-theme-button-color)',
                color: 'var(--tg-theme-button-text-color)',
              }}
            >
              {t.auth.retry}
            </button>
          </div>
        )}

        {!isLoading && user && (
          <>
            {activeSection === 'clients' ? (
              <ClientList onOpenEstimate={openEstimatesOf} backSuspended={showAccount || menuOpen || showSync} />
            ) : activeSection === 'projects' ? (
              <ProjectWorkspace resetSignal={projectsNavToken} backSuspended={showAccount || menuOpen || showSync} openRequest={openRequest} />
            ) : activeSection === 'calendar' ? (
              <CalendarScreen backSuspended={showAccount || menuOpen || showSync} onOpenProject={openProjectOf} />
            ) : activeSection === 'archive' ? (
              <ArchiveScreen />
            ) : activeSection === 'documents' ? (
              <SentDocuments />
            ) : activeSection === 'knowledge' ? (
              <KnowledgeBase backSuspended={showAccount || menuOpen || showSync} />
            ) : activeSection === 'access' && user.is_admin ? (
              <AccessScreen />
            ) : activeSection === 'security' ? (
              <SecurityProbe />
            ) : (
              <PriceBook resetSignal={priceNavToken} backSuspended={showAccount || menuOpen || showSync} />
            )}
          </>
        )}
      </main>

      {!isLoading && user && (
        <AppMenu
          open={menuOpen}
          title={t.app.title}
          accountLabel={t.auth.account}
          items={menuItems}
          onClose={closeMenu}
          onOpenAccount={() => {
            setMenuOpen(false);
            setShowAccount(true);
          }}
        />
      )}

      {showAccount && user && (
        <AccountModal
          user={user}
          isDevAuth={isDevAuth}
          onClose={() => setShowAccount(false)}
          onOpenSync={() => {
            setShowAccount(false);
            setShowSync(true);
          }}
        />
      )}

      {showSync && user && <SyncScreen onClose={() => setShowSync(false)} />}
    </div>
  );
};

export const App: React.FC = () => (
  <I18nProvider>
    <AppContent />
  </I18nProvider>
);

export default App;
