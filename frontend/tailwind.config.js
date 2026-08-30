/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'Cascadia Code', 'monospace'],
      },
      colors: {
        // ComplyFlow brand palette
        brand: {
          50: '#f0f4ff',
          100: '#e0e9ff',
          200: '#c7d5fd',
          300: '#a4b8fc',
          400: '#7e93f8',
          500: '#5b6ef3',
          600: '#4451e8',
          700: '#3840d3',
          800: '#2f36ab',
          900: '#2b3188',
          950: '#1c1f57',
        },
        // Status colors
        ready: '#16a34a',
        action: '#d97706',
        critical: '#dc2626',
        conflict: '#9333ea',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in': 'fadeIn 0.3s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(8px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}
