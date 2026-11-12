---
type: Software Module
title: File preview components
description: File preview presentation with Markdown, PDF and raster image renderer adapters.
---

# Preview

- [FilePreview.svelte](./FilePreview.svelte) — Preview status, retry and sign-in presentation with adapter-selected content components.
- [MarkdownPreview.svelte](./MarkdownPreview.svelte) — Styled Markdown article accepting content without filesystem or API dependencies.
- [ImagePreview.svelte](./ImagePreview.svelte) — Content-only responsive image display with decode-failure reporting.
- [image-adapter.ts](./image-adapter.ts) — Raster image type selection and binary-to-data-URL preparation without SVG embedding.
- [image-format.ts](./image-format.ts) — Supported raster MIME types, extensions and byte signatures.
- [image-adapter.test.ts](./image-adapter.test.ts) — Raster selection, format detection, binary preservation and invalid-content rejection.
- [image-preview.dom.test.ts](./image-preview.dom.test.ts) — Image rendering, source replacement, decode failure, retry and navigation behavior.
- [PdfPreview.svelte](./PdfPreview.svelte) — Content-only PDF frame using the browser's native viewer with a prepared PDF data URL.
- [pdf-adapter.ts](./pdf-adapter.ts) — PDF type selection, header validation and lossless binary-to-data-URL preparation.
- [pdf-adapter.test.ts](./pdf-adapter.test.ts) — PDF selection, binary preservation, empty content and invalid-document rejection.
- [markdown-adapter.ts](./markdown-adapter.ts) — Markdown MIME detection and extension fallback for unspecified or generic text formats.
- [markdown.ts](./markdown.ts) — Escaped Markdown rendering with raw HTML, images and relative or unsafe links disabled.
- [markdown.test.ts](./markdown.test.ts) — Filetype selection, Markdown formatting, HTML escaping and resource privacy tests.
- [file-preview.dom.test.ts](./file-preview.dom.test.ts) — Renderer replacement, loading and retry interactions through the component boundary.
- [PlainPreview.test-support.svelte](./PlainPreview.test-support.svelte) — Test-only alternate component proving injected renderer replacement.
