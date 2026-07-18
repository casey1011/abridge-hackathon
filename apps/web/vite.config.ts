import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // The pnpm workspace can resolve more than one physical copy of React
  // (root vs. apps/web vs. nested under react-dom). Force a single instance so
  // hooks work — otherwise react-dom and components load different Reacts.
  resolve: {
    dedupe: ['react', 'react-dom'],
  },
})
