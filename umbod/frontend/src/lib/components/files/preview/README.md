---
type: Software Module
title: File preview components
description: File preview presentation with CSV tables, plain text, Markdown, PDF and raster image renderer adapters.
---

# Preview

- [CsvPreview.svelte](./CsvPreview.svelte) — Read-only CSV table with bounded rows and columns, literal cells and plain text fallback for malformed CSV.
- [csv.ts](./csv.ts) — Quoted CSV parsing and bounded rectangular table preparation without header guessing or value coercion.
- [csv-preview-state.svelte.ts](./csv-preview-state.svelte.ts) — Reactive CSV presentation derived from current content without I/O.
- [csv-adapter.ts](./csv-adapter.ts) — CSV MIME selection and extension fallback using the bounded text reader.
- [csv.test.ts](./csv.test.ts) — CSV quoting, line endings, ragged rows, malformed input and display limits.
- [csv-adapter.test.ts](./csv-adapter.test.ts) — CSV selection, text adapter precedence and content-port loading.
- [csv-preview.dom.test.ts](./csv-preview.dom.test.ts) — Literal table rendering, content replacement, truncation and malformed CSV fallback.

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
- [TextPreview.svelte](./TextPreview.svelte) — Content-only, read-only plain text display with preserved whitespace and wrapped long lines.
- [text-adapter.ts](./text-adapter.ts) — Plain text, YAML, TOML and log selection using the existing bounded text reader.
- [text-adapter.test.ts](./text-adapter.test.ts) — Text selection, Markdown precedence and unchanged text loading.
- [text-preview.dom.test.ts](./text-preview.dom.test.ts) — Literal text rendering, selection replacement, empty files and read-permission gating.
