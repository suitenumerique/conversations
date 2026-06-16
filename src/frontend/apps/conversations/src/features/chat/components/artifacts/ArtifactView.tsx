import React from 'react';

import { Box, Text } from '@/components';

import {
  ArtifactBlock,
  ArtifactSpec,
  BarChartBlock,
  CalloutBlock,
  LineChartBlock,
  Series,
  StatGridBlock,
  TableBlock,
  Tone,
} from './artifactSchema';

const TONE_COLOR: Record<Tone, string> = {
  neutral: 'var(--c--globals--colors--gray-600)',
  success: 'var(--c--globals--colors--success-600)',
  danger: 'var(--c--globals--colors--error-600)',
  warning: 'var(--c--globals--colors--warning-600)',
  info: 'var(--c--globals--colors--info-600)',
};

const TONE_BG: Record<Tone, string> = {
  neutral: 'var(--c--globals--colors--gray-100)',
  success: 'var(--c--globals--colors--success-100)',
  danger: 'var(--c--globals--colors--error-100)',
  warning: 'var(--c--globals--colors--warning-100)',
  info: 'var(--c--globals--colors--info-100)',
};

// Palette used to auto-assign colors to series that have no explicit tone.
const SERIES_PALETTE = [
  'var(--c--globals--colors--brand-600)',
  'var(--c--globals--colors--info-600)',
  'var(--c--globals--colors--purple-500)',
  'var(--c--globals--colors--success-600)',
  'var(--c--globals--colors--warning-600)',
  'var(--c--globals--colors--error-600)',
];

const seriesColor = (serie: Series, index: number): string =>
  serie.tone
    ? TONE_COLOR[serie.tone]
    : SERIES_PALETTE[index % SERIES_PALETTE.length];

const niceMax = (value: number): number => {
  if (value <= 0) {
    return 1;
  }
  const magnitude = Math.pow(10, Math.floor(Math.log10(value)));
  const normalized = value / magnitude;
  const step =
    normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return step * magnitude;
};

const formatValue = (value: number, suffix: string | null): string => {
  const rounded = Math.round(value * 100) / 100;
  return `${rounded}${suffix ?? ''}`;
};

const ChartLegend: React.FC<{
  series: Series[];
  hidden: ReadonlySet<number>;
  onToggle: (index: number) => void;
}> = ({ series, hidden, onToggle }) => {
  if (series.length < 2) {
    return null;
  }
  return (
    <Box $direction="row" $gap="12px" $css="flex-wrap: wrap; margin-top: 8px;">
      {series.map((serie, index) => {
        const isHidden = hidden.has(index);
        return (
          <button
            key={serie.name}
            type="button"
            onClick={() => onToggle(index)}
            aria-pressed={!isHidden}
            title={
              isHidden ? `Afficher ${serie.name}` : `Masquer ${serie.name}`
            }
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              background: 'none',
              border: 'none',
              padding: 0,
              cursor: 'pointer',
              opacity: isHidden ? 0.4 : 1,
            }}
          >
            <span
              style={{
                width: 10,
                height: 10,
                borderRadius: 2,
                background: seriesColor(serie, index),
                display: 'inline-block',
              }}
            />
            <Text
              $size="xs"
              $theme="greyscale"
              $variation="700"
              $css={isHidden ? 'text-decoration: line-through;' : ''}
            >
              {serie.name}
            </Text>
          </button>
        );
      })}
    </Box>
  );
};

// Local, ephemeral toggle state for hiding/showing chart series via the legend.
const useSeriesToggle = () => {
  const [hidden, setHidden] = React.useState<ReadonlySet<number>>(
    () => new Set<number>(),
  );
  const toggle = React.useCallback((index: number) => {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  }, []);
  return { hidden, toggle };
};

// --- Charts (responsive inline SVG, no external dependency) ----------------

