export default {
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#080a16',
        surface: '#0d1024',
        'surface-2': '#141837',
        foreground: '#e8eafc',
        muted: '#8a90b8',
        primary: '#00e5ff',
        'primary-dim': '#0a1428',
        secondary: '#ffb300',
        success: '#58d68d',
        danger: '#ff5c8a',
      },
    },
  },
  plugins: [],
}