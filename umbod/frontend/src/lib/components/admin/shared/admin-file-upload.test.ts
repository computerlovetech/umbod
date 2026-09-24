import { render } from 'svelte/server';
import { describe, expect, test } from 'vitest';
import AdminFileUpload from './AdminFileUpload.svelte';

describe('AdminFileUpload', () => {
  test('renders a reusable accessible file form control', () => {
    const { body } = render(AdminFileUpload, {
      props: {
        id: 'specification',
        name: 'file',
        label: 'OpenAPI specification',
        accept: 'application/json,.json',
        required: true,
        buttonText: 'Choose JSON file',
        helperText: 'JSON · Maximum 10 MB',
        maxBytes: 10 * 1024 * 1024
      }
    });

    expect(body).toContain('OpenAPI specification');
    expect(body).toContain('Drop a file here');
    expect(body).toContain('Choose JSON file');
    expect(body).toContain('JSON · Maximum 10 MB');
    expect(body).toMatch(/<input[^>]*type="file"[^>]*id="specification"[^>]*name="file"/);
    expect(body).toMatch(/<input[^>]*accept="application\/json,.json"[^>]*required/);
    expect(body).toMatch(/<label[^>]*for="specification"/);
  });

  test('supports optional and disabled form composition', () => {
    const { body } = render(AdminFileUpload, {
      props: {
        id: 'replacement',
        name: 'replacement',
        label: 'Replacement catalog',
        optionalText: '(optional)',
        disabled: true
      }
    });

    expect(body).toContain('(optional)');
    expect(body).toMatch(/<input[^>]*disabled/);
    expect(body).not.toMatch(/<input[^>]*required/);
  });
});
