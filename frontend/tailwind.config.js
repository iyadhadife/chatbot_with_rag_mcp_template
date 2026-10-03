/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      // Palette neutre sombre + accent orange : remplace gray/indigo pour
      // restyler toute l'interface (y compris ChunksView / ChatMessage).
      colors: {
        gray: {
          50: '#fafafa', 100: '#f2f2f2', 200: '#e4e4e4', 300: '#cfcfcf',
          400: '#a1a1a1', 500: '#707070', 600: '#454545', 700: '#2e2e2e',
          800: '#222222', 900: '#181818', 950: '#121212',
        },
        indigo: {
          300: '#ffb48a', 400: '#ff8f52', 500: '#ff6a1a', 600: '#f25c0c',
          700: '#c2490a', 800: '#8a3407', 900: '#451a03',
        },
        sidebar: '#0e0e0e',
      },
    },
  },
  plugins: [],
}
