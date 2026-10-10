import React, { useCallback, useState } from 'react';
import { useAuth } from './hooks/useAuth';
import { I18nProvider, useI18n } from './hooks/useI18n';
import { ClientList } from './components/ClientList';
import { PriceBook } from './components/PriceBook';
import { ProjectWorkspace } from './components/ProjectWorkspace';
import { AccountModal } from './components/AccountModal';
import { AppMenu, AppMenuItem } from './components/AppMenu';

const AppContent: React.FC = () => {
  const { user, isDevAuth, isLoading, error, retry } = useAuth();
  const { t, locale, setLocale } = useI18n();
  const [activeSection, setActiveSection] = useState<'clients' | 'projects' | 'pricebook'>('clients');
  const [projectsNavToken, setProjectsNavToken] = useState(0);
  const [showAccount, setShowAccount] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const closeMenu = useCallback(() => setMenuOpen(false), []);

  const choose = (section: 'clients' | 'projects' | 'pricebook') => {
    setActiveSection(section);
    // Choosing "Obiekty" always leads back to the list of objects, even when it is already the open section.
    if (section === 'projects') setProjectsNavToken((n) => n + 1);
    setMenuOpen(false);
  };
  const menuItems: AppMenuItem[] = [
    { id: 'show-clients', label: t.navigation.clients, active: activeSection === 'clients', onSelect: () => choose('clients') },
    { id: 'show-projects', label: t.navigation.projects, active: activeSection === 'projects', onSelect: () => choose('projects') },
    { id: 'show-pricebook', label: t.navigation.pricebook, active: activeSection === 'pricebook', onSelect: () => choose('pricebook') },
  ];

  return (
    <div
      className="min-h-screen flex flex-col items-center justify-start w-full overflow-x-hidden transition-colors"
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
          style={{ backgroundColor: 'var(--tg-theme-bg-color)' }}
        >
          <div className="flex items-center gap-1 min-w-0">
            {!isLoading && user && (
              <button
                type="button"
                aria-label="open-menu"
                aria-expanded={menuOpen}
                onClick={() => setMenuOpen(true)}
                className="min-h-11 min-w-11 -ml-2.5 shrink-0 flex items-center justify-center rounded-xl"
                style={{ color: 'var(--tg-theme-text-color)' }}
              >
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true">
                  <path d="M4 7h16M4 12h16M4 17h16" />
                </svg>
              </button>
            )}
            <h1 className="text-lg font-bold tracking-tight truncate" style={{ color: 'var(--tg-theme-text-color)' }}>
              {t.app.title}
            </h1>
          </div>
          {/* Language switcher: small by the owner's request, in the right corner */}
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
        </header>

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

        {!isLoading && error && (
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
              <ClientList />
            ) : activeSection === 'projects' ? (
              <ProjectWorkspace resetSignal={projectsNavToken} backSuspended={showAccount || menuOpen} />
            ) : (
              <PriceBook />
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
        />
      )}
    </div>
  );
};

export const App: React.FC = () => (
  <I18nProvider>
    <AppContent />
  </I18nProvider>
);

export default App;
