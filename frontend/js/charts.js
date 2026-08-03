/**
 * NetAtlas Chart.js helpers
 */
const Charts = (() => {
  const COLORS = {
    accent: '#00c9a7',
    accentDim: 'rgba(0, 201, 167, 0.15)',
    info: '#3b9eff',
    infoDim: 'rgba(59, 158, 255, 0.15)',
    warning: '#f0a030',
    warningDim: 'rgba(240, 160, 48, 0.15)',
    danger: '#f05252',
    muted: '#7d8fa6',
    grid: '#2a384c',
    text: '#7d8fa6',
  };

  const defaults = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        labels: { color: COLORS.text, font: { family: "'IBM Plex Sans'" } },
      },
    },
    scales: {
      x: {
        ticks: { color: COLORS.text },
        grid: { color: COLORS.grid },
      },
      y: {
        ticks: { color: COLORS.text },
        grid: { color: COLORS.grid },
      },
    },
  };

  const instances = [];

  function destroyAll() {
    instances.forEach((c) => c.destroy());
    instances.length = 0;
  }

  function lineChart(canvas, labels, datasets, opts = {}) {
    const ctx = typeof canvas === 'string' ? document.getElementById(canvas) : canvas;
    if (!ctx) return null;
    const chart = new Chart(ctx, {
      type: 'line',
      data: { labels, datasets },
      options: { ...defaults, ...opts },
    });
    instances.push(chart);
    return chart;
  }

  function doughnutChart(canvas, labels, data, colors) {
    const ctx = typeof canvas === 'string' ? document.getElementById(canvas) : canvas;
    if (!ctx) return null;
    const palette = colors || [COLORS.accent, COLORS.info, COLORS.warning, COLORS.danger, COLORS.muted];
    const chart = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{
          data,
          backgroundColor: palette,
          borderColor: '#141c27',
          borderWidth: 2,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'right',
            labels: { color: COLORS.text, font: { family: "'IBM Plex Sans'" }, padding: 12 },
          },
        },
      },
    });
    instances.push(chart);
    return chart;
  }

  function barChart(canvas, labels, datasets, opts = {}) {
    const ctx = typeof canvas === 'string' ? document.getElementById(canvas) : canvas;
    if (!ctx) return null;
    const chart = new Chart(ctx, {
      type: 'bar',
      data: { labels, datasets },
      options: { ...defaults, ...opts },
    });
    instances.push(chart);
    return chart;
  }

  return { lineChart, doughnutChart, barChart, destroyAll, COLORS };
})();