const VIEW_W = 640;
const VIEW_H = 300;
const PAD = { top: 16, right: 16, bottom: 44, left: 44 };
const PLOT_W = VIEW_W - PAD.left - PAD.right;
const PLOT_H = VIEW_H - PAD.top - PAD.bottom;

const AxisGrid: React.FC<{ max: number; suffix: string | null }> = ({
  max,
  suffix,
}) => {
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  return (
    <>
      {ticks.map((ratio) => {
        const y = PAD.top + PLOT_H * (1 - ratio);
        return (
          <g key={ratio}>
            <line
              x1={PAD.left}
              x2={PAD.left + PLOT_W}
              y1={y}
              y2={y}
              stroke="var(--c--globals--colors--gray-200)"
              strokeWidth={1}
            />
            <text
              x={PAD.left - 6}
              y={y + 4}
              textAnchor="end"
              fontSize={11}
              fill="var(--c--globals--colors--gray-600)"
            >
              {formatValue(max * ratio, suffix)}
            </text>
          </g>
        );
      })}
    </>
  );
};

const CategoryLabels: React.FC<{ categories: string[] }> = ({ categories }) => {
  const band = PLOT_W / categories.length;
  return (
    <>
      {categories.map((category, index) => (
        <text
          key={`${category}-${index}`}
          x={PAD.left + band * index + band / 2}
          y={VIEW_H - PAD.bottom + 18}
          textAnchor="middle"
          fontSize={11}
          fill="var(--c--globals--colors--gray-700)"
        >
          {category.length > 12 ? `${category.slice(0, 11)}…` : category}
        </text>
      ))}
    </>
  );
};

const BarChartView: React.FC<{ block: BarChartBlock }> = ({ block }) => {
  const { categories, series, stacked, valueSuffix } = block;
  const { hidden, toggle } = useSeriesToggle();

  // Original indices of the currently-visible series (colors stay stable).
  const visible = series
    .map((_, index) => index)
    .filter((index) => !hidden.has(index));

  const max = stacked
    ? Math.max(
        1,
        ...categories.map((_, ci) =>
          visible.reduce(
            (sum, si) => sum + Math.max(0, series[si].data[ci]),
            0,
          ),
        ),
      )
    : Math.max(
        1,
        ...visible.flatMap((si) => series[si].data.map((v) => Math.max(0, v))),
      );
  const top = niceMax(max);
  const band = PLOT_W / categories.length;

  return (
    <Box>
      <svg
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        style={{ width: '100%', height: 'auto' }}
        role="img"
        aria-label={block.title}
      >
        <AxisGrid max={top} suffix={valueSuffix} />
        {categories.map((_, ci) => {
          const groupX = PAD.left + band * ci;
          if (stacked) {
            let cursorY = PAD.top + PLOT_H;
            const barW = Math.min(band * 0.6, 48);
            const barX = groupX + (band - barW) / 2;
            return (
              <g key={ci}>
                {visible.map((si) => {
                  const s = series[si];
                  const h = (Math.max(0, s.data[ci]) / top) * PLOT_H;
                  cursorY -= h;
                  return (
                    <rect
                      key={si}
                      x={barX}
                      y={cursorY}
                      width={barW}
                      height={h}
                      style={{ fill: seriesColor(s, si) }}
                    >
                      <title>{`${s.name}: ${formatValue(s.data[ci], valueSuffix)}`}</title>
                    </rect>
                  );
                })}
              </g>
            );
          }
          const innerW = band * 0.7;
          const count = Math.max(visible.length, 1);
          const barW = Math.min(innerW / count, 40);
          const startX = groupX + (band - barW * count) / 2;
          return (
            <g key={ci}>
              {visible.map((si, slot) => {
                const s = series[si];
                const h = (Math.max(0, s.data[ci]) / top) * PLOT_H;
                const x = startX + barW * slot;
                const y = PAD.top + PLOT_H - h;
                return (
                  <rect
                    key={si}
                    x={x}
                    y={y}
                    width={Math.max(barW - 2, 1)}
                    height={h}
                    style={{ fill: seriesColor(s, si) }}
                  >
                    <title>{`${s.name}: ${formatValue(s.data[ci], valueSuffix)}`}</title>
                  </rect>
                );
              })}
            </g>
          );
        })}
        <CategoryLabels categories={categories} />
      </svg>
      <ChartLegend series={series} hidden={hidden} onToggle={toggle} />
    </Box>
  );
};

