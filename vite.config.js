import { defineConfig } from 'vite';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig({
  root: 'frontend',
  esbuild: { jsx: 'automatic' },
  build: {
    outDir: '../static/react',
    emptyOutDir: true,
    cssCodeSplit: false,
    rollupOptions: {
      // Rollup resolves explicit entry points from the process working
      // directory, not Vite's `root`. Use an absolute path so this works both
      // from the repository and from the Docker frontend build stage.
      input: fileURLToPath(new URL('./frontend/src/main.jsx', import.meta.url)),
      output: {
        entryFileNames: 'app.js',
        assetFileNames: ({ names }) => names?.some((name) => name.endsWith('.css')) ? 'style.css' : 'assets/[name]-[hash][extname]',
      },
    },
  },
});
