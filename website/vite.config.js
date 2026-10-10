import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import { renderDesktopPage } from './src/downloads.mjs';

const releaseMetadataUrl = new URL('../release-metadata.json', import.meta.url);
const releaseFields = ['chartVersion', 'imageTag', 'sdkVersion'];

export default defineConfig({
  build: {
    rollupOptions: {
      input: {
        desktop: fileURLToPath(new URL('./index.html', import.meta.url)),
        enterprise: fileURLToPath(new URL('./enterprise/index.html', import.meta.url)),
      },
    },
  },
  plugins: [{
    name: 'release-metadata',
    transformIndexHtml: {
      order: 'pre',
      handler(html) {
        html = html.replace(/\{\{\s*partial\.(header|footer)\s*\}\}/g, (_, name) =>
          readFileSync(new URL(`./partials/${name}.html`, import.meta.url), 'utf8'));
        if (html.includes('id="desktop-download-options"')) {
          html = renderDesktopPage(html, JSON.parse(readFileSync(new URL('./public/desktop-downloads.json', import.meta.url), 'utf8')));
        }
        const metadata = JSON.parse(readFileSync(releaseMetadataUrl, 'utf8'));
        if (Object.keys(metadata).length !== releaseFields.length ||
            releaseFields.some((field) => typeof metadata[field] !== 'string' || !metadata[field])) {
          throw new Error('release-metadata.json must define chartVersion, imageTag, and sdkVersion');
        }
        return html.replace(/\{\{\s*release\.([A-Za-z]+)\s*\}\}/g, (_, field) => {
          if (!releaseFields.includes(field)) {
            throw new Error(`Unknown release metadata field: ${field}`);
          }
          return metadata[field];
        });
      },
    },
  }],
});