const LineChartView: React.FC<{ block: LineChartBlock }> = ({ block }) => {
  const { categories, series, valueSuffix } = block;
  const { hidden, toggle } = useSeriesToggle();

  const visible = series
    .map((_, index) => index)
    .filter((index) => !hidden.has(index));

  const max = Math.max(
    1,
    ...visible.flatMap((si) => series[si].data.map((v) => Math.max(0, v))),
  );
  const top = niceMax(max);
  const band = PLOT_W / categories.length;
  const pointX = (index: number) => PAD.left + band * index + band / 2;
  const pointY = (value: number) =>
    PAD.top + PLOT_H - (Math.max(0, value) / top) * PLOT_H;

  return (
    <Box>
      <svg
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        style={{ width: '100%', height: 'auto' }}
        role="img"
        aria-label={block.title}
      >
        <AxisGrid max={top} suffix={valueSuffix} />
        {visible.map((si) => {
          const s = series[si];
          const color = seriesColor(s, si);
          const points = s.data
            .map((v, i) => `${pointX(i)},${pointY(v)}`)
            .join(' ');
          return (
            <g key={si}>
              <polyline
                points={points}
                fill="none"
                style={{ stroke: color }}
                strokeWidth={2}
                strokeLinejoin="round"
                strokeLinecap="round"
              />
              {s.data.map((v, i) => (
                <circle
                  key={i}
                  cx={pointX(i)}
                  cy={pointY(v)}
                  r={3}
                  style={{ fill: color }}
                >
                  <title>{`${s.name} · ${categories[i]}: ${formatValue(v, valueSuffix)}`}</title>
                </circle>
              ))}
            </g>
          );
        })}
        <CategoryLabels categories={categories} />
      </svg>
      <ChartLegend series={series} hidden={hidden} onToggle={toggle} />
    </Box>
  );
};

const StatGridView: React.FC<{ block: StatGridBlock }> = ({ block }) => (
  <Box
    $css={`
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap: 12px;
    `}
  >
    {block.items.map((item, index) => (
      <Box
        key={index}
        $direction="column"
        $gap="2px"
        $padding="12px"
        $css="border: 1px solid var(--c--globals--colors--gray-200); border-radius: 8px;"
      >
        <Text $size="xl" $weight="700" style={{ color: TONE_COLOR[item.tone] }}>
          {item.value}
        </Text>
        <Text $size="xs" $theme="greyscale" $variation="600">
          {item.label}
        </Text>
      </Box>
    ))}
  </Box>
);

type SortDir = 'asc' | 'desc';

// Compare two cells numerically when both look numeric, otherwise as locale
// strings. Mirrors what a user expects when sorting a mixed column.
const compareCells = (a: string, b: string): number => {
  const na = Number(a.replace(/\s/g, '').replace(',', '.'));
  const nb = Number(b.replace(/\s/g, '').replace(',', '.'));
  if (Number.isFinite(na) && Number.isFinite(nb)) {
    return na - nb;
  }
  return a.localeCompare(b);
};

