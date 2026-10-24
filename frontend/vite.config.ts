import { defineConfig } from 'vite';
import { resolve } from 'node:path';

export default defineConfig({
  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        simulator: resolve(__dirname, 'simulator/index.html'),
        scenarios: resolve(__dirname, 'scenarios/index.html'),
        insights: resolve(__dirname, 'insights/index.html'),
      },
    },
  },
});
