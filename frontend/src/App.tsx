import React from 'react';

export const App: React.FC = () => {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center p-6 bg-slate-50 text-slate-900">
      <div className="w-full max-w-md p-8 bg-white rounded-2xl shadow-sm border border-slate-100 text-center">
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 mb-2">
          Renovation App
        </h1>
        <p className="text-sm text-slate-500 font-medium">
          Frontend is running
        </p>
      </div>
    </main>
  );
};

export default App;
