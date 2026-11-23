import { Button } from '@gouvfr-lasuite/cunningham-react';
import { Suspense, lazy, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Box, Loader, Text } from '@/components';
import {
  TableChartData,
  chartFileName,
  pieLegendLabels,
} from '@/features/chat/utils/tableChart';

import type { ChartExportText } from './TableChartCanvas';

const TableChartCanvas = lazy(() => import('./TableChartCanvas'));

const downloadPng = async (chart: TableChartData, text: ChartExportText) => {
  // Same chunk as the canvas: Chart.js is already loaded by then.
  const { renderChartPng } = await import('./TableChartCanvas');
  const url = URL.createObjectURL(await renderChartPng(chart, text));
  const link = document.createElement('a');
  link.href = url;
  link.download = chartFileName(chart.title);
  link.click();
  // After the click has started the download.
  setTimeout(() => URL.revokeObjectURL(url));
};

const DATA_TABLE_CSS = `
  border-collapse: collapse;
  font-size: var(--c--globals--font--sizes--sm);
  th, td {
    padding: var(--c--globals--spacings--2xs) var(--c--globals--spacings--xs);
    border-bottom: 1px solid var(--c--contextuals--border--semantic--neutral--tertiary);
    text-align: left;
  }
  td + td, th + th {
    text-align: right;
  }
`;

/**
 * A chart computed by the server from a spreadsheet query, with its values as a
 * table on demand (for screen readers, and to check the numbers).
 *
 * Every label and value comes from a user file: they are only rendered as React
 * text or handed to Chart.js, which draws them on a canvas.
 */
export const TableChart = ({ chart }: { chart: TableChartData }) => {
  const { t, i18n } = useTranslation();
  const [showData, setShowData] = useState(false);
  const [exporting, setExporting] = useState(false);
  const partialNote =
    chart.total > chart.labels.length
      ? t('The chart shows the first {{shown}} of {{total}} rows.', {
          shown: chart.labels.length,
          total: chart.total,
        })
      : undefined;
  const exportImage = () => {
    setExporting(true);
    void downloadPng(chart, {
      note: partialNote,
      legendLabels:
        chart.type === 'pie'
          ? pieLegendLabels(chart, i18n.language)
          : undefined,
    }).finally(() => setExporting(false));
  };
  const formatValue = (value: number | null) =>
    value === null ? '' : value.toLocaleString(i18n.language);

  return (
    <Box
      as="figure"
      $direction="column"
      $gap="8px"
      $width="100%"
      $maxWidth="var(--chat-content-max-width, 750px)"
      $margin={{ all: 'auto', top: 'base', bottom: 'md' }}
    >
      <Text as="figcaption" $weight="700" $size="md">
        {chart.title}
      </Text>
      <Suspense fallback={<Loader />}>
        <TableChartCanvas chart={chart} />
      </Suspense>
      {partialNote && (
        <Text $theme="neutral" $variation="secondary" $size="sm">
          {partialNote}
        </Text>
      )}
      <Box $direction="row">
        <Button
          size="small"
          color="neutral"
          variant="tertiary"
          aria-expanded={showData}
          onClick={() => setShowData((shown) => !shown)}
        >
          {showData ? t('Hide data') : t('Show data')}
        </Button>
        <Button
          size="small"
          color="neutral"
          variant="tertiary"
          disabled={exporting}
          onClick={exportImage}
        >
          {t('Download chart')}
        </Button>
      </Box>
      {showData && (
        // Box is a flex box by default: a table needs table layout so its
        // header and body share the same columns.
        <Box as="table" $display="table" $css={DATA_TABLE_CSS}>
          <thead>
            <tr>
              <th scope="col">{t('Label')}</th>
              {chart.series.map((series, index) => (
                <th scope="col" key={index}>
                  {series.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {chart.labels.map((label, row) => (
              <tr key={row}>
                <th scope="row">{label}</th>
                {chart.series.map((series, index) => (
                  <td key={index}>{formatValue(series.values[row])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </Box>
      )}
    </Box>
  );
};
