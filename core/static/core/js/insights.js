/* ============================================================
   Flamingo Fitness - shared "Insights" module (charts + raw data).
   Loaded after dashboard.js and after the Chart.js UMD CDN build
   is present, so window.Chart exists at render time.

   Power, cleanliness, Duolingo theme:
     window.FFInsights.createInsights(containerEl, modality, data)
   appends a segmented "Graph / Raw data" tab block to any skill-tree
   panel. Ranges (7D/2W/1M/3M/All) filter the ALREADY-fetched history
   client-side so switching is instant and offline-friendly.
   ============================================================ */
(function () {
    'use strict';

    function getChartJS() {
        if (typeof window !== 'undefined' && window.Chart) {
            return window.Chart;
        }
        return null;
    }

    function isoDate(offsetDays) {
        var d = new Date();
        if (offsetDays) d.setDate(d.getDate() - offsetDays);
        var m = String(d.getMonth() + 1).padStart(2, '0');
        var day = String(d.getDate()).padStart(2, '0');
        return d.getFullYear() + '-' + m + '-' + day;
    }

    function hexToRgba(hex, alpha) {
        if (/^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(hex)) {
            var h = hex.replace('#', '');
            if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
            var num = parseInt(h, 16);
            var r = (num >> 16) & 255, g = (num >> 8) & 255, b = num & 255;
            return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
        }
        return 'rgba(148,163,184,' + alpha + ')';
    }

    function mixTowardWhite(hex, amt) {
        if (!/^#[0-9a-fA-F]{6}$/.test(hex)) return hex;
        var num = parseInt(hex.replace('#', ''), 16);
        var r = (num >> 16) & 255, g = (num >> 8) & 255, b = num & 255;
        r = Math.round(r + (255 - r) * amt);
        g = Math.round(g + (255 - g) * amt);
        b = Math.round(b + (255 - b) * amt);
        return '#' + r.toString(16).padStart(2, '0') + g.toString(16).padStart(2, '0') + b.toString(16).padStart(2, '0');
    }

    // ------------------------------------------------------------------
    // Per-modality configuration (Duolingo neon accents).
    // ------------------------------------------------------------------
    var RANGES = [
        { label: '1W', days: 7 },
        { label: '2W', days: 14 },
        { label: '1M', days: 30 },
        { label: '3M', days: 90 },
        { label: 'All', days: 0 }
    ];

    var CFG = {
        hydration: {
            label: 'Hydration',
            icon: 'fa-glass-water',
            accent: '#38bdf8',
            unit: 'oz',
            chart: {
                series: [{
                    key: 'water', label: 'Water', color: '#38bdf8',
                    goalKey: 'water_goal', goalLabel: 'Target'
                }]
            },
            summary: [
                { key: 'water', label: 'Avg', stat: 'avg', unit: 'oz', color: '#38bdf8' },
                { key: 'water', label: 'Best', stat: 'max', unit: 'oz', color: '#a5f3fc' },
                { key: null, label: 'On target', stat: 'good', color: '#4ade80' }
            ],
            rawColumns: [
                { key: 'water', label: 'Water', unit: 'oz', color: '#38bdf8' },
                { key: 'water_goal', label: 'Goal', unit: 'oz' },
                { key: 'water_pct', label: 'Pct', suffix: '%' },
                { key: 'perfect', label: 'Target', kind: 'bool' },
                { key: 'xp', label: 'XP', kind: 'xp' }
            ],
            goodDay: function (d) { return !!d.perfect; }
        },

        nutrition: {
            label: 'Nutrition',
            icon: 'fa-apple-whole',
            accent: '#a78bfa',
            chart: {
                dualAxis: true,
                series: [
                    {
                        key: 'protein', label: 'Protein', color: '#a78bfa',
                        goalKey: 'protein_goal', goalLabel: 'Protein goal', unit: 'g'
                    },
                    {
                        key: 'calories', label: 'Calories', color: '#f87171',
                        goalKey: 'calorie_goal', goalLabel: 'Calorie cap', unit: 'cal'
                    }
                ]
            },
            summary: [
                { key: 'protein', label: 'Avg protein', stat: 'avg', unit: 'g', color: '#a78bfa' },
                { key: 'calories', label: 'Avg calories', stat: 'avg', unit: 'cal', color: '#f87171' },
                { key: null, label: 'Perfect', stat: 'good', color: '#4ade80' }
            ],
            rawColumns: [
                { key: 'protein', label: 'Protein', unit: 'g', color: '#a78bfa' },
                { key: 'protein_goal', label: 'P goal', unit: 'g' },
                { key: 'calories', label: 'Calories', unit: 'cal', color: '#f87171' },
                { key: 'calorie_goal', label: 'C cap', unit: 'cal' },
                { key: 'perfect', label: 'Perfect', kind: 'bool' },
                { key: 'xp', label: 'XP', kind: 'xp' }
            ],
            goodDay: function (d) { return !!d.perfect; }
        },
        endurance: {
            label: 'Endurance',
            icon: 'fa-bicycle',
            accent: '#60a5fa',
            chart: {
                dualAxis: true,
                series: [
                    {
                        key: 'total_calories_burned', label: 'Calories burned',
                        color: '#60a5fa', unit: 'kcal'
                    },
                    {
                        key: 'total_duration_minutes', label: 'Duration',
                        color: '#2dd4bf', unit: 'min'
                    }
                ]
            },
            summary: [
                { key: 'total_calories_burned', label: 'Avg kcal', stat: 'avg', unit: 'kcal', color: '#60a5fa' },
                { key: 'total_duration_minutes', label: 'Avg min', stat: 'avg', unit: 'min', color: '#2dd4bf' },
                { key: null, label: 'Active days', stat: 'good', color: '#4ade80' }
            ],
            rawColumns: [
                { key: 'total_calories_burned', label: 'Calories', unit: 'kcal', color: '#60a5fa' },
                { key: 'total_duration_minutes', label: 'Minutes', unit: 'min', color: '#2dd4bf' },
                { key: 'exercise_count', label: 'Workouts', kind: 'int' },
                { key: 'xp', label: 'XP', kind: 'xp' }
            ],
            goodDay: function (d) { return (d.xp || 0) > 0; }
        },

        strength: {
            label: 'Strength',
            icon: 'fa-dumbbell',
            accent: '#a78bfa',
            chart: {
                dualAxis: true,
                series: [
                    {
                        key: 'total_volume_lbs', label: 'Volume',
                        color: '#a78bfa', unit: 'lbs'
                    },
                    {
                        key: 'duration_minutes', label: 'Session',
                        color: '#f472b6', unit: 'min'
                    }
                ]
            },
            summary: [
                { key: 'total_volume_lbs', label: 'Avg volume', stat: 'avg', unit: 'lbs', color: '#a78bfa' },
                { key: 'duration_minutes', label: 'Avg min', stat: 'avg', unit: 'min', color: '#f472b6' },
                { key: null, label: 'Workout days', stat: 'good', color: '#4ade80' }
            ],
            rawColumns: [
                { key: 'total_volume_lbs', label: 'Volume', unit: 'lbs', color: '#a78bfa' },
                { key: 'duration_minutes', label: 'Minutes', unit: 'min', color: '#f472b6' },
                { key: 'total_sets', label: 'Sets', kind: 'int' },
                { key: 'pr', label: 'PR', kind: 'bool' },
                { key: 'xp', label: 'XP', kind: 'xp' }
            ],
            goodDay: function (d) { return (d.xp || 0) > 0; }
        },

        recovery: {
            label: 'Recovery',
            icon: 'fa-bed',
            accent: '#818cf8',
            unit: 'h',
            chart: {
                series: [{
                    key: 'sleep_hours', label: 'Sleep', color: '#818cf8',
                    goalValue: 8, goalLabel: '8h target', unit: 'h'
                }]
            },
            summary: [
                { key: 'sleep_hours', label: 'Avg', stat: 'avg', unit: 'h', color: '#818cf8' },
                { key: 'sleep_hours', label: 'Best', stat: 'max', unit: 'h', color: '#c7d2fe' },
                { key: null, label: '8h+ nights', stat: 'good', color: '#4ade80' }
            ],
            rawColumns: [
                { key: 'sleep_hours', label: 'Sleep', unit: 'h', color: '#818cf8' },
                { key: 'deep_pct', label: 'Deep', suffix: '%' },
                { key: 'rem_pct', label: 'REM', suffix: '%' },
                { key: 'xp', label: 'XP', kind: 'xp' }
            ],
            goodDay: function (d) { return (d.sleep_hours || 0) >= 8; }
        }
    };
    // ------------------------------------------------------------------
    // Range + aggregation helpers (history arrives newest-first).
    // ------------------------------------------------------------------
    function filterByRange(history, days) {
        if (!days || days <= 0) return history.slice();
        var cutoff = isoDate(days);
        return history.filter(function (d) { return (d.date || '') >= cutoff; });
    }

    function chronological(rows) {
        return rows.slice().sort(function (a, b) {
            return (a.date || '') < (b.date || '') ? -1 : 1;
        });
    }

    function num(v) {
        var n = parseFloat(v);
        return isFinite(n) ? n : null;
    }

    function avgValues(rows, key) {
        var sum = 0, count = 0;
        rows.forEach(function (d) {
            var n = num(d[key]);
            if (n !== null) { sum += n; count += 1; }
        });
        return count ? sum / count : null;
    }

    function maxValue(rows, key) {
        var best = null;
        rows.forEach(function (d) {
            var n = num(d[key]);
            if (n !== null && (best === null || n > best)) best = n;
        });
        return best;
    }

    function formatNum(n, unit, opts) {
        if (n === null || n === undefined) return '\u2014';
        opts = opts || {};
        var v = Math.round(n * 10) / 10;
        var out = opts.int ? String(Math.round(v)) : String(v);
        return out + (unit ? ' ' + unit : '');
    }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    function buildSummaryChips(cfg, rows) {
        var wrap = el('div', 'insights-summary');
        cfg.summary.forEach(function (m) {
            var chip = el('div', 'insights-chip');
            var value, label = m.label;
            if (m.stat === 'avg') {
                value = formatNum(avgValues(rows, m.key), m.unit, { int: true });
            } else if (m.stat === 'max') {
                value = formatNum(maxValue(rows, m.key), m.unit);
            } else {
                var g = rows.filter(cfg.goodDay).length;
                value = g + '/' + rows.length;
            }
            var dot = el('span', 'insights-dot');
            if (m.color) dot.style.background = m.color;
            chip.appendChild(dot);
            var inner = el('div', 'insights-chip-text');
            inner.appendChild(el('div', 'insights-chip-value', value));
            inner.appendChild(el('div', 'insights-chip-label', label));
            chip.appendChild(inner);
            wrap.appendChild(chip);
        });
        return wrap;
    }

    function buildChart(canvas, cfg, rows) {
        var ChartJS = getChartJS();
        if (!ChartJS) {
            if (canvas.parentNode) {
                var existingMsg = canvas.parentNode.querySelector('.insights-chart-loading');
                if (!existingMsg) {
                    var msg = el('div', 'insights-note insights-chart-loading', 'Loading chart...');
                    canvas.parentNode.insertBefore(msg, canvas);
                    canvas.style.display = 'none';

                    var pollCount = 0;
                    var timer = setInterval(function () {
                        pollCount++;
                        if (getChartJS()) {
                            clearInterval(timer);
                            if (msg.parentNode) msg.parentNode.removeChild(msg);
                            canvas.style.display = '';
                            buildChart(canvas, cfg, rows);
                        } else if (pollCount > 40) {
                            clearInterval(timer);
                            msg.textContent = 'Chart library not available \u2014 try reloading.';
                        }
                    }, 100);
                }
            }
            return null;
        }

        if (canvas.parentNode) {
            var oldMsg = canvas.parentNode.querySelector('.insights-chart-loading');
            if (oldMsg && oldMsg.parentNode) oldMsg.parentNode.removeChild(oldMsg);
        }
        canvas.style.display = '';
        var asc = chronological(rows);
        var labels = asc.map(function (d) { return d.date || '\u2014'; });
        var perfectArr = asc.map(function (d) { return cfg.goodDay(d); });

        var dualAxis = !!(cfg.chart && cfg.chart.dualAxis && cfg.chart.series.length > 1);
        var datasets = [];
        cfg.chart.series.forEach(function (s, idx) {
            var values = asc.map(function (d) { return num(d[s.key]) || 0; });
            var single = cfg.chart.series.length === 1;
            var bg = values.map(function (_, i) {
                var on = single || perfectArr[i];
                return hexToRgba(s.color, on ? 0.95 : 0.38);
            });
            var yAxisID = dualAxis ? (idx === 0 ? 'y' : 'y1') : 'y';
            datasets.push({
                label: s.label + (s.unit ? ' (' + s.unit + ')' : ''),
                data: values,
                type: 'bar',
                yAxisID: yAxisID,
                backgroundColor: bg,
                hoverBackgroundColor: hexToRgba(mixTowardWhite(s.color, 0.15), 0.98),
                borderColor: hexToRgba(s.color, 0.9),
                borderWidth: 1,
                borderRadius: idx === 1 ? 6 : 9,
                maxBarThickness: 30,
                order: 2
            });

            var goalKeep = asc.map(function (d) {
                var g;
                if (s.goalValue != null) g = s.goalValue;
                else if (s.goalKey != null) g = (d[s.goalKey] != null) ? num(d[s.goalKey]) : null;
                else g = null;
                return g;
            });
            if (goalKeep.some(function (g) { return g !== null; })) {
                datasets.push({
                    label: s.goalLabel || 'Goal',
                    data: goalKeep,
                    type: 'line',
                    yAxisID: yAxisID,
                    borderColor: hexToRgba(mixTowardWhite(s.color, 0.4), 0.95),
                    borderWidth: 2,
                    borderDash: [6, 5],
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    fill: false,
                    tension: 0.25,
                    order: 1
                });
            }
        });

        var s0 = cfg.chart.series[0];
        var s1 = cfg.chart.series[1];
        var chartScales = {
            x: {
                grid: { display: false },
                ticks: { color: '#94a3b8', maxTicksLimit: 8, font: { family: 'Nunito', weight: '700' } }
            },
            y: {
                type: 'linear',
                display: true,
                position: 'left',
                beginAtZero: true,
                grid: { color: 'rgba(148,163,184,0.12)' },
                ticks: {
                    color: (dualAxis && s0) ? s0.color : '#94a3b8',
                    font: { family: 'Nunito', weight: '700' },
                    callback: function (value) {
                        if (dualAxis && s0 && s0.unit) {
                            return value >= 1000 ? (value / 1000).toFixed(1) + 'k' : value + (s0.unit === 'g' ? 'g' : '');
                        }
                        return value >= 1000 ? (value / 1000).toFixed(1) + 'k' : value;
                    }
                },
                title: (dualAxis && s0) ? {
                    display: true,
                    text: s0.label + (s0.unit ? ' (' + s0.unit + ')' : ''),
                    color: s0.color,
                    font: { family: 'Nunito', weight: '800', size: 10 }
                } : undefined
            }
        };

        if (dualAxis && s1) {
            chartScales.y1 = {
                type: 'linear',
                display: true,
                position: 'right',
                beginAtZero: true,
                grid: { drawOnChartArea: false },
                ticks: {
                    color: s1.color,
                    font: { family: 'Nunito', weight: '700' },
                    callback: function (value) {
                        if (s1.unit) {
                            return value >= 1000 ? (value / 1000).toFixed(1) + 'k' : value + (s1.unit === 'g' ? 'g' : '');
                        }
                        return value >= 1000 ? (value / 1000).toFixed(1) + 'k' : value;
                    }
                },
                title: {
                    display: true,
                    text: s1.label + (s1.unit ? ' (' + s1.unit + ')' : ''),
                    color: s1.color,
                    font: { family: 'Nunito', weight: '800', size: 10 }
                }
            };
        }

        return new ChartJS(canvas.getContext('2d'), {
            type: 'bar',
            data: { labels: labels, datasets: datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                animation: { duration: 350, easing: 'easeOutQuart' },
                plugins: {
                    legend: {
                        display: true,
                        position: 'bottom',
                        labels: {
                            color: '#cbd5e1', boxWidth: 10, boxHeight: 10,
                            padding: 14,
                            font: { family: 'Nunito', weight: '700', size: 11 }
                        }
                    },
                    tooltip: {
                        mode: 'index', intersect: false,
                        backgroundColor: 'rgba(15,23,42,0.96)',
                        titleColor: '#f8fafc', bodyColor: '#cbd5e1',
                        padding: 12, cornerRadius: 12, displayColors: true,
                        boxWidth: 8, boxHeight: 8,
                        titleFont: { family: 'Nunito', weight: '800' },
                        bodyFont: { family: 'Nunito', weight: '700' }
                    }
                },
                scales: chartScales
            }
        });
    }

    function fmtCell(v, kind, unit, suffix) {
        if (kind === 'bool') return v ? '\u2713' : '\u2014';
        var n = num(v);
        if (n === null) return '\u2014';
        if (kind === 'xp') return '+' + Math.round(n) + ' XP';
        var out = String(Math.round(n * 10) / 10);
        if (kind === 'int') out = String(Math.round(n));
        if (unit) out += ' ' + unit;
        if (suffix) out += suffix;
        return out;
    }

    function buildRawSection(container, cfg, rows) {
        var asc = chronological(rows).slice().reverse(); // newest first
        var headBtn = el('button', 'raw-export-btn', '\u2B07 Download JSON');
        headBtn.type = 'button';
        headBtn.setAttribute('aria-label', 'Download this range as JSON');
        headBtn.addEventListener('click', function () {
            var blob = new Blob([JSON.stringify(asc, null, 2)], { type: 'application/json' });
            var url = URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = url;
            a.download = cfg.kebab + '-raw.json';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            setTimeout(function () { URL.revokeObjectURL(url); }, 400);
        });
        container.appendChild(headBtn);

        var table = el('table', 'raw-table');
        var thead = el('thead');
        var htr = el('tr');
        htr.appendChild(el('th', '', 'Date'));
        cfg.rawColumns.forEach(function (c) { htr.appendChild(el('th', '', c.label)); });
        htr.appendChild(el('th', '', ''));
        thead.appendChild(htr);
        table.appendChild(thead);

        var tbody = el('tbody');
        asc.forEach(function (d) {
            var tr = el('tr', 'raw-row');
            tr.appendChild(el('td', 'raw-date', d.date || '\u2014'));
            cfg.rawColumns.forEach(function (c) {
                var td = el('td');
                if (c.color) td.style.color = c.color;
                td.textContent = fmtCell(d[c.key], c.kind, c.unit, c.suffix);
                tr.appendChild(td);
            });
            var toggleTd = el('td');
            var btn = el('button', 'raw-toggle', '\u203A');
            btn.type = 'button';
            btn.setAttribute('aria-label', 'Toggle raw JSON for ' + (d.date || 'day'));
            toggleTd.appendChild(btn);
            tr.appendChild(toggleTd);
            tbody.appendChild(tr);

            var preWrap = el('div', 'raw-json hidden');
            preWrap.textContent = JSON.stringify(d.raw_payload || d, null, 2);
            btn.addEventListener('click', function () {
                var open = preWrap.classList.toggle('hidden');
                btn.classList.toggle('open', !open);
            });
            tbody.appendChild(preWrap);
        });
        table.appendChild(tbody);
        container.appendChild(table);
    }
    // ------------------------------------------------------------------
    // Public entry point.
    // ------------------------------------------------------------------
    window.FFInsights = {
        createInsights: function (container, modality, data) {
            if (!container) return;
            var cfg = CFG[modality];
            var history = (data && data.history) || [];
            if (!cfg || !history.length) return;
            cfg.kebab = modality;

            var box = el('div', 'insights-box');

            // Segmented Duolingo-style tab bar.
            var tabs = el('div', 'insights-tabs');
            var tabChart = el('button', 'insights-tab active', '\u{1F4C8} Graph');
            var tabRaw = el('button', 'insights-tab', '\u{1F9EE} Raw data');
            tabChart.type = 'button';
            tabRaw.type = 'button';
            tabs.appendChild(tabChart);
            tabs.appendChild(tabRaw);
            box.appendChild(tabs);

            // Chart section.
            var chartSection = el('div', 'insights-section insights-chart-section');
            var toolbar = el('div', 'insights-toolbar');
            var chipsWrap = el('div', 'insights-range');
            var activeRange = RANGES[RANGES.length - 1];
            RANGES.forEach(function (r) {
                var chip = el('button', 'insights-range-chip' + (r.days === 0 ? ' active' : ''), r.label);
                chip.type = 'button';
                chip.addEventListener('click', function () {
                    Array.prototype.forEach.call(chipsWrap.querySelectorAll('.insights-range-chip'), function (c) {
                        c.classList.remove('active');
                    });
                    chip.classList.add('active');
                    activeRange = r;
                    renderChart();
                });
                chipsWrap.appendChild(chip);
            });
            toolbar.appendChild(chipsWrap);

            var chartCard = el('div', 'insights-chart-card');
            var canvasWrap = el('div', 'insights-chart-wrap');
            var canvas = el('canvas');
            canvas.setAttribute('aria-label', cfg.label + ' chart');
            canvasWrap.appendChild(canvas);
            chartCard.appendChild(canvasWrap);
            var summarySlot = el('div', 'insights-summary-slot');
            chartSection.appendChild(toolbar);
            chartSection.appendChild(summarySlot);
            chartSection.appendChild(chartCard);
            box.appendChild(chartSection);

            // Raw section (hidden by default).
            var rawSection = el('div', 'insights-section insights-raw-section hidden');
            box.appendChild(rawSection);

            var chartInstance = null;
            function renderChart() {
                var rows = filterByRange(history, activeRange.days);
                summarySlot.innerHTML = '';
                if (!rows.length) {
                    summarySlot.appendChild(el('div', 'insights-note', 'No data in this range \u2014 try a wider window.'));
                    if (chartInstance) { chartInstance.destroy(); chartInstance = null; }
                    canvas.style.display = 'none';
                    return;
                }
                canvas.style.display = '';
                summarySlot.appendChild(buildSummaryChips(cfg, rows));
                if (chartInstance) chartInstance.destroy();
                chartInstance = buildChart(canvas, cfg, rows);
            }

            function renderRaw() {
                rawSection.innerHTML = '';
                var rows = filterByRange(history, activeRange.days);
                if (!rows.length) {
                    rawSection.appendChild(el('div', 'insights-note', 'No data in this range.'));
                    return;
                }
                buildRawSection(rawSection, cfg, rows);
            }

            function activate(tab, section) {
                Array.prototype.forEach.call(tabs.querySelectorAll('.insights-tab'), function (t) {
                    t.classList.remove('active');
                });
                tab.classList.add('active');
                chartSection.classList.add('hidden');
                rawSection.classList.add('hidden');
                section.classList.remove('hidden');
                if (section === chartSection) renderChart();
                else renderRaw();
            }

            tabChart.addEventListener('click', function () { activate(tabChart, chartSection); });
            tabRaw.addEventListener('click', function () { activate(tabRaw, rawSection); });

            container.appendChild(box);
            renderChart(); // default view is the graph
        }
    };
})();




