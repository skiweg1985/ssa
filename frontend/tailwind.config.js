/** @type {import('tailwindcss').Config} */

/* Farb-, Schrift- und Motion-Mapping. Das System ist in design.md beschrieben.
 *
 * Dieser Config ist die Brücke zwischen src/tokens.css und den Utility-Klassen.
 * Jede Farbe hier zeigt auf einen Token — es gibt keinen Hex-Wert mehr im Projekt.
 *
 * Zwei Entscheidungen, die beim Lesen überraschen können:
 *
 * 1. Die Rampen `slate`, `primary`, `blue`, `emerald`, `green`, `amber`, `yellow` und `red`
 *    sind ÜBERSCHRIEBEN. Sie tragen nicht mehr Tailwinds Standardwerte, sondern die
 *    Tokens aus tokens.css. So greift das Designsystem in allen bestehenden Aufrufen, ohne dass
 *    ~865 Klassennamen in 46 Dateien angefasst werden mussten.
 *    `green` zeigt auf dieselben Werte wie `emerald`, `yellow` auf dieselben wie `amber`,
 *    `blue` auf dieselben wie `primary` — die doppelt vergebenen Statusfarben
 *    kollabieren damit auf drei Bedeutungen und einen Akzent.
 *
 * 2. `white` ist ein kühles Beinahe-Weiß, kein #fff — bg-white liefert
 *    oklch(99.4% 0.003 250).
 *
 * `purple`, `violet`, `indigo` und `cyan` sind bewusst NICHT definiert. Sie kamen nur in
 * den entfernten Verlaufs-Headern vor; wären sie hier gemappt, könnten sie unbemerkt
 * zurückkehren.
 */

// Erzeugt aus einer Token-Präfix eine 50–900-Rampe mit funktionierendem Alpha-Modifier.
const ramp = (prefix, shades) =>
  Object.fromEntries(
    shades.map((s) => [s, `oklch(var(--${prefix}-${s}) / <alpha-value>)`])
  )

const FULL = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900]

const accent = ramp("a", FULL)
const ok = ramp("ok", FULL)
const warn = ramp("warn", FULL)
const danger = ramp("dg", FULL)

export default {
  darkMode: ["class"],
  content: ['./index.html', './src/**/*.{ts,tsx,js,jsx}'],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: { "2xl": "1400px" },
    },
    extend: {
      colors: {
        // ---- Neutrale Rampe -------------------------------------------------------
        slate: { ...ramp("n", [...FULL, 950]) },
        white: "oklch(var(--n-paper) / <alpha-value>)",

        // ---- Akzent ---------------------------------------------------------------
        primary: {
          ...accent,
          DEFAULT: "oklch(var(--a-500) / <alpha-value>)",
          foreground: "oklch(var(--n-paper) / <alpha-value>)",
        },
        blue: accent, // „läuft gerade" trug vorher eine eigene Blaufamilie — jetzt der Akzent

        // ---- Status: genau drei Bedeutungen ---------------------------------------
        emerald: ok,
        green: ok, // war doppelt vergeben — zeigt jetzt auf dieselbe Rampe
        amber: warn,
        yellow: warn, // dito
        red: danger,

        // ---- Semantische Aliase für neuen Code ------------------------------------
        paper: "var(--color-paper)",
        surface: "var(--color-surface)",
        ink: "var(--color-ink)",
        rule: "var(--color-rule)",
        accent: {
          DEFAULT: "var(--color-accent)",
          ink: "var(--color-accent-ink)",
          soft: "var(--color-accent-soft)",
        },
        border: "var(--color-rule)",
        input: "var(--color-rule-2)",
        ring: "var(--color-focus)",
        background: "var(--color-paper)",
        foreground: "var(--color-ink)",
        muted: {
          DEFAULT: "var(--color-surface-2)",
          foreground: "var(--color-ink-3)",
        },
        card: {
          DEFAULT: "var(--color-surface)",
          foreground: "var(--color-ink)",
        },
        popover: {
          DEFAULT: "var(--color-surface)",
          foreground: "var(--color-ink)",
        },
        destructive: {
          DEFAULT: "oklch(var(--dg-600) / <alpha-value>)",
          foreground: "oklch(var(--n-paper) / <alpha-value>)",
        },
        secondary: {
          DEFAULT: "var(--color-surface-2)",
          foreground: "var(--color-ink)",
        },
      },

      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "sans-serif"],
        display: ["Space Grotesk", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SF Mono", "Menlo", "Consolas", "monospace"],
      },
      letterSpacing: {
        display: "var(--tracking-display)",
        label: "var(--tracking-label)",
      },

      // Mit dem Lineal gezogen — keine Pillen, keine 0px-Brutalität.
      // (Der frühere `md`-Eintrag hatte eine Klammer zu viel und fiel still aus.)
      borderRadius: {
        sm: "var(--radius-inset)",
        md: "var(--radius-control)",
        lg: "var(--radius-card)",
        xl: "var(--radius-card)",
      },

      transitionTimingFunction: {
        out: "var(--ease-out)",
        in: "var(--ease-in)",
        "in-out": "var(--ease-in-out)",
        DEFAULT: "var(--ease-out)",
      },
      transitionDuration: {
        instant: "var(--dur-instant)",
        short: "var(--dur-short)",
        medium: "var(--dur-medium)",
        DEFAULT: "var(--dur-short)",
      },

      zIndex: {
        sticky: "var(--z-sticky)",
        header: "var(--z-header)",
        overlay: "var(--z-overlay)",
        dialog: "var(--z-dialog)",
        popover: "var(--z-popover)",
        toast: "var(--z-toast)",
      },

      keyframes: {
        "accordion-down": {
          from: { height: 0 },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: 0 },
        },
      },
      animation: {
        "accordion-down": "accordion-down var(--dur-short) var(--ease-out)",
        "accordion-up": "accordion-up var(--dur-short) var(--ease-out)",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}
