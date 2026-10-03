const STEPS = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950]
const scale = (name) => Object.fromEntries(STEPS.map((s) => [s, `rgb(var(--${name}-${s}) / <alpha-value>)`]))

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      keyframes: {
        marquee: {
          '0%': { transform: 'translateX(100%)' },
          '100%': { transform: 'translateX(-100%)' },
        },
        confetti: {
          '0%': { transform: 'translateY(0) rotate(0deg)', opacity: '1' },
          '100%': { transform: 'translateY(105vh) rotate(720deg)', opacity: '0.6' },
        },
        popIn: {
          '0%': { transform: 'scale(0.6)', opacity: '0' },
          '70%': { transform: 'scale(1.05)', opacity: '1' },
          '100%': { transform: 'scale(1)' },
        },
      },
      colors: {
        // Values come from CSS variables (src/index.css): the site is dark navy + blue,
        // while everything inside .game-theme (game pages) keeps the original charcoal + emerald.
        'dark-bg': 'rgb(var(--dark-bg) / <alpha-value>)',
        'dark-card': 'rgb(var(--dark-card) / <alpha-value>)',
        'dark-elevated': 'rgb(var(--dark-elevated) / <alpha-value>)',
        'dark-border': 'rgb(var(--dark-border) / <alpha-value>)',
        'brand-blue': '#2f7cf6',
        'brand-green': '#16a34a',
        emerald: scale('emerald'),
        teal: scale('teal'),
      },
    },
  },
  plugins: [],
}
