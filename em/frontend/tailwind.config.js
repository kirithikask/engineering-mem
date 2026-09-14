/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        em: {
          // Light industrial engineering palette.
          paper: "#F4F3EF",
          surface: "#FFFFFF",
          panel: "#E8E8E4",
          panelDeep: "#DEDDD7",
          line: "#D6D5CF",
          lineSoft: "#E4E3DE",
          graphite: "#1B1E21",
          ink: "#2C3237",
          steel: "#596168",
          muted: "#858C91",
          amber: "#C58B2A",
          amberDark: "#8D621E",
          amberSoft: "#F2E6CC",
          success: "#55745F",
          successSoft: "#E2EAE5",
          warning: "#B47A28",
          fault: "#A94D45",
          faultSoft: "#F0E0DE",
          // Navy — secondary engineering/brand colour
          navy: "#0B2545",
          navyDeep: "#071A33",
          navyMid: "#163A5F",
          navyTint: "#E8EEF5",
        },
      },
      fontFamily: {
        // Local system stacks only: the platform must render identically with
        // no network access, so no webfont CDN is referenced anywhere.
        sans: ['"Segoe UI"', 'system-ui', '-apple-system', 'Roboto', 'Arial', 'sans-serif'],
        mono: ['ui-monospace', '"Cascadia Mono"', 'Consolas', '"SFMono-Regular"', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem' }],
      },
      letterSpacing: {
        label: '0.14em',
      },
      boxShadow: {
        panel: '0 1px 2px rgba(27,30,33,0.06)',
        lift: '0 6px 20px -8px rgba(27,30,33,0.28)',
      },
      keyframes: {
        scanline: {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100%)' },
        },
        navyScan: {
          '0%': { opacity: '0', transform: 'translateY(-8px)' },
          '100%': { opacity: '0.18', transform: 'translateY(100vh)' },
        },
        flow: {
          '0%': { backgroundPosition: '0% 0%' },
          '100%': { backgroundPosition: '200% 0%' },
        },
        riseIn: {
          '0%': { opacity: '0', transform: 'translateY(14px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        sweep: {
          '0%': { transform: 'translateX(-120%)' },
          '100%': { transform: 'translateX(220%)' },
        },
        pulseRing: {
          '0%,100%': { opacity: '0.55' },
          '50%': { opacity: '1' },
        },
        machineReveal: {
          '0%': { opacity: '0', transform: 'scale(0.96) translateY(12px)' },
          '100%': { opacity: '1', transform: 'scale(1) translateY(0)' },
        },
        calloutFade: {
          '0%': { opacity: '0', transform: 'translateX(-6px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
      },
      animation: {
        scanline: 'scanline 4.5s linear infinite',
        flow: 'flow 3s linear infinite',
        riseIn: 'riseIn 0.5s ease-out both',
        sweep: 'sweep 2.4s ease-in-out infinite',
        pulseRing: 'pulseRing 1.8s ease-in-out infinite',
        machineReveal: 'machineReveal 1.1s cubic-bezier(0.22,0.61,0.36,1) both',
        calloutFade: 'calloutFade 0.7s ease-out both',
        navyScan: 'navyScan 6s linear infinite',
      },
    },
  },
  plugins: [],
}
