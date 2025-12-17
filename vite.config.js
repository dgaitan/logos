import { defineConfig } from 'vite';
import tailwindcss from '@tailwindcss/vite';
import { resolve } from 'path';

export default defineConfig({
  plugins: [
    tailwindcss(), // This is the new v4 plugin
  ],
  root: resolve('./assets'), // We will create this folder next
  base: '/assets/',
  build: {
    outDir: resolve('./assets/dist'),
    manifest: true,
    emptyOutDir: true,
    rollupOptions: {
      input: {
        // This is your main entry point. 
        // You can import your CSS inside this JS file, or add a separate CSS entry.
        main: resolve('./assets/js/scripts.js'),
      },
    },
  },
});