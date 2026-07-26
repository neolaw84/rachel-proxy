import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig(({ mode }) => {
  const isCloud = mode === 'cloud';
  const outDir = isCloud ? 'dist/cloud' : 'dist/local';

  return {
    root: 'frontend',
    define: {
      'import.meta.env.VITE_MULTI_TENANT': JSON.stringify(isCloud),
    },
    build: {
      outDir: resolve(__dirname, outDir),
      emptyOutDir: true,
      rollupOptions: {
        input: {
          main: resolve(__dirname, 'frontend/index.html'),
        },
      },
    },
  };
});
