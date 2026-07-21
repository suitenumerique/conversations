import {
  getDocumentParsingSummary,
  getToolCardStatus,
  getToolErrorFromResult,
  getToolReadableContent,
  truncateText,
} from '../toolCardUtils';

describe('toolCardUtils', () => {
  it('truncates long text with an ellipsis', () => {
    expect(truncateText('abcdefghij', 6)).toBe('abcde…');
  });

  it('detects tool errors from result payloads', () => {
    expect(
      getToolErrorFromResult({ state: 'error', error: 'Boom' }),
    ).toBe('Boom');
    expect(getToolErrorFromResult({ ok: true })).toBeUndefined();
  });

  it('maps invocation states to card statuses', () => {
    expect(
      getToolCardStatus({
        toolCallId: '1',
        toolName: 'web_search',
        state: 'call',
        args: {},
      }),
    ).toBe('running');

    expect(
      getToolCardStatus({
        toolCallId: '2',
        toolName: 'web_search',
        state: 'result',
        args: {},
        result: { ok: true },
      }),
    ).toBe('completed');
  });

  it('formats web search content without JSON', () => {
    const content = getToolReadableContent(
      'web_search',
      { query: 'climate news' },
      {
        '0': { title: 'Article A', url: 'https://example.com/a' },
        '1': { title: 'Article B', url: 'https://example.com/b' },
      },
      (key, options) =>
        key.replace('{{count}}', String(options?.count ?? '')),
    );

    expect(content.inputPreview).toBe('Query: climate news');
    expect(content.outputPreview).toContain('2 results');
    expect(content.outputPreview).toContain('Article A');
  });

  it('extracts document parsing identifiers from args', () => {
    expect(
      getDocumentParsingSummary({
        documents: [{ identifier: 'doc-a.pdf' }, { identifier: 'doc-b.pdf' }],
      }),
    ).toBe('doc-a.pdf, doc-b.pdf');
  });
});
