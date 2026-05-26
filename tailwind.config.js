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
  content: [
    './app/templates/**/*.html',
    './app/static/js/**/*.js',
  ],
  theme: {
    extend: {
      colors: {
        parchment: '#f5f0e8',
        ink: '#2c1810',
        accent: '#8b0000',
        gold: '#b8860b',
        success: { DEFAULT: '#4d6b46', dark: '#3a5235' },
        info: { DEFAULT: '#3f5d70', dark: '#324a5a' },
      },
      fontFamily: {
        display: ['var(--font-display)', 'Georgia', 'Cambria', 'serif'],
      },
      boxShadow: {
        sm: '0 1px 2px 0 rgba(44,24,16,0.07)',
        DEFAULT: '0 1px 3px 0 rgba(44,24,16,0.10), 0 1px 2px -1px rgba(44,24,16,0.08)',
        md: '0 4px 6px -1px rgba(44,24,16,0.10), 0 2px 4px -2px rgba(44,24,16,0.08)',
        lg: '0 10px 15px -3px rgba(44,24,16,0.13), 0 4px 6px -4px rgba(44,24,16,0.10)',
      },
    },
  },
  plugins: [],
};
