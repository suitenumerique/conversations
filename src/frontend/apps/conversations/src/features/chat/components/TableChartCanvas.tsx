import {
  ArcElement,
  BarController,
  BarElement,
  CategoryScale,
  ChartData,
  Chart as ChartJS,
  ChartOptions,
  Legend,
  LineController,
  LineElement,
  LinearScale,
  PieController,
  Plugin,
  PointElement,
  SubTitle,
  Title,
  Tooltip,
} from 'chart.js';
import { useEffect, useRef, useState } from 'react';
import { Chart } from 'react-chartjs-2';

import { useCunninghamTheme } from '@/cunningham';
import { TableChartData } from '@/features/chat/utils/tableChart';
import { useResponsiveStore } from '@/stores';

// Controllers too: the generic <Chart> does not register them, and the ones
// react-chartjs-2's typed charts register can be tree-shaken out of a build.
ChartJS.register(
  ArcElement,
  BarController,
  BarElement,
  CategoryScale,
  Legend,
  LineController,
  LineElement,
  LinearScale,
  PieController,
  PointElement,
  SubTitle,
  Title,
  Tooltip,
);

// A categorical data-vis palette, not the theme's brand colors: blue, orange,
// aqua, yellow, magenta, green, violet, red. The order keeps neighbours apart
// for color-blind readers; dark mode has its own steps of the same hues,
// checked against the dark surfaces. Some light steps are under 3:1 on white,
// which is why the "show data" table exists.
const SERIES_COLORS_LIGHT = [
  '#2a78d6',
  '#eb6834',
  '#1baf7a',
  '#eda100',
  '#e87ba4',
  '#008300',
  '#6250d6',
  '#e34948',
];
const SERIES_COLORS_DARK = [
  '#3987e5',
  '#d95926',
  '#199e70',
  '#c98500',
  '#d55181',
  '#008300',
  '#9085e9',
  '#e66767',
];
const DARK_THEMES: readonly string[] = ['dark', 'dsfr-dark'];
// Theme tokens, read at runtime: a canvas does not resolve CSS variables.
const TEXT_COLOR_VAR =
  '--c--contextuals--content--semantic--neutral--secondary';
const GRID_COLOR_VAR = '--c--contextuals--border--semantic--neutral--tertiary';

interface ChartColors {
  series: string[];
  text: string;
  grid: string;
  background: string;
}

const TRANSPARENT = new Set(['', 'transparent', 'rgba(0, 0, 0, 0)']);

/** The color actually painted behind `element`: the first ancestor with a background. */
const backgroundBehind = (element: HTMLElement): string => {
  for (
    let node: HTMLElement | null = element;
    node;
    node = node.parentElement
  ) {
    const color = getComputedStyle(node).backgroundColor;
    if (!TRANSPARENT.has(color)) {
      return color;
    }
  }
  return 'transparent';
};

const readColors = (element: HTMLElement, theme: string): ChartColors => {
  const style = getComputedStyle(element);
  const read = (name: string) => style.getPropertyValue(name).trim();
  return {
    series: DARK_THEMES.includes(theme)
      ? SERIES_COLORS_DARK
      : SERIES_COLORS_LIGHT,
    text: read(TEXT_COLOR_VAR),
    grid: read(GRID_COLOR_VAR),
    background: backgroundBehind(element),
  };
};

const buildData = (
  chart: TableChartData,
  colors: ChartColors,
): ChartData<'bar' | 'line' | 'pie'> => ({
  labels: chart.labels,
  datasets: chart.series.map((series, index) => {
    const color = colors.series[index % colors.series.length];
    return {
      label: series.name,
      data: series.values,
      // A pie has a single series: one color per slice instead.
      backgroundColor:
        chart.type === 'pie'
          ? chart.labels.map(
              (_, slice) => colors.series[slice % colors.series.length],
            )
          : color,
      // Pie slices are split by a gap in the page background, in either theme.
      borderColor: chart.type === 'pie' ? colors.background : color,
    };
  }),
});

const buildOptions = (
  chart: TableChartData,
  colors: ChartColors,
  isMobile: boolean,
): ChartOptions<'bar' | 'line' | 'pie'> => {
  const legend = {
    display: chart.type === 'pie' || chart.series.length > 1,
    labels: { color: colors.text },
  };
  if (chart.type === 'pie') {
    // Beside the pie, it leaves the pie the full height; too narrow on mobile.
    const position = isMobile ? ('top' as const) : ('right' as const);
    return {
      maintainAspectRatio: false,
      plugins: { legend: { ...legend, position } },
    };
  }
  const axis = { ticks: { color: colors.text }, grid: { color: colors.grid } };
  return {
    maintainAspectRatio: false,
    plugins: { legend },
    scales: { x: axis, y: { ...axis, beginAtZero: chart.type === 'bar' } },
  };
};

