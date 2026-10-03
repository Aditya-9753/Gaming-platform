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
        // Rudra247 theme: neutral charcoal like popular casino lobbies
        'dark-bg': '#141416',
        'dark-card': '#1d1d20',
        'dark-elevated': '#28282c',
        'dark-border': '#323238',
        'brand-blue': '#2f7cf6',
        'brand-green': '#16a34a',
      },
    },
  },
  plugins: [],
}
