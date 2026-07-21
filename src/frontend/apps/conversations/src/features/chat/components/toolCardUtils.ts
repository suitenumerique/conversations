import { ToolInvocation } from '@ai-sdk/ui-utils';

export type ToolCardStatus = 'running' | 'completed' | 'error';

interface ToolDisplayInfo {
  label: string;
  icon: string;
}

const TOOL_DISPLAY_INFO: Record<string, ToolDisplayInfo> = {
  web_search: { label: 'Web search', icon: 'search' },
  summarize: { label: 'Summarize', icon: 'summarize' },
  summarize_project: { label: 'Summarize project', icon: 'summarize' },
  document_parsing: { label: 'Document parsing', icon: 'description' },
  document_search_rag: { label: 'Document search', icon: 'find_in_page' },
  conversation_resume: { label: 'Conversation resume', icon: 'history' },
  get_current_weather: { label: 'Weather', icon: 'cloud' },
  self_documentation: { label: 'Assistant info', icon: 'info' },
};

const PREVIEW_MAX_LENGTH = 120;
const EXPANDED_PREVIEW_MAX_LENGTH = 280;

const formatToolName = (toolName: string): string =>
  toolName
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');

export const truncateText = (text: string, maxLength: number): string => {
  const normalized = text.replace(/\s+/g, ' ').trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }

  return `${normalized.slice(0, maxLength - 1).trimEnd()}…`;
};

export const getToolDisplayInfo = (toolName: string): ToolDisplayInfo => {
  return (
    TOOL_DISPLAY_INFO[toolName] ?? {
      label: formatToolName(toolName),
      icon: 'build',
    }
  );
};

export const getToolRunningLabel = (
  toolName: string,
  t: (key: string, options?: Record<string, unknown>) => string,
): string => {
  if (toolName === 'summarize' || toolName === 'summarize_project') {
    return t('Summarizing...');
  }

  if (toolName === 'document_parsing') {
    return t('Extracting documents...');
  }

  if (toolName === 'web_search') {
    return t('Searching the web...');
  }

  if (toolName === 'document_search_rag') {
    return t('Searching documents...');
  }

  return t('Running...');
};

export const getToolErrorFromResult = (result: unknown): string | undefined => {
  if (!result || typeof result !== 'object') {
    return undefined;
  }

  const payload = result as { state?: string; error?: string; kind?: string };

  if (payload.state !== 'error') {
    return undefined;
  }

  return payload.error || payload.kind || 'Tool execution failed';
};

export const getToolCardStatus = (
  toolInvocation: ToolInvocation,
): ToolCardStatus => {
  if (
    toolInvocation.state === 'partial-call' ||
    toolInvocation.state === 'call'
  ) {
    return 'running';
  }

  if (getToolErrorFromResult(toolInvocation.result)) {
    return 'error';
  }

  return 'completed';
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const readStringField = (
  source: Record<string, unknown>,
  keys: string[],
): string | undefined => {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
  }

  return undefined;
};

const extractWebSearchResults = (
  output: unknown,
): Array<{ title?: string; url?: string }> => {
  if (!isRecord(output)) {
    return [];
  }

  return Object.values(output)
    .filter(isRecord)
    .map((entry) => ({
      title: readStringField(entry, ['title']),
      url: readStringField(entry, ['url']),
    }))
    .filter((entry) => entry.title || entry.url);
};

const formatWebSearchOutputPreview = (
  output: unknown,
  t: (key: string, options?: Record<string, unknown>) => string,
  maxLength: number,
): string | undefined => {
  const results = extractWebSearchResults(output);
  if (results.length === 0) {
    return undefined;
  }

  const titles = results
    .map((result) => result.title || result.url)
    .filter((value): value is string => Boolean(value));

  if (titles.length === 0) {
    return t('{{count}} results found', { count: results.length });
  }

  const lead = t('{{count}} results', { count: results.length });
  return truncateText(`${lead}: ${titles.slice(0, 2).join(', ')}`, maxLength);
};

const formatSummarizeOutputPreview = (
  output: unknown,
  maxLength: number,
): string | undefined => {
  if (typeof output === 'string' && output.trim()) {
    return truncateText(output, maxLength);
  }

  if (!isRecord(output)) {
    return undefined;
  }

  const summary = readStringField(output, ['summary', 'return_value', 'text']);
  return summary ? truncateText(summary, maxLength) : undefined;
};

