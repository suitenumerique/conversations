/**
 * Client-side mirror of the backend `ArtifactSpec` (see
 * `src/backend/chat/artifacts/schema.py`).
 *
 * The artifact comes from the model's tool-call `args` and is therefore
 * untrusted: we re-validate and sanitize it here before rendering. Only
 * whitelisted block types are accepted; anything malformed is dropped so a
 * bad spec never crashes the chat or renders arbitrary content.
 */

export type Tone = 'neutral' | 'success' | 'danger' | 'warning' | 'info';

const TONES: ReadonlySet<string> = new Set([
  'neutral',
  'success',
  'danger',
  'warning',
  'info',
]);

// Bounds mirror the backend; kept generous but finite to avoid huge renders.
const MAX_BLOCKS = 12;
const MAX_STAT_ITEMS = 8;
const MAX_CATEGORIES = 50;
const MAX_SERIES = 6;
const MAX_TABLE_ROWS = 100;
const MAX_TABLE_COLS = 12;
const MAX_LABEL_LEN = 200;
const MAX_TEXT_LEN = 4000;

export interface StatItem {
  label: string;
  value: string;
  tone: Tone;
}

export interface StatGridBlock {
  type: 'stat_grid';
  items: StatItem[];
}

export interface Series {
  name: string;
  data: number[];
  tone: Tone | null;
}

export interface BarChartBlock {
  type: 'bar_chart';
  title: string;
  categories: string[];
  series: Series[];
  stacked: boolean;
  valueSuffix: string | null;
}

export interface LineChartBlock {
  type: 'line_chart';
  title: string;
  categories: string[];
  series: Series[];
  valueSuffix: string | null;
}

export interface TableBlock {
  type: 'table';
  title: string;
  headers: string[];
  rows: string[][];
}

export interface CalloutBlock {
  type: 'callout';
  tone: Tone;
  title: string | null;
  text: string;
}

export type ArtifactBlock =
  | StatGridBlock
  | BarChartBlock
  | LineChartBlock
  | TableBlock
  | CalloutBlock;

export interface ArtifactSpec {
  title: string;
  blocks: ArtifactBlock[];
}

const isObject = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v);

const toTone = (v: unknown, fallback: Tone): Tone =>
  typeof v === 'string' && TONES.has(v) ? (v as Tone) : fallback;

const toShortString = (v: unknown): string | null => {
  if (typeof v !== 'string') {
    return null;
  }
  const trimmed = v.trim();
  if (!trimmed) {
    return null;
  }
  return trimmed.slice(0, MAX_LABEL_LEN);
};

const toCellString = (v: unknown): string => {
  if (typeof v === 'string') {
    return v.slice(0, MAX_LABEL_LEN);
  }
  if (typeof v === 'number' || typeof v === 'boolean') {
    return String(v);
  }
  return '';
};

const toNumberArray = (v: unknown): number[] | null => {
  if (!Array.isArray(v) || v.length === 0 || v.length > MAX_CATEGORIES) {
    return null;
  }
  const out: number[] = [];
  for (const item of v) {
    const n = typeof item === 'number' ? item : Number(item);
    if (!Number.isFinite(n)) {
      return null;
    }
    out.push(n);
  }
  return out;
};

const parseSeries = (v: unknown, expectedLength: number): Series | null => {
  if (!isObject(v)) {
    return null;
  }
  const name = toShortString(v.name);
  const data = toNumberArray(v.data);
  if (name === null || data === null || data.length !== expectedLength) {
    return null;
  }
  return {
    name,
    data,
    tone: TONES.has(v.tone as string) ? (v.tone as Tone) : null,
  };
};

const parseCategories = (v: unknown): string[] | null => {
  if (!Array.isArray(v) || v.length === 0 || v.length > MAX_CATEGORIES) {
    return null;
  }
  const out: string[] = [];
  for (const item of v) {
    const s = toShortString(item);
    if (s === null) {
      return null;
    }
    out.push(s);
  }
  return out;
};

