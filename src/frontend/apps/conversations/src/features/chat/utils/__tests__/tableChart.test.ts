import { chartFileName, parseTableChart, pieLegendLabels } from '../tableChart';

const CHART = {
  type: 'bar',
  title: 'Sales per region',
  labels: ['Nord', 'Sud'],
  series: [{ name: 'montant_sum', values: [1002, null] }],
  total: 2,
};

describe('parseTableChart', () => {
  it('returns the chart of a valid output', () => {
    expect(parseTableChart({ chart: CHART })).toEqual(CHART);
  });

  it.each([
    ['no output', undefined],
    ['an output without chart', 'Some markdown table'],
    ['an unknown type', { chart: { ...CHART, type: 'scatter' } }],
    ['a non-string label', { chart: { ...CHART, labels: ['Nord', 3] } }],
    ['no labels', { chart: { ...CHART, labels: [], series: [] } }],
    [
      'values not matching the labels',
      { chart: { ...CHART, series: [{ name: 'a', values: [1] }] } },
    ],
    [
      'a non-numeric value',
      { chart: { ...CHART, series: [{ name: 'a', values: [1, '2'] }] } },
    ],
    [
      'an infinite value',
      { chart: { ...CHART, series: [{ name: 'a', values: [1, Infinity] }] } },
    ],
    [
      'too many series',
      {
        chart: {
          ...CHART,
          series: Array.from({ length: 7 }, () => ({
            name: 'a',
            values: [1, 2],
          })),
        },
      },
    ],
    ['a total below the row count', { chart: { ...CHART, total: 1 } }],
    ['a too long title', { chart: { ...CHART, title: 'x'.repeat(201) } }],
  ])('rejects %s', (_case, output) => {
    expect(parseTableChart(output)).toBeNull();
  });
});

describe('chartFileName', () => {
  it.each([
    ['Consommation de GNC par région', 'Consommation de GNC par région.png'],
    ['Sales: 2024/2025 (€)', 'Sales 2024 2025.png'],
    ['../../etc/passwd', 'etc passwd.png'],
    ['???', 'chart.png'],
    ['x'.repeat(100), `${'x'.repeat(80)}.png`],
  ])('turns %j into %j', (title, fileName) => {
    expect(chartFileName(title)).toBe(fileName);
  });
});

describe('pieLegendLabels', () => {
  const PIE = {
    type: 'pie' as const,
    title: 'Per region',
    labels: ['Nord', 'Sud', 'Est'],
    series: [{ name: 'n', values: [1500, 500, null] }],
    total: 3,
  };

  it('adds the value and the share of the total to each label', () => {
    expect(pieLegendLabels(PIE, 'en')).toEqual([
      'Nord: 1,500 (75%)',
      'Sud: 500 (25%)',
      'Est',
    ]);
  });

  it('formats numbers for the language', () => {
    // French: narrow no-break space between thousands, no-break space before %.
    expect(pieLegendLabels(PIE, 'fr')[0]).toBe('Nord: 1\u202f500 (75\u00a0%)');
  });

  it('gives no share when the total is zero', () => {
    const empty = { ...PIE, series: [{ name: 'n', values: [0, 0, 0] }] };

    expect(pieLegendLabels(empty, 'en')).toEqual([
      'Nord: 0',
      'Sud: 0',
      'Est: 0',
    ]);
  });
});
