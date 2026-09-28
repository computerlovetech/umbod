import { readFileSync } from 'node:fs';
import { defineConfig } from 'vite';

const releaseMetadataUrl = new URL('../release-metadata.json', import.meta.url);
const releaseFields = ['chartVersion', 'imageTag', 'sdkVersion'];

export default defineConfig({
  plugins: [{
    name: 'release-metadata',
    transformIndexHtml(html) {
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
  }],
});
