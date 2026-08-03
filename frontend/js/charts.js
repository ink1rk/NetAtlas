/**
 * NetAtlas Chart.js helpers
 */
const Charts = (() => {
  const COLORS = {
    accent: '#00B8FF',
    accentDim: 'rgba(0, 184, 255, 0.15)',
    info: '#3B82F6',
    infoDim: 'rgba(59, 130, 246, 0.15)',
    warning: '#FFB300',
    warningDim: 'rgba(255, 179, 0, 0.15)',
    danger: '#FF3D71',
    dangerDim: 'rgba(255, 61, 113, 0.15)',
    success: '#00E676',
    successDim: 'rgba(0, 230, 118, 0.15)',
    muted: '#94A3B8',
    grid: '#1E293B',
    text: '#94A3B8',
    card: '#111827',
  };

  const defaults = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        labels: { color: COLORS.text, font: { family: "'Inter'" } },
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
    const palette = colors || [
      COLORS.accent, COLORS.success, COLORS.warning, COLORS.danger, COLORS.muted,
    ];
    const chart = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{
          data,
          backgroundColor: palette,
          borderColor: COLORS.card,
          borderWidth: 2,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'right',
            labels: { color: COLORS.text, font: { family: "'Inter'" }, padding: 12 },
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