const formatGenericOutputPreview = (
  output: unknown,
  maxLength: number,
): string | undefined => {
  if (typeof output === 'string' && output.trim()) {
    return truncateText(output, maxLength);
  }

  if (typeof output === 'number' || typeof output === 'boolean') {
    return String(output);
  }

  if (!isRecord(output)) {
    return undefined;
  }

  const directValue = readStringField(output, [
    'summary',
    'message',
    'text',
    'title',
    'query',
    'result',
  ]);
  if (directValue) {
    return truncateText(directValue, maxLength);
  }

  if (Array.isArray(output.results)) {
    return truncateText(
      `${output.results.length} results`,
      maxLength,
    );
  }

  const keys = Object.keys(output);
  if (keys.length === 0) {
    return undefined;
  }

  return truncateText(`${keys.length} items`, maxLength);
};

export interface ToolReadableContent {
  inputLabel?: string;
  inputPreview?: string;
  outputPreview?: string;
  headerPreview?: string;
  errorPreview?: string;
}

export const getToolReadableContent = (
  toolName: string,
  args: ToolInvocation['args'],
  output: unknown,
  t: (key: string, options?: Record<string, unknown>) => string,
  maxLength = PREVIEW_MAX_LENGTH,
): ToolReadableContent => {
  const errorPreview = getToolErrorFromResult(output);
  if (errorPreview) {
    return {
      headerPreview: truncateText(errorPreview, maxLength),
      errorPreview: truncateText(errorPreview, EXPANDED_PREVIEW_MAX_LENGTH),
    };
  }

  const argsRecord = isRecord(args) ? args : undefined;
  let inputPreview: string | undefined;
  let outputPreview: string | undefined;

  if (toolName === 'web_search') {
    const query = argsRecord ? readStringField(argsRecord, ['query']) : undefined;
    inputPreview = query
      ? t('Query: {{query}}', { query: truncateText(query, maxLength) })
      : undefined;
    outputPreview = formatWebSearchOutputPreview(output, t, maxLength);
  } else if (
    toolName === 'summarize' ||
    toolName === 'summarize_project'
  ) {
    const instructions = argsRecord
      ? readStringField(argsRecord, ['instructions'])
      : undefined;
    const documentId = argsRecord
      ? readStringField(argsRecord, ['document_id'])
      : undefined;

    if (instructions) {
      inputPreview = t('Instructions: {{instructions}}', {
        instructions: truncateText(instructions, maxLength),
      });
    } else if (documentId) {
      inputPreview = t('Document: {{document}}', {
        document: truncateText(documentId, maxLength),
      });
    }

    outputPreview = formatSummarizeOutputPreview(output, maxLength);
  } else if (toolName === 'document_parsing') {
    const documents = argsRecord?.documents;
    if (typeof documents === 'string' && documents.trim()) {
      inputPreview = t('Documents: {{documents}}', {
        documents: truncateText(documents, maxLength),
      });
    }
  } else if (toolName === 'document_search_rag') {
    const query = argsRecord ? readStringField(argsRecord, ['query']) : undefined;
    inputPreview = query
      ? t('Query: {{query}}', { query: truncateText(query, maxLength) })
      : undefined;
    outputPreview = formatGenericOutputPreview(output, maxLength);
  } else {
    const query = argsRecord ? readStringField(argsRecord, ['query']) : undefined;
    if (query) {
      inputPreview = t('Query: {{query}}', { query: truncateText(query, maxLength) });
    }

    outputPreview = formatGenericOutputPreview(output, maxLength);
  }

  const headerPreview =
    outputPreview ||
    inputPreview ||
    (toolName === 'document_parsing' ? undefined : t('Completed'));

  return {
    inputLabel:
      toolName === 'web_search' || toolName === 'document_search_rag'
        ? t('Request')
        : toolName === 'summarize' || toolName === 'summarize_project'
          ? t('Context')
          : t('Details'),
    inputPreview,
    outputPreview: outputPreview
      ? truncateText(outputPreview, EXPANDED_PREVIEW_MAX_LENGTH)
      : undefined,
    headerPreview,
  };
};

export const getDocumentParsingSummary = (
  args: ToolInvocation['args'],
): string | undefined => {
  const documents: unknown = args?.documents;

  if (
    !Array.isArray(documents) ||
    !documents.every(
      (doc): doc is { identifier: string } =>
        typeof doc === 'object' && doc !== null && 'identifier' in doc,
    )
  ) {
    return undefined;
  }

  return documents.map((doc) => doc.identifier).join(', ');
};

export const getToolExpandedOutputPreview = (
  toolName: string,
  output: unknown,
  t: (key: string, options?: Record<string, unknown>) => string,
): string | undefined => {
  if (toolName === 'web_search') {
    const results = extractWebSearchResults(output);
    if (results.length === 0) {
      return undefined;
    }

    return results
      .slice(0, 3)
      .map((result, index) => {
        const label = result.title || result.url || t('Result {{index}}', { index: index + 1 });
        return `• ${label}`;
      })
      .join('\n');
  }

  return getToolReadableContent(toolName, undefined, output, t, EXPANDED_PREVIEW_MAX_LENGTH)
    .outputPreview;
};
