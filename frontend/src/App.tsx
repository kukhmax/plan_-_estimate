import React, { useState } from 'react';
import { useAuth } from './hooks/useAuth';
import { I18nProvider, useI18n } from './hooks/useI18n';
import { ClientList } from './components/ClientList';
import { ProjectWorkspace } from './components/ProjectWorkspace';

const AppContent: React.FC = () => {
  const { user, isDevAuth, isLoading, error, retry } = useAuth();
  const { t, locale, setLocale } = useI18n();
  const [activeSection, setActiveSection] = useState<'clients' | 'projects'>('clients');
  const [projectsNavToken, setProjectsNavToken] = useState(0);

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

      <main className="w-full max-w-lg p-4 sm:p-6 flex flex-col items-center">
        <header className="text-center my-6 w-full">
          <div className="flex items-center justify-between">
            <h1
              className="text-2xl font-bold tracking-tight"
              style={{ color: 'var(--tg-theme-text-color)' }}
            >
              {t.app.title}
            </h1>
            {/* Language switcher */}
            <div className="flex gap-1">
              {(['pl', 'ru'] as const).map((lang) => (
                <button
                  key={lang}
                  aria-label={`lang-${lang}`}
                  onClick={() => setLocale(lang)}
                  className="text-xs px-2 py-1 rounded-lg font-semibold uppercase transition"
                  style={
                    locale === lang
                      ? {
                          backgroundColor: 'var(--tg-theme-button-color)',
                          color: 'var(--tg-theme-button-text-color)',
                        }
                      : {
                          backgroundColor: 'var(--tg-theme-secondary-bg-color)',
                          color: 'var(--tg-theme-hint-color)',
                        }
                  }
                >
                  {lang}
                </button>
              ))}
            </div>
          </div>
          <p
            className="text-sm mt-1 text-left"
            style={{ color: 'var(--tg-theme-hint-color)' }}
          >
            {t.app.subtitle}
          </p>
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
            <section
              aria-label="user-card"
              className="w-full rounded-2xl border border-slate-200 shadow-sm overflow-hidden"
              style={{
                backgroundColor: 'var(--tg-theme-secondary-bg-color)',
              }}
            >
              <div className="p-5 border-b border-slate-100 flex items-center justify-between">
                <div>
                  <span
                    className="text-xs font-semibold uppercase tracking-wider"
                    style={{ color: 'var(--tg-theme-hint-color)' }}
                  >
                    {t.auth.logged_in_as}
                  </span>
                  <h2
                    className="text-lg font-bold"
                    style={{ color: 'var(--tg-theme-text-color)' }}
                  >
                    {user.first_name || user.last_name
                      ? `${user.first_name || ''} ${user.last_name || ''}`.trim()
                      : user.username || 'Wykonawca'}
                  </h2>
                </div>
                <span
                  className={`text-xs px-2.5 py-1 rounded-full font-semibold ${
                    isDevAuth
                      ? 'bg-amber-100 text-amber-800'
                      : 'bg-emerald-100 text-emerald-800'
                  }`}
                >
                  {isDevAuth ? t.auth.mock_auth : t.auth.telegram_verified}
                </span>
              </div>

              <dl className="p-5 space-y-3 text-sm">
                <div className="flex justify-between border-b border-slate-50 pb-2">
                  <dt style={{ color: 'var(--tg-theme-hint-color)' }}>Telegram User ID</dt>
                  <dd
                    className="font-mono font-medium"
                    style={{ color: 'var(--tg-theme-text-color)' }}
                  >
                    {user.telegram_user_id}
                  </dd>
                </div>

                {user.username && (
                  <div className="flex justify-between border-b border-slate-50 pb-2">
                    <dt style={{ color: 'var(--tg-theme-hint-color)' }}>Username</dt>
                    <dd
                      className="font-medium"
                      style={{ color: 'var(--tg-theme-link-color)' }}
                    >
                      @{user.username}
                    </dd>
                  </div>
                )}

                <div className="flex justify-between border-b border-slate-50 pb-2">
                  <dt style={{ color: 'var(--tg-theme-hint-color)' }}>UUID</dt>
                  <dd
                    className="font-mono text-xs break-all"
                    style={{ color: 'var(--tg-theme-hint-color)' }}
                  >
                    {user.id}
                  </dd>
                </div>
              </dl>
            </section>

            <nav aria-label="main-navigation" className="w-full mt-4 grid grid-cols-2 gap-2">
              <button
                type="button"
                aria-label="show-clients"
                onClick={() => setActiveSection('clients')}
                className={`px-3 py-2 text-sm font-semibold rounded-xl transition ${
                  activeSection === 'clients'
                    ? ''
                    : 'border border-slate-200'
                }`}
                style={
                  activeSection === 'clients'
                    ? {
                        backgroundColor: 'var(--tg-theme-button-color)',
                        color: 'var(--tg-theme-button-text-color)',
                      }
                    : {
                        backgroundColor: 'var(--tg-theme-secondary-bg-color)',
                        color: 'var(--tg-theme-hint-color)',
                      }
                }
              >
                {t.navigation.clients}
              </button>
              <button
                type="button"
                aria-label="show-projects"
                onClick={() => {
                  setActiveSection('projects');
                  setProjectsNavToken((n) => n + 1);
                }}
                className={`px-3 py-2 text-sm font-semibold rounded-xl transition ${
                  activeSection === 'projects'
                    ? ''
                    : 'border border-slate-200'
                }`}
                style={
                  activeSection === 'projects'
                    ? {
                        backgroundColor: 'var(--tg-theme-button-color)',
                        color: 'var(--tg-theme-button-text-color)',
                      }
                    : {
                        backgroundColor: 'var(--tg-theme-secondary-bg-color)',
                        color: 'var(--tg-theme-hint-color)',
                      }
                }
              >
                {t.navigation.projects}
              </button>
            </nav>

            {activeSection === 'clients' ? (
              <ClientList />
            ) : (
              <ProjectWorkspace resetSignal={projectsNavToken} />
            )}
          </>
        )}
      </main>
    </div>
  );
};

export const App: React.FC = () => (
  <I18nProvider>
    <AppContent />
  </I18nProvider>
);

export default App;
