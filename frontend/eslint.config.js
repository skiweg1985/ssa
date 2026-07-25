import js from "@eslint/js"
import globals from "globals"
import tseslint from "typescript-eslint"
import reactHooks from "eslint-plugin-react-hooks"
import reactRefresh from "eslint-plugin-react-refresh"

export default tseslint.config(
  {
    // Build-Artefakte und Abhängigkeiten nicht linten
    ignores: ["dist/**", "node_modules/**", "*.config.js", "*.config.ts"],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      // Bewusst nicht "...reactHooks.configs.recommended.rules": ab
      // eslint-plugin-react-hooks@7 enthaelt "recommended" den vollstaendigen
      // React-Compiler-Regelsatz (16 statt 2 Regeln). Der schlaegt hier
      // 16-mal an -- ueberwiegend beim ueblichen "im Effekt laden bzw.
      // Formularstate zuruecksetzen"-Muster -- und liesse den Lint-Lauf mit
      // --max-warnings 0 sofort rot werden. Der Plugin-Major war lediglich
      // erzwungen, weil erst v7 ESLint 10 in den Peers fuehrt; die Uebernahme
      // des Compiler-Regelsatzes ist eine eigene Entscheidung und laeuft
      // ueber ein eigenes Issue. Bis dahin gilt der bisherige Regelsatz.
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],
      // Ungenutzte Variablen: führendes _ als bewusste Kennzeichnung erlauben
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
    },
  },
)