const parseChartSeries = (
  v: unknown,
  expectedLength: number,
): Series[] | null => {
  if (!Array.isArray(v) || v.length === 0 || v.length > MAX_SERIES) {
    return null;
  }
  const out: Series[] = [];
  for (const item of v) {
    const serie = parseSeries(item, expectedLength);
    if (serie === null) {
      return null;
    }
    out.push(serie);
  }
  return out;
};

const parseBlock = (raw: unknown): ArtifactBlock | null => {
  if (!isObject(raw) || typeof raw.type !== 'string') {
    return null;
  }

  switch (raw.type) {
    case 'stat_grid': {
      if (!Array.isArray(raw.items)) {
        return null;
      }
      const items: StatItem[] = [];
      for (const item of raw.items.slice(0, MAX_STAT_ITEMS)) {
        if (!isObject(item)) {
          continue;
        }
        const label = toShortString(item.label);
        const value = toShortString(item.value);
        if (label === null || value === null) {
          continue;
        }
        items.push({ label, value, tone: toTone(item.tone, 'neutral') });
      }
      return items.length > 0 ? { type: 'stat_grid', items } : null;
    }

    case 'bar_chart':
    case 'line_chart': {
      const title = toShortString(raw.title);
      const categories = parseCategories(raw.categories);
      if (title === null || categories === null) {
        return null;
      }
      const series = parseChartSeries(raw.series, categories.length);
      if (series === null) {
        return null;
      }
      const valueSuffix =
        typeof raw.value_suffix === 'string'
          ? raw.value_suffix.slice(0, 12)
          : null;
      if (raw.type === 'bar_chart') {
        return {
          type: 'bar_chart',
          title,
          categories,
          series,
          stacked: raw.stacked === true,
          valueSuffix,
        };
      }
      return { type: 'line_chart', title, categories, series, valueSuffix };
    }

    case 'table': {
      const title = toShortString(raw.title);
      if (
        title === null ||
        !Array.isArray(raw.headers) ||
        !Array.isArray(raw.rows)
      ) {
        return null;
      }
      const headers = raw.headers
        .slice(0, MAX_TABLE_COLS)
        .map((h) => toCellString(h));
      if (headers.length === 0) {
        return null;
      }
      const rows: string[][] = [];
      for (const rawRow of raw.rows.slice(0, MAX_TABLE_ROWS)) {
        if (!Array.isArray(rawRow)) {
          continue;
        }
        const row = rawRow.slice(0, headers.length).map((c) => toCellString(c));
        // Pad short rows so the table stays rectangular.
        while (row.length < headers.length) {
          row.push('');
        }
        rows.push(row);
      }
      return rows.length > 0 ? { type: 'table', title, headers, rows } : null;
    }

    case 'callout': {
      const text =
        typeof raw.text === 'string' && raw.text.trim()
          ? raw.text.trim().slice(0, MAX_TEXT_LEN)
          : null;
      if (text === null) {
        return null;
      }
      return {
        type: 'callout',
        tone: toTone(raw.tone, 'info'),
        title: toShortString(raw.title),
        text,
      };
    }

    default:
      // Unknown / unsupported block type: dropped (never rendered as raw markup).
      return null;
  }
};

/**
 * Validate and sanitize an untrusted artifact spec (typically
 * `toolInvocation.args.spec`). Returns `null` when the input is unusable.
 */
export const parseArtifactSpec = (raw: unknown): ArtifactSpec | null => {
  if (!isObject(raw)) {
    return null;
  }
  const title = toShortString(raw.title);
  if (title === null || !Array.isArray(raw.blocks)) {
    return null;
  }
  const blocks: ArtifactBlock[] = [];
  for (const rawBlock of raw.blocks.slice(0, MAX_BLOCKS)) {
    const block = parseBlock(rawBlock);
    if (block !== null) {
      blocks.push(block);
    }
  }
  return blocks.length > 0 ? { title, blocks } : null;
};
