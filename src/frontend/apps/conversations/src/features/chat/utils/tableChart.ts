export type TableChartType = 'bar' | 'line' | 'pie';

export interface TableChartSeries {
  name: string;
  values: (number | null)[];
}

/** A chart of a query_table result, computed by the server from the spreadsheet. */
export interface TableChartData {
  type: TableChartType;
  title: string;
  labels: string[];
  series: TableChartSeries[];
  /** Rows in the full result; more than `labels.length` when the result was cut. */
  total: number;
}

const CHART_TYPES: readonly string[] = ['bar', 'line', 'pie'];
// Server caps: 100 result rows, 6 series, 120-char titles, 80-char labels.
const MAX_POINTS = 100;
const MAX_SERIES = 6;
const MAX_TEXT_LENGTH = 200;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const isShortString = (value: unknown): value is string =>
  typeof value === 'string' && value.length <= MAX_TEXT_LENGTH;

const isSeries = (value: unknown, length: number): value is TableChartSeries =>
  isRecord(value) &&
  isShortString(value.name) &&
  Array.isArray(value.values) &&
  value.values.length === length &&
  value.values.every((v) => v === null || Number.isFinite(v));

/**
 * The chart in a query_table output, or null when there is none or it is malformed.
 *
 * The output is saved with the message and replayed when the conversation is
 * reopened, so it is checked again here rather than trusted.
 */
export const parseTableChart = (output: unknown): TableChartData | null => {
  if (!isRecord(output) || !isRecord(output.chart)) {
    return null;
  }
  const { type, title, labels, series, total } = output.chart;
  if (
    typeof type !== 'string' ||
    !CHART_TYPES.includes(type) ||
    !isShortString(title) ||
    !Array.isArray(labels) ||
    labels.length === 0 ||
    labels.length > MAX_POINTS ||
    !labels.every(isShortString) ||
    !Array.isArray(series) ||
    series.length === 0 ||
    series.length > MAX_SERIES ||
    !series.every((s) => isSeries(s, labels.length)) ||
    !Number.isInteger(total) ||
    (total as number) < labels.length
  ) {
    return null;
  }
  return {
    type: type as TableChartType,
    title,
    labels,
    series,
    total: total as number,
  };
};

/** A file name for the exported chart, from its title (which comes from the model). */
export const chartFileName = (title: string): string => {
  const name = title
    .replace(/[^\p{L}\p{N} _-]+/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 80)
    .trim();
  return `${name || 'chart'}.png`;
};

/**
 * Pie legend entries with each slice's value and share, for the exported image,
 * where there is no tooltip to read them from.
 */
export const pieLegendLabels = (
  chart: TableChartData,
  locale: string,
): string[] => {
  const values = chart.series[0].values;
  const total = values.reduce<number>((sum, value) => sum + (value ?? 0), 0);
  const percent = new Intl.NumberFormat(locale, {
    style: 'percent',
    maximumFractionDigits: 1,
  });
  return chart.labels.map((label, index) => {
    const value = values[index];
    if (value === null) {
      return label;
    }
    const share = total > 0 ? ` (${percent.format(value / total)})` : '';
    return `${label}: ${value.toLocaleString(locale)}${share}`;
  });
};
