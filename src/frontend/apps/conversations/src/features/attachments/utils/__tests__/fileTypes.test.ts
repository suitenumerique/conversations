import {
  getUploadContentType,
  isFileAccepted,
  withMarkdownExtensions,
} from '../fileTypes';

const ACCEPT_WITH_MARKDOWN = 'application/pdf,text/markdown,image/*';
const ACCEPT_WITHOUT_MARKDOWN = 'application/pdf,image/*';

const makeFile = (name: string, type: string) =>
  new File(['content'], name, { type });

describe('isFileAccepted', () => {
  it.each(['', 'application/octet-stream', 'text/markdown', 'text/plain'])(
    'accepts a .md file with type %j',
    (type) => {
      expect(
        isFileAccepted(makeFile('notes.md', type), ACCEPT_WITH_MARKDOWN),
      ).toBe(true);
    },
  );

  it('accepts a .markdown file with an empty type', () => {
    expect(
      isFileAccepted(makeFile('NOTES.Markdown', ''), ACCEPT_WITH_MARKDOWN),
    ).toBe(true);
  });

  it('rejects a .md file when the config does not accept markdown', () => {
    expect(
      isFileAccepted(makeFile('notes.md', ''), ACCEPT_WITHOUT_MARKDOWN),
    ).toBe(false);
  });

  it('rejects a .md file whose type is not a markdown-compatible one', () => {
    expect(
      isFileAccepted(makeFile('notes.md', 'text/html'), ACCEPT_WITH_MARKDOWN),
    ).toBe(false);
  });

  it.each(['', 'application/octet-stream'])(
    'still rejects a disallowed extension with type %j',
    (type) => {
      expect(
        isFileAccepted(makeFile('setup.exe', type), ACCEPT_WITH_MARKDOWN),
      ).toBe(false);
    },
  );

  it('keeps the existing MIME matching for other files', () => {
    expect(
      isFileAccepted(
        makeFile('doc.pdf', 'application/pdf'),
        ACCEPT_WITH_MARKDOWN,
      ),
    ).toBe(true);
    expect(
      isFileAccepted(makeFile('photo.png', 'image/png'), ACCEPT_WITH_MARKDOWN),
    ).toBe(true);
    expect(isFileAccepted(makeFile('doc.pdf', ''), ACCEPT_WITH_MARKDOWN)).toBe(
      false,
    );
  });

  it('accepts everything when there is no config', () => {
    expect(isFileAccepted(makeFile('setup.exe', ''), undefined)).toBe(true);
  });
});

describe('getUploadContentType', () => {
  it.each(['', 'application/octet-stream', 'text/markdown'])(
    'reports text/markdown for a .md file with type %j',
    (type) => {
      expect(getUploadContentType(makeFile('notes.md', type))).toBe(
        'text/markdown',
      );
    },
  );

  it('keeps the browser type for other files', () => {
    expect(getUploadContentType(makeFile('setup.exe', ''))).toBe('');
    expect(
      getUploadContentType(makeFile('data.bin', 'application/octet-stream')),
    ).toBe('application/octet-stream');
  });
});

describe('withMarkdownExtensions', () => {
  it('adds the markdown extensions when markdown is accepted', () => {
    expect(withMarkdownExtensions(ACCEPT_WITH_MARKDOWN)).toBe(
      `${ACCEPT_WITH_MARKDOWN},.md,.markdown`,
    );
  });

  it('does not duplicate extensions already present', () => {
    expect(withMarkdownExtensions('text/markdown,.MD,.markdown')).toBe(
      'text/markdown,.MD,.markdown',
    );
  });

  it('leaves a config without markdown untouched', () => {
    expect(withMarkdownExtensions(ACCEPT_WITHOUT_MARKDOWN)).toBe(
      ACCEPT_WITHOUT_MARKDOWN,
    );
    expect(withMarkdownExtensions(undefined)).toBeUndefined();
  });
});
