import MarkdownIt, { type Token } from 'markdown-it';

const markdown = new MarkdownIt({ html: false, linkify: false, typographer: false });
markdown.validateLink = (url: string): boolean => /^(https?:\/\/|mailto:)/i.test(url);
markdown.renderer.rules.image = (tokens: Token[], index: number): string => markdown.utils.escapeHtml(tokens[index].content);

export function renderMarkdown(content: string): string {
  return markdown.render(content);
}
