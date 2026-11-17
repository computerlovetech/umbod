import MarkdownIt, { type Token } from 'markdown-it';
import hljs from 'highlight.js/lib/core';
import typescript from 'highlight.js/lib/languages/typescript';
import javascript from 'highlight.js/lib/languages/javascript';
import json from 'highlight.js/lib/languages/json';
import python from 'highlight.js/lib/languages/python';
import bash from 'highlight.js/lib/languages/bash';
import yaml from 'highlight.js/lib/languages/yaml';
import css from 'highlight.js/lib/languages/css';
import xml from 'highlight.js/lib/languages/xml';
import sql from 'highlight.js/lib/languages/sql';
import markdownGrammar from 'highlight.js/lib/languages/markdown';
import plaintext from 'highlight.js/lib/languages/plaintext';

for (const [name, grammar] of Object.entries({ typescript, javascript, json, python, bash, yaml, css, xml, sql, markdown: markdownGrammar, plaintext })) {
  hljs.registerLanguage(name, grammar);
}

function markdownBody(content: string): string {
  return content.replace(/^\uFEFF?---[ \t]*\r?\n(?:[^\n]*\n)*?(?:---|\.\.\.)[ \t]*\r?(?:\n|$)/, '');
}

export function renderMarkdown(content: string): string {
  let highlightedCharacters = 0;
  let diagrams = 0;
  const renderer = new MarkdownIt({ html: false, linkify: false, typographer: false });
  renderer.validateLink = (url: string): boolean => /^(https?:\/\/|mailto:)/i.test(url);
  renderer.renderer.rules.image = (tokens: Token[], index: number): string => renderer.utils.escapeHtml(tokens[index].content);
  renderer.renderer.rules.fence = (tokens: Token[], index: number): string => {
    const token = tokens[index];
    const language = token.info.trim().split(/\s+/)[0].toLowerCase();
    const escaped = renderer.utils.escapeHtml(token.content);
    if (language === 'mermaid' && ++diagrams <= 8) {
      return '<div class="mermaid-diagram" data-mermaid><pre><code>' + escaped + '</code></pre></div>\n';
    }
    if (language !== 'mermaid' && hljs.getLanguage(language) && token.content.length <= 20000 && highlightedCharacters + token.content.length <= 100000) {
      highlightedCharacters += token.content.length;
      try {
        return '<pre><code class="hljs">' + hljs.highlight(token.content, { language, ignoreIllegals: true }).value + '</code></pre>\n';
      } catch {
        return '<pre><code>' + escaped + '</code></pre>\n';
      }
    }
    return '<pre><code>' + escaped + '</code></pre>\n';
  };
  return renderer.render(markdownBody(content));
}