const TableView: React.FC<{ block: TableBlock }> = ({ block }) => {
  // Ephemeral sort state: clicking a header cycles asc -> desc -> none.
  const [sort, setSort] = React.useState<{
    col: number;
    dir: SortDir;
  } | null>(null);

  const onSort = (col: number) => {
    setSort((prev) => {
      if (!prev || prev.col !== col) {
        return { col, dir: 'asc' };
      }
      if (prev.dir === 'asc') {
        return { col, dir: 'desc' };
      }
      return null;
    });
  };

  const rows = React.useMemo(() => {
    if (!sort) {
      return block.rows;
    }
    const sorted = [...block.rows].sort((ra, rb) =>
      compareCells(ra[sort.col] ?? '', rb[sort.col] ?? ''),
    );
    return sort.dir === 'desc' ? sorted.reverse() : sorted;
  }, [block.rows, sort]);

  return (
    <Box $css="overflow-x: auto;">
      <table
        style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontSize: 14,
        }}
      >
        <thead>
          <tr>
            {block.headers.map((header, index) => {
              const active = sort?.col === index;
              const caret = active ? (sort?.dir === 'asc' ? ' ▲' : ' ▼') : '';
              return (
                <th
                  key={index}
                  onClick={() => onSort(index)}
                  aria-sort={
                    active
                      ? sort?.dir === 'asc'
                        ? 'ascending'
                        : 'descending'
                      : 'none'
                  }
                  style={{
                    textAlign: 'left',
                    padding: '8px 10px',
                    borderBottom:
                      '1px solid var(--c--globals--colors--gray-300)',
                    color: 'var(--c--globals--colors--gray-700)',
                    fontWeight: 600,
                    whiteSpace: 'nowrap',
                    cursor: 'pointer',
                    userSelect: 'none',
                  }}
                >
                  {header}
                  {caret}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((cell, cellIndex) => (
                <td
                  key={cellIndex}
                  style={{
                    padding: '8px 10px',
                    borderBottom:
                      '1px solid var(--c--globals--colors--gray-200)',
                    color: 'var(--c--globals--colors--gray-900)',
                  }}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </Box>
  );
};

const CalloutView: React.FC<{ block: CalloutBlock }> = ({ block }) => (
  <Box
    $direction="column"
    $gap="4px"
    $padding="12px"
    $css={`
      border-radius: 8px;
      background: ${TONE_BG[block.tone]};
      border-left: 3px solid ${TONE_COLOR[block.tone]};
    `}
  >
    {block.title && (
      <Text $weight="700" $size="sm" style={{ color: TONE_COLOR[block.tone] }}>
        {block.title}
      </Text>
    )}
    <Text
      $size="sm"
      $theme="greyscale"
      $variation="800"
      $css="white-space: pre-wrap;"
    >
      {block.text}
    </Text>
  </Box>
);

const BlockView: React.FC<{ block: ArtifactBlock }> = ({ block }) => {
  switch (block.type) {
    case 'stat_grid':
      return <StatGridView block={block} />;
    case 'bar_chart':
      return <BarChartView block={block} />;
    case 'line_chart':
      return <LineChartView block={block} />;
    case 'table':
      return <TableView block={block} />;
    case 'callout':
      return <CalloutView block={block} />;
    default:
      return null;
  }
};

const blockTitle = (block: ArtifactBlock): string | null =>
  block.type === 'bar_chart' ||
  block.type === 'line_chart' ||
  block.type === 'table'
    ? block.title
    : null;

export const ArtifactView: React.FC<{ spec: ArtifactSpec }> = ({ spec }) => (
  <Box
    $direction="column"
    $gap="16px"
    $padding="16px"
    $margin={{ top: 'base', bottom: 'md' }}
    $css={`
      width: 100%;
      max-width: var(--chat-content-max-width, 750px);
      margin-left: auto;
      margin-right: auto;
      border: 1px solid var(--c--globals--colors--gray-200);
      border-radius: 12px;
    `}
    data-testid="artifact-view"
  >
    <Text $weight="700" $size="lg" $theme="greyscale" $variation="900">
      {spec.title}
    </Text>
    {spec.blocks.map((block, index) => {
      const title = blockTitle(block);
      return (
        <Box key={index} $direction="column" $gap="6px">
          {title && (
            <Text $size="sm" $weight="600" $theme="greyscale" $variation="700">
              {title}
            </Text>
          )}
          <BlockView block={block} />
        </Box>
      );
    })}
  </Box>
);
