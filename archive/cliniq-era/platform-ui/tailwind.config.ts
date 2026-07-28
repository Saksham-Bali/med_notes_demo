import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./app/**/*.{js,ts,jsx,tsx}', './components/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        clinical: {
          bg: '#0f172a',
          card: '#1e293b',
          border: '#334155',
          accent: '#14b8a6',
          warning: '#f59e0b',
          error: '#ef4444',
        }
      }
    }
  },
  plugins: [],
}
export default config
