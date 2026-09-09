import React, { useState } from 'react';
import { useAuth } from './hooks/useAuth';
import { I18nProvider, useI18n } from './hooks/useI18n';
import { ClientList } from './components/ClientList';
import { ProjectWorkspace } from './components/ProjectWorkspace';

const AppContent: React.FC = () => {
  const { user, isDevAuth, isLoading, error, retry } = useAuth();
  const { t, locale, setLocale } = useI18n();
  const [activeSection, setActiveSection] = useState<'clients' | 'projects'>('clients');

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col items-center justify-start">
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

      <main className="w-full max-w-lg p-6 flex flex-col items-center">
        <header className="text-center my-6 w-full">
          <div className="flex items-center justify-between">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">
              {t.app.title}
            </h1>
            {/* Language switcher */}
            <div className="flex gap-1">
              {(['pl', 'ru'] as const).map((lang) => (
                <button
                  key={lang}
                  aria-label={`lang-${lang}`}
                  onClick={() => setLocale(lang)}
                  className={`text-xs px-2 py-1 rounded-lg font-semibold uppercase transition ${
                    locale === lang
                      ? 'bg-slate-900 text-white'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  {lang}
                </button>
              ))}
            </div>
          </div>
          <p className="text-sm text-slate-500 mt-1 text-left">
            {t.app.subtitle}
          </p>
        </header>

        {isLoading && (
          <div className="w-full bg-white rounded-2xl p-8 border border-slate-200 shadow-sm text-center">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-slate-200 border-t-blue-600 mb-4" />
            <p className="text-slate-600 font-medium text-sm">
              {t.auth.loading}
            </p>
          </div>
        )}

        {!isLoading && error && (
          <div className="w-full bg-white rounded-2xl p-6 border border-red-100 shadow-sm text-center">
            <div className="w-12 h-12 bg-red-50 text-red-500 rounded-full flex items-center justify-center mx-auto mb-3 text-xl font-bold">
              !
            </div>
            <h2 className="text-lg font-semibold text-red-600 mb-1">
              {t.auth.error_title}
            </h2>
            <p className="text-sm text-slate-600 mb-4">{t.auth.errors[error]}</p>
            <button
              onClick={retry}
              className="px-4 py-2 bg-slate-900 text-white text-sm font-medium rounded-xl hover:bg-slate-800 transition"
            >
              {t.auth.retry}
            </button>
          </div>
        )}

        {!isLoading && user && (
          <>
            <section
              aria-label="user-card"
              className="w-full bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden"
            >
              <div className="p-5 border-b border-slate-100 flex items-center justify-between">
                <div>
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                    {t.auth.logged_in_as}
                  </span>
                  <h2 className="text-lg font-bold text-slate-900">
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
                  <dt className="text-slate-500">Telegram User ID</dt>
                  <dd className="font-mono font-medium text-slate-800">
                    {user.telegram_user_id}
                  </dd>
                </div>

                {user.username && (
                  <div className="flex justify-between border-b border-slate-50 pb-2">
                    <dt className="text-slate-500">Username</dt>
                    <dd className="font-medium text-blue-600">
                      @{user.username}
                    </dd>
                  </div>
                )}

                <div className="flex justify-between border-b border-slate-50 pb-2">
                  <dt className="text-slate-500">UUID</dt>
                  <dd className="font-mono text-xs text-slate-600 break-all">
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
                    ? 'bg-slate-900 text-white'
                    : 'bg-white border border-slate-200 text-slate-600'
                }`}
              >
                {t.navigation.clients}
              </button>
              <button
                type="button"
                aria-label="show-projects"
                onClick={() => setActiveSection('projects')}
                className={`px-3 py-2 text-sm font-semibold rounded-xl transition ${
                  activeSection === 'projects'
                    ? 'bg-slate-900 text-white'
                    : 'bg-white border border-slate-200 text-slate-600'
                }`}
              >
                {t.navigation.projects}
              </button>
            </nav>

            {activeSection === 'clients' ? <ClientList /> : <ProjectWorkspace />}
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
