const MARKDOWN_EXTENSIONS = ['.md', '.markdown'];
const MARKDOWN_MIME_TYPE = 'text/markdown';
// Any of these in the accept config means markdown uploads are allowed.
const MARKDOWN_ACCEPT_TYPES = [
  MARKDOWN_MIME_TYPE,
  'text/x-markdown',
  'application/markdown',
  'application/x-markdown',
  ...MARKDOWN_EXTENSIONS,
];
// Browsers on Windows take `file.type` from the registry, which usually has no
// entry for .md: the file then comes with an empty or generic type.
const MARKDOWN_FILE_TYPES = [
  MARKDOWN_MIME_TYPE,
  'text/x-markdown',
  'text/plain',
  'application/octet-stream',
  '',
];

const parseAccept = (accept: string): string[] =>
  accept
    .split(',')
    .map((type) => type.trim())
    .filter(Boolean);

const acceptsMarkdown = (acceptedTypes: string[]): boolean =>
  acceptedTypes.some((type) =>
    MARKDOWN_ACCEPT_TYPES.includes(type.toLowerCase()),
  );

export const isMarkdownFile = (file: File): boolean => {
  const name = file.name.toLowerCase();
  return (
    MARKDOWN_EXTENSIONS.some((ext) => name.endsWith(ext)) &&
    MARKDOWN_FILE_TYPES.includes(file.type)
  );
};

/** MIME type to report for an upload, fixing the one browsers get wrong for markdown. */
export const getUploadContentType = (file: File): string =>
  isMarkdownFile(file) ? MARKDOWN_MIME_TYPE : file.type;

/**
 * Add the markdown extensions to an `accept` value that allows markdown, so the
 * file picker shows .md files even where the OS knows no MIME type for them.
 */
export const withMarkdownExtensions = (accept?: string): string | undefined => {
  if (!accept) {
    return accept;
  }
  const acceptedTypes = parseAccept(accept);
  if (!acceptsMarkdown(acceptedTypes)) {
    return accept;
  }
  const lowered = acceptedTypes.map((type) => type.toLowerCase());
  const missing = MARKDOWN_EXTENSIONS.filter((ext) => !lowered.includes(ext));
  return missing.length ? [accept, ...missing].join(',') : accept;
};

export const isFileAccepted = (file: File, accept?: string): boolean => {
  if (!accept) {
    return true;
  }
  const acceptedTypes = parseAccept(accept);
  if (isMarkdownFile(file) && acceptsMarkdown(acceptedTypes)) {
    return true;
  }
  return acceptedTypes.some((acceptedType) => {
    if (acceptedType.startsWith('.')) {
      return file.name.toLowerCase().endsWith(acceptedType.toLowerCase());
    }
    if (acceptedType.endsWith('/*')) {
      const baseType = acceptedType.slice(0, -2);
      return file.type.startsWith(baseType);
    }
    return file.type === acceptedType;
  });
};
