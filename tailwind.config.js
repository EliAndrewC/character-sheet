/** Tailwind config for the build-time CSS pipeline.
 *
 * The app used to ship the Tailwind Play CDN runtime (app/static/js/tailwind.js,
 * ~407KB) which compiled CSS in the browser on every page load. We now compile
 * a purged stylesheet (app/static/css/app.css) at build time instead - via the
 * standalone Tailwind CLI in scripts/build-css.sh (local) and the Docker
 * `cssbuild` stage (deploys). This file is the single source of truth for the
 * theme; it must stay in sync with the @font-face / custom CSS in base.html.
 *
 * IMPORTANT: only classes that appear *literally* in the content files below
 * survive purging. Classes assembled by string concatenation in JS won't be
 * detected - add those to `safelist`.
 */
module.exports = {
  // Dark mode is opt-in per user (Profile > Appearance). It's toggled by a
  // `dark` class on <html> (server-rendered from the account preference / a
  // cookie - see app/main.py dark_mode_enabled), NOT the `media` default, so
  // a user's choice always wins over their OS setting.
  darkMode: 'class',
  content: [
    './app/templates/**/*.html',
    './app/static/js/**/*.js',
  ],
  theme: {
    extend: {
      // The theme palette is driven by CSS custom properties (defined in
      // tailwind-input.css for both light `:root` and `.dark`). Because every
      // `bg-ink`, `text-ink/60`, `bg-parchment`, etc. resolves through these
      // variables, flipping the `.dark` class re-themes the whole site without
      // per-element `dark:` variants. The `<alpha-value>` placeholder keeps
      // Tailwind's opacity modifiers (e.g. `text-ink/50`) working.
      colors: {
        parchment: 'rgb(var(--color-parchment) / <alpha-value>)',
        ink: 'rgb(var(--color-ink) / <alpha-value>)',
        accent: 'rgb(var(--color-accent) / <alpha-value>)',
        gold: 'rgb(var(--color-gold) / <alpha-value>)',
        success: {
          DEFAULT: 'rgb(var(--color-success) / <alpha-value>)',
          dark: 'rgb(var(--color-success-dark) / <alpha-value>)',
        },
        info: {
          DEFAULT: 'rgb(var(--color-info) / <alpha-value>)',
          dark: 'rgb(var(--color-info-dark) / <alpha-value>)',
        },
      },
      fontFamily: {
        display: ['var(--font-display)', 'Georgia', 'Cambria', 'serif'],
      },
      boxShadow: {
        sm: '0 1px 2px 0 rgb(var(--shadow-rgb) / 0.07)',
        DEFAULT: '0 1px 3px 0 rgb(var(--shadow-rgb) / 0.10), 0 1px 2px -1px rgb(var(--shadow-rgb) / 0.08)',
        md: '0 4px 6px -1px rgb(var(--shadow-rgb) / 0.10), 0 2px 4px -2px rgb(var(--shadow-rgb) / 0.08)',
        lg: '0 10px 15px -3px rgb(var(--shadow-rgb) / 0.13), 0 4px 6px -4px rgb(var(--shadow-rgb) / 0.10)',
      },
    },
  },
  plugins: [],
};
