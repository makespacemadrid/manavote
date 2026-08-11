import { defineConfig } from 'vite';

export default defineConfig({
  root: 'frontend',
  esbuild: { jsx: 'automatic' },
  build: {
    outDir: '../static/react',
    emptyOutDir: true,
    cssCodeSplit: false,
    rollupOptions: {
      input: 'src/main.jsx',
      output: {
        entryFileNames: 'app.js',
        assetFileNames: ({ names }) => names?.some((name) => name.endsWith('.css')) ? 'style.css' : 'assets/[name]-[hash][extname]',
      },
    },
  },
});
