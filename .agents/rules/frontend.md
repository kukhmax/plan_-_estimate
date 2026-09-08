# Frontend Engineering Rules

## 1. Technology Stack
- **Library**: React 18+ (functional components, hooks).
- **Language**: TypeScript (strict mode enabled, `noImplicitAny: true`, strict null checks).
- **Build Tool**: Vite (fast HMR, optimized ESM builds).
- **Styling**: Tailwind CSS (clean utility classes, responsive mobile-first Telegram Mini App design).
- **Icons & UI**: Lightweight Lucide icons or headless components.
- **Testing**: Vitest + React Testing Library.

## 2. Directory Structure Conventions
```
frontend/
├── src/
│   ├── api/                  # Typed API client, fetchers, and react-query/swr hooks
│   ├── assets/               # Static media, icons, brand logos
│   ├── components/           # Reusable presentational components
│   │   ├── common/           # Buttons, Inputs, Modals, Cards, Loaders
│   │   ├── layout/           # App header, navigation, Telegram container
│   │   └── domain/           # ObiektCard, RoomList, SubstrateBadge, QualityPicker
│   ├── features/             # Feature modules grouped by business domain
│   │   ├── clients/
│   │   ├── obiekty/
│   │   ├── rooms/
│   │   ├── inspections/
│   │   ├── estimates/
│   │   ├── protocols/
│   │   └── pricebook/
│   ├── hooks/                # Custom React hooks (Telegram WebApp, viewport, storage)
│   ├── i18n/                 # Internationalization: dictionaries & translation providers
│   │   ├── locales/
│   │   │   ├── pl.json       # Polish UI strings
│   │   │   └── ru.json       # Russian UI strings
│   │   └── context.tsx
│   ├── types/                # TypeScript interface definitions (mirrored from backend DTOs)
│   ├── utils/                # Formatting (currency, area m², date), offline storage helpers
│   ├── App.tsx
│   └── main.tsx
├── public/
├── index.html
├── tailwind.config.js
├── tsconfig.json
├── vite.config.ts
└── package.json
```

## 3. Strict Frontend Rules

### Rule A: Never Hardcode Prices or Rates in Components
- **Zero Hardcoded Prices**: No prices, labor rates, material allowances, or markup percentages may exist in frontend component files.
- All pricing and monetary calculation logic resides on the backend or is dynamically fed by the backend Price Book (`/api/v1/pricebook`).
- Frontend components only format and display monetary values provided by backend DTOs using standard currency formatters (e.g. `120,00 zł`).

### Rule B: Never Hardcode Legal Content or Norms in Components
- **Zero Hardcoded Legal Text**: Technical conditions, Polish Building Law references, ITB guidelines, PN-EN standard clauses, and contract disclaimers must never be hardcoded into React JSX/TSX.
- Legal snippets, warranty disclaimers, and technical acceptance clauses must be retrieved from the backend domain knowledge catalog (`/api/v1/legal-knowledge` / `/api/v1/protocols/templates`).

### Rule C: Internationalization (PL / RU) Outside Business Logic
- Every user-facing UI string must be translated and accessed via i18n translation keys (e.g. `t('rooms.substrate.inspection_title')`).
- Languages supported:
  - **PL** (Polish) - default for Polish construction context and contractor workflows.
  - **RU** (Russian) - secondary option for contractor interface.
- **Client-facing documents**: All generated proposals, estimates, technical acceptance protocols, and contracts default strictly to **PL** (Polish), complying with Polish construction standards and commercial law.

### Rule D: Telegram Mini App UX Standards
- Responsive, mobile-first design optimized for Telegram WebApp viewport.
- Handle Telegram `themeParams` (dark/light theme auto-adaptation).
- Utilize native Telegram features: MainButton, BackButton, HapticFeedback when appropriate.
- Safely handle running inside Telegram WebApp as well as fallback browser testing during development.

### Rule E: Offline Readiness (IndexedDB)
- Architecture must accommodate draft persistence via IndexedDB (e.g. `idb` or Dexie.js) so that inspection photos, room measurements, and on-site notes can be drafted without reliable cellular signal in basements or reinforced concrete buildings.
- Offline sync must be clean and not compromise backend consistency.

### Rule F: Testing
- Component unit tests with Vitest and `@testing-library/react`.
- Test user interactions (entering room dimensions, selecting substrate, switching language).
- Test that components render correctly without hardcoded values.
