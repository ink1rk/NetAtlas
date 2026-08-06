/**
 * NetAtlas Chart.js helpers
 */
const Charts = (() => {
  const COLORS = {
    accent: '#29B6FF',
    accentDim: 'rgba(41, 182, 255, 0.15)',
    info: '#4C9AFF',
    infoDim: 'rgba(76, 154, 255, 0.15)',
    warning: '#FBB03B',
    warningDim: 'rgba(251, 176, 59, 0.15)',
    danger: '#FB5B78',
    dangerDim: 'rgba(251, 91, 120, 0.15)',
    success: '#34D399',
    successDim: 'rgba(52, 211, 153, 0.15)',
    muted: '#8B99B0',
    grid: '#1C2536',
    text: '#8B99B0',
    card: '#0D1220',
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
