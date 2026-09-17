/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        paper: '#F3EEE1',
        parchment: '#E9E0CC',
        vellum: '#FAF7EE',
        ink: '#1B1611',
        soot: '#2A241C',
        smoke: '#6E6455',
        faint: '#A79B86',
        line: '#D8CDB2',
        vermilion: '#D5431F',
        ember: '#A93212',
        pine: '#23402F',
        moss: '#3E5C48',
        butter: '#F2B705',
      },
      fontFamily: {
        display: ['Fraunces', 'Georgia', 'Times New Roman', 'serif'],
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      boxShadow: {
        hard: '4px 4px 0 0 #1B1611',
        'hard-sm': '2px 2px 0 0 #1B1611',
        card: '0 1px 0 #D8CDB2, 0 16px 36px -28px rgba(27,22,17,.45)',
        stamp: 'inset 0 0 0 1px currentColor',
      },
      keyframes: {
        rise: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        stampIn: {
          '0%': { opacity: '0', transform: 'scale(1.4) rotate(-8deg)' },
          '60%': { opacity: '1', transform: 'scale(.96) rotate(-4deg)' },
          '100%': { opacity: '1', transform: 'scale(1) rotate(-4deg)' },
        },
        dots: {
          '0%, 60%, 100%': { opacity: '.25' },
          '30%': { opacity: '1' },
        },
        shimmer: {
          '0%': { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(220%)' },
        },
      },
      animation: {
        rise: 'rise .45s cubic-bezier(.2,.7,.2,1) both',
        stamp: 'stampIn .35s cubic-bezier(.2,.7,.2,1) both',
      },
    },
  },
  plugins: [],
}