// Exports are pasted into documents: always light, whatever the theme.
const EXPORT_COLORS: ChartColors = {
  series: SERIES_COLORS_LIGHT,
  text: '#52514e',
  grid: '#e1e0d9',
  background: '#ffffff',
};
const EXPORT_TITLE_COLOR = '#0b0b0b';
const EXPORT_WIDTH = 960;
const EXPORT_HEIGHT = 540;
const EXPORT_PIXEL_RATIO = 2;

// A canvas is transparent: paint the background before the chart.
const exportBackground: Plugin = {
  id: 'exportBackground',
  beforeDraw: ({ ctx, width, height }) => {
    ctx.save();
    ctx.fillStyle = EXPORT_COLORS.background;
    ctx.fillRect(0, 0, width, height);
    ctx.restore();
  },
};

/**
 * The chart as a PNG, with its title, on a white background.
 *
 * Drawn on a canvas of its own, in light colors and at a fixed size, so the
 * image does not depend on the theme or the window.
 */
export interface ChartExportText {
  /** Shown under the title: what the image does not show, such as cut rows. */
  note?: string;
  /** Pie legend entries replacing the plain labels, with values and shares. */
  legendLabels?: string[];
}

export const renderChartPng = (
  chart: TableChartData,
  { note, legendLabels }: ChartExportText = {},
): Promise<Blob> => {
  const canvas = document.createElement('canvas');
  canvas.width = EXPORT_WIDTH;
  canvas.height = EXPORT_HEIGHT;
  const options = buildOptions(chart, EXPORT_COLORS, false);
  const legend = options.plugins?.legend;
  const instance = new ChartJS(canvas, {
    type: chart.type,
    data: buildData(chart, EXPORT_COLORS),
    options: {
      ...options,
      responsive: false,
      animation: false,
      devicePixelRatio: EXPORT_PIXEL_RATIO,
      layout: { padding: 16 },
      plugins: {
        ...options.plugins,
        legend: legendLabels
          ? {
              ...legend,
              labels: {
                ...legend?.labels,
                generateLabels: (instance) =>
                  ChartJS.overrides.pie.plugins.legend.labels
                    .generateLabels(instance)
                    .map((item, index) => ({
                      ...item,
                      text: legendLabels[index] ?? item.text,
                    })),
              },
            }
          : legend,
        subtitle: {
          display: Boolean(note),
          text: note ?? '',
          color: EXPORT_COLORS.text,
          align: 'start',
          padding: { bottom: 16 },
        },
        title: {
          display: true,
          text: chart.title,
          color: EXPORT_TITLE_COLOR,
          align: 'start',
          font: { size: 18, weight: 'bold' },
          padding: { bottom: note ? 4 : 16 },
        },
      },
    },
    plugins: [exportBackground],
  });
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      instance.destroy();
      if (blob) {
        resolve(blob);
      } else {
        reject(new Error('The chart could not be exported.'));
      }
    }, 'image/png');
  });
};

/** Draws the chart on a canvas. Lazy-loaded: Chart.js is fetched with the first chart. */
const TableChartCanvas = ({ chart }: { chart: TableChartData }) => {
  const theme = useCunninghamTheme((state) => state.theme);
  const isMobile = useResponsiveStore((state) => state.isMobile);
  const containerRef = useRef<HTMLDivElement>(null);
  const [colors, setColors] = useState<ChartColors | null>(null);

  useEffect(() => {
    if (containerRef.current) {
      // The app's font (it changes with the theme), here and in exports.
      ChartJS.defaults.font.family = getComputedStyle(
        containerRef.current,
      ).fontFamily;
      setColors(readColors(containerRef.current, theme));
    }
  }, [theme]);

  return (
    <div ref={containerRef} style={{ position: 'relative', height: '320px' }}>
      {colors && (
        <Chart
          type={chart.type}
          data={buildData(chart, colors)}
          options={buildOptions(chart, colors, isMobile)}
          role="img"
          aria-label={chart.title}
        />
      )}
    </div>
  );
};

export default TableChartCanvas;
