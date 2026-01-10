# Frontend - Synology Space Analyzer

Modernisiertes React-Dashboard für den Synology Space Analyzer.

## Technologie-Stack

- **React 18** + **TypeScript**
- **Vite** (Build Tool)
- **Tailwind CSS** (Styling)
- **shadcn/ui** (UI Components)
- **Chart.js** (Charts)
- **lucide-react** (Icons)

## Entwicklung

### Voraussetzungen

- Node.js 18+ und npm

### Installation

```bash
cd frontend
npm install
```

### Development Server

```bash
npm run dev
```

Der Development Server läuft auf `http://localhost:5173` und nutzt einen Proxy für API-Calls zu `http://localhost:8080`.

## Build

### Produktions-Build

```bash
npm run build
```

Dies erstellt die optimierten statischen Dateien im `dist/` Verzeichnis.

### Backend-Integration

Das Backend serviert automatisch die gebauten Dateien aus `frontend/dist/`:

1. Build ausführen: `npm run build`
2. Backend starten: `uvicorn app.main:app --host 0.0.0.0 --port 8080`
3. Frontend ist verfügbar unter `http://localhost:8080`

Das Backend erkennt automatisch, ob `frontend/dist/` existiert und serviert die React-App. Falls nicht, fällt es auf die alte Template-Version zurück.

## Projektstruktur

```
frontend/
├── src/
│   ├── components/        # React Komponenten
│   │   ├── ui/           # shadcn/ui Komponenten
│   │   ├── layout/       # Topbar, CommandPalette
│   │   ├── table/        # ScanTable, TableRow, TableActions
│   │   ├── modals/       # ResultsModal, HistoryModal, DetailModal, StorageModal
│   │   └── charts/       # SizeChart
│   ├── hooks/            # Custom Hooks (useScans, useDebounce, etc.)
│   ├── lib/              # API Layer, Utils
│   ├── types/            # TypeScript Interfaces
│   ├── App.tsx           # Hauptkomponente
│   └── main.tsx          # Entry Point
├── dist/                 # Build Output (wird generiert)
└── package.json
```

## Features

- ✅ 100% Feature-Parität mit alter Version
- ✅ Moderne, skalierbare UI
- ✅ Filter, Sort, Density Toggle
- ✅ Command Palette (⌘K)
- ✅ Auto-Refresh (30s)
- ✅ Alle Modals (Results, History, Detail, Storage)
- ✅ Toast Notifications
- ✅ Responsive Design

## API-Integration

Alle API-Calls sind in `src/lib/api.ts` zentralisiert und mappen 1:1 zu den Backend-Endpoints. Keine Backend-Änderungen erforderlich.
