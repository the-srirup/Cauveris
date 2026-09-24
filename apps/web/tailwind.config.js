export default {
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#0a0a12',
        foreground: '#e0e0ff',
        primary: '#00ffff', // electric cyan
        secondary: '#ffb800', // restrained amber
        success: '#8fbc8f', // soft green
        danger: '#ff6b6b', // red for failures
        muted: '#6b6b80',
      },
    },
  },
  plugins: [],
}