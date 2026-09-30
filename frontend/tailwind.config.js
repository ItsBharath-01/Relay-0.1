/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Primary brand = indigo
        primary: {
          50: '#eef2ff',
          100: '#e0e7ff',
          200: '#c7d2fe',
          300: '#a5b4fc',
          400: '#818cf8',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
          800: '#3730a3',
          900: '#312e81',
          950: '#1e1b4b',
        },
        brand: {
          50: '#eef2ff',
          100: '#e0e7ff',
          200: '#c7d2fe',
          300: '#a5b4fc',
          400: '#818cf8',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
          800: '#3730a3',
          900: '#312e81',
          950: '#1e1b4b',
        },
        status: {
          pending: {
            bg: '#f1f5f9',
            text: '#475569',
            border: '#cbd5e1',
          },
          running: {
            bg: '#eff6ff',
            text: '#1d4ed8',
            border: '#93c5fd',
          },
          success: {
            bg: '#f0fdf4',
            text: '#15803d',
            border: '#86efac',
          },
          warning: {
            bg: '#fffbeb',
            text: '#b45309',
            border: '#fde68a',
          },
          error: {
            bg: '#fef2f2',
            text: '#b91c1c',
            border: '#fca5a5',
          },
          approval: {
            bg: '#f5f3ff',
            text: '#6d28d9',
            border: '#c4b5fd',
          },
        }
      },
      fontFamily: {
        sans: [
          'Inter',
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI"',
          'Roboto',
          '"Noto Sans"',
          '"Noto Sans Devanagari"',
          '"Noto Sans Kannada"',
          '"Noto Sans Tamil"',
          '"Noto Sans Telugu"',
          '"Noto Sans Malayalam"',
          '"Noto Sans Bengali"',
          'sans-serif',
        ],
        mono: ['"JetBrains Mono"', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      },
      boxShadow: {
        'subtle': '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
        'lifted': '0 4px 6px -1px rgba(0, 0, 0, 0.07), 0 2px 4px -2px rgba(0, 0, 0, 0.05)',
      },
      borderRadius: {
        'subtle': '8px',
        'card': '12px',
      }
    },
  },
  plugins: [],
}
