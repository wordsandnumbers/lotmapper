/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'media',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        auth: {
          canvas: 'rgb(var(--auth-canvas) / <alpha-value>)',
          panel: 'rgb(var(--auth-panel) / <alpha-value>)',
          logo: 'rgb(var(--auth-logo) / <alpha-value>)',
          tagline: 'rgb(var(--auth-tagline) / <alpha-value>)',
          heading: 'rgb(var(--auth-heading) / <alpha-value>)',
          body: 'rgb(var(--auth-body) / <alpha-value>)',
        },
        brand: {
          primary: 'rgb(var(--brand-primary) / <alpha-value>)',
          primaryHover: 'rgb(var(--brand-primary-hover) / <alpha-value>)',
          accent: 'rgb(var(--brand-accent) / <alpha-value>)',
        },
        app: {
          canvas: 'rgb(var(--app-canvas) / <alpha-value>)',
          panel: 'rgb(var(--app-panel) / <alpha-value>)',
          heading: 'rgb(var(--app-heading) / <alpha-value>)',
          body: 'rgb(var(--app-body) / <alpha-value>)',
        },
      },
    },
  },
  plugins: [],
}
