import { defineConfig } from 'vite';
import { copyFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

function sitesBundle() {
  return {
    name: 'sites-bundle',
    closeBundle() {
      const output = resolve('dist');
      mkdirSync(resolve(output, 'server'), { recursive: true });
      mkdirSync(resolve(output, '.openai'), { recursive: true });
      copyFileSync(resolve('site/server.js'), resolve(output, 'server/index.js'));
      copyFileSync(resolve('.openai/hosting.json'), resolve(output, '.openai/hosting.json'));
    }
  };
}

export default defineConfig({
  root: 'site',
  base: './',
  plugins: [sitesBundle()],
  build: {
    outDir: '../dist',
    emptyOutDir: true
  }
});
