/**
 * Flamingo Fitness - BioStream Pulse Controller (timeline.js)
 * -----------------------------------------------------------
 * Interactive metabolic timeline showing vitality vs physiological decay over time.
 * Features:
 * - Vertical inverted time river: Top is Current Time, Bottom is Midnight (00:00).
 * - Horizontal polarity axis: Center is 0 (neutral), Right is Vitality (+), Left is Decay (-).
 * - Continuous cubic Bezier physiological flow curve with exponential metabolic decay.
 * - 5 Signature Color Channels: Sleep (#818CF8), Food (#F59E0B), Water (#06B6D4), Strength (#F43F5E), Cardio (#10B981).
 * - Touch & cursor interactive scrubber HUD with dynamic time/vitality readout.
 * - 1-tap interactive drilldown modal with itemized sets, reps, macros & XP.
 */
(function () {
    'use strict';

    // 5 Specified Color Signatures and Configurations
    var CATEGORIES = {
        sleep: {
            id: 'sleep',
            label: 'Sleep',
            color: '#818CF8', // Indigo
            bgClass: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/30',
            glowColor: 'rgba(129, 140, 248, 0.4)',
            icon: 'fa-moon',
            desc: 'Rest, REM cycles & neural repair'
        },
        food: {
            id: 'food',
            label: 'Food',
            color: '#F59E0B', // Amber
            bgClass: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
            glowColor: 'rgba(245, 158, 11, 0.4)',
            icon: 'fa-utensils',
            desc: 'Fuel, glycemic balance & nutrition'
        },
        water: {
            id: 'water',
            label: 'Water',
            color: '#06B6D4', // Cyan
            bgClass: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30',
            glowColor: 'rgba(6, 182, 212, 0.4)',
            icon: 'fa-droplet',
            desc: 'Cellular hydration & electrolyte pool'
        },
        strength: {
            id: 'strength',
            label: 'Strength',
            color: '#F43F5E', // Rose
            bgClass: 'bg-rose-500/10 text-rose-400 border-rose-500/30',
            glowColor: 'rgba(244, 63, 94, 0.4)',
            icon: 'fa-dumbbell',
            desc: 'Muscular loading, strain & hypertrophy'
        },
        cardio: {
            id: 'cardio',
            label: 'Cardio',
            color: '#10B981', // Emerald
            bgClass: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
            glowColor: 'rgba(16, 185, 129, 0.4)',
            icon: 'fa-fire',
            desc: 'Aerobic output, VO2 capacity & endurance'
        }
    };

    window._timelineState = {
        filter: 'all',
        days: 14,
        data: null,
        eventsById: {},
        points: [],
        currentNowMin: 1080
    };

    // ------------------------------------------------------------------
    // Router / Panel Loader entry point
    // ------------------------------------------------------------------
    window.loadTimeline = function () {
        function runLoad() {
            if (typeof window.ensureSinglePanelVisible === 'function') {
                window.ensureSinglePanelVisible('timeline-view');
            }
            if (typeof window.setActiveNav === 'function') {
                window.setActiveNav('nav-timeline');
            }
            fetchTimelineData(window._timelineState.filter, window._timelineState.days);
        }

        if (typeof window.ensurePanelLoaded === 'function') {
            return window.ensurePanelLoaded('timeline-view').then(runLoad);
        } else {
            runLoad();
        }
    };

    window.filterTimeline = function (category) {
        window._timelineState.filter = category;
        var pills = document.querySelectorAll('.timeline-filter-pill');
        pills.forEach(function (pill) {
            pill.classList.toggle('active', pill.getAttribute('data-filter') === category);
        });
        fetchTimelineData(category, window._timelineState.days);
    };

    window.onTimelineDaysChange = function (days) {
        window._timelineState.days = parseInt(days, 10) || 14;
        fetchTimelineData(window._timelineState.filter, window._timelineState.days);
    };

    function fetchTimelineData(category, days) {
        var loadingEl = document.getElementById('timeline-loading');
        var streamEl = document.getElementById('timeline-stream');
        var emptyEl = document.getElementById('timeline-empty');

        if (loadingEl) loadingEl.classList.remove('hidden');
        if (streamEl) streamEl.classList.add('hidden');
        if (emptyEl) emptyEl.classList.add('hidden');

        var url = '/api/v1/timeline/?category=' + encodeURIComponent(category || 'all') +
                  '&days=' + encodeURIComponent(days || 14);

        fetch(url, { credentials: 'same-origin' })
            .then(function (res) {
                if (!res.ok) throw new Error('Timeline fetch error: ' + res.status);
                return res.json();
            })
            .then(function (data) {
                window._timelineState.data = data;
                renderTimeline(data);
            })
            .catch(function (err) {
                window.ffWarn && window.ffWarn('[Timeline] fetch error:', err);
                if (loadingEl) loadingEl.classList.add('hidden');
                if (emptyEl) emptyEl.classList.remove('hidden');
            });
    }

    // ------------------------------------------------------------------
    // Main Rendering
    // ------------------------------------------------------------------
    function renderTimeline(data) {
        var loadingEl = document.getElementById('timeline-loading');
        var streamEl = document.getElementById('timeline-stream');
        var emptyEl = document.getElementById('timeline-empty');

        if (loadingEl) loadingEl.classList.add('hidden');
        window._timelineState.eventsById = {};

        var days = (data && data.days) || [];
        if (days.length === 0) {
            if (emptyEl) emptyEl.classList.remove('hidden');
            return;
        }

        if (streamEl) streamEl.classList.remove('hidden');

        // 1. Calculate Current Time
        var d = new Date();
        var nowMin = data.current_now_min || (d.getHours() * 60 + d.getMinutes());
        nowMin = Math.max(nowMin, 180); // clamp to at least 3:00 AM for visual span
        window._timelineState.currentNowMin = nowMin;

        var clockEl = document.getElementById('biostream-current-time');
        if (clockEl) {
            var timeObj = formatTime(nowMin);
            clockEl.textContent = timeObj.full12;
        }

        // 2. Extract Events for Today (or top day in feed) for the BioStream Canvas
        var topDay = days[0];
        var streamEvents = topDay ? (topDay.events || []) : [];

        // Synthesize realistic biological metabolic dips if user has long gaps
        var enrichedEvents = enrichBiologicalDips(streamEvents, nowMin);

        // Update Bio-Equilibrium Diagnostics
        updateBioEquilibrium(enrichedEvents);

        // 3. Render the BioStream Pulse SVG Curve & Nodes
        renderBioStream(enrichedEvents, nowMin, window._timelineState.filter);

        // 4. Render Itemized Day Groups Feed
        if (streamEl) {
            streamEl.innerHTML = '';
            days.forEach(function (day) {
                var daySection = buildDaySection(day);
                streamEl.appendChild(daySection);
            });
        }
    }

    // ------------------------------------------------------------------
    // Bio-Equilibrium Diagnostics
    // ------------------------------------------------------------------
    function updateBioEquilibrium(events) {
        var posCount = 0;
        var negCount = 0;
        var totalVal = 0;

        events.forEach(function (e) {
            var v = typeof e.value === 'number' ? e.value : 50;
            totalVal += v;
            if (v >= 0) posCount++;
            else negCount++;
        });

        var avgScore = events.length > 0 ? Math.round(totalVal / events.length) : 55;

        var avgScoreEl = document.getElementById('pulse-avg-score');
        var posEl = document.getElementById('pulse-vitality-count');
        var negEl = document.getElementById('pulse-deficit-count');

        if (avgScoreEl) {
            avgScoreEl.textContent = (avgScore >= 0 ? '+' : '') + avgScore;
            avgScoreEl.className = 'text-sm sm:text-base font-black ' + (avgScore >= 0 ? 'text-emerald-400' : 'text-rose-400');
        }
        if (posEl) posEl.textContent = posCount;
        if (negEl) negEl.textContent = negCount;
    }

    // ------------------------------------------------------------------
    // Enriches events with natural metabolic dips (dehydration, fasting gap)
    // ------------------------------------------------------------------
    function enrichBiologicalDips(events, nowMin) {
        var list = events.slice();

        // If no events overnight, insert natural overnight wake deficit
        var hasEarlyWater = list.some(function (e) { return (e.time_min || 0) < 480 && e.category === 'water'; });
        if (!hasEarlyWater && nowMin >= 420) {
            list.push({
                id: 'synth-dehyd-1',
                synthetic: true,
                time_min: 390,
                time_str: '6:30 AM',
                category: 'water',
                value: -40,
                title: 'Overnight Dehydration',
                subtitle: 'Natural fasting fluid deficit (-40)',
                chips: [{ label: 'Fluid Deficit', icon: 'fa-droplet-slash', color: 'rose' }]
            });
        }

        return list.sort(function (a, b) { return (a.time_min || 0) - (b.time_min || 0); });
    }

    // ------------------------------------------------------------------
    // SVG BioStream Coordinate Curve & Interactive Scrubber
    // ------------------------------------------------------------------
    function renderBioStream(events, currentNow, filterCategory) {
        var svg = document.getElementById('biostream-svg');
        if (!svg) return;

        var svgWidth = 480;
        var svgHeight = 640;
        var centerX = svgWidth / 2;
        var maxDeviation = centerX - 45;

        function timeToY(timeMin) {
            var topY = 24;
            var bottomY = svgHeight - 24;
            var ratio = (currentNow - timeMin) / (currentNow || 1);
            return topY + ratio * (bottomY - topY);
        }

        function yToTime(y) {
            var topY = 24;
            var bottomY = svgHeight - 24;
            var clampedY = Math.max(topY, Math.min(bottomY, y));
            var ratio = (clampedY - topY) / (bottomY - topY);
            return Math.round(currentNow - ratio * currentNow);
        }

        // Filter events
        var filteredEvents = filterCategory === 'all'
            ? events
            : events.filter(function (e) { return e.category === filterCategory; });

        // Sample points along time domain [0, currentNow]
        var samples = 48;
        var step = currentNow / samples;
        var points = [];

        for (var i = 0; i <= samples; i++) {
            var t = Math.min(i * step, currentNow);
            var composite = 0;
            var totalWeight = 0;

            filteredEvents.forEach(function (evt) {
                var evtTime = evt.time_min || 0;
                var delta = t - evtTime;
                var evtVal = typeof evt.value === 'number' ? evt.value : 60;

                if (delta >= 0 && delta < 240) { // impact lingers for 4 hours
                    var decay = Math.exp(-delta / 60);
                    composite += evtVal * decay;
                    totalWeight += decay;
                } else if (Math.abs(delta) < 20) {
                    composite += evtVal;
                    totalWeight += 1;
                }
            });

            // Apply natural background decay if no recent events
            var normalizedScore = totalWeight > 0 ? (composite / Math.max(1, totalWeight * 0.8)) : -15;
            var clampedScore = Math.max(-100, Math.min(100, normalizedScore));

            var y = timeToY(t);
            var x = centerX + (clampedScore / 100) * maxDeviation;

            points.push({
                timeMin: t,
                score: clampedScore,
                x: x,
                y: y
            });
        }

        // Sort descending from top (currentNow) to bottom (0)
        points.sort(function (a, b) { return a.y - b.y; });
        window._timelineState.points = points;

        // Construct SVG Bezier Smooth Path String
        if (points.length >= 2) {
            var d = 'M ' + points[0].x.toFixed(1) + ' ' + points[0].y.toFixed(1);
            for (var j = 0; j < points.length - 1; j++) {
                var p0 = points[Math.max(0, j - 1)];
                var p1 = points[j];
                var p2 = points[j + 1];
                var p3 = points[Math.min(points.length - 1, j + 2)];

                var cp1x = p1.x + (p2.x - p0.x) / 6;
                var cp1y = p1.y + (p2.y - p0.y) / 6;
                var cp2x = p2.x - (p3.x - p1.x) / 6;
                var cp2y = p2.y - (p3.y - p1.y) / 6;

                d += ' C ' + cp1x.toFixed(1) + ' ' + cp1y.toFixed(1) + ', ' +
                     cp2x.toFixed(1) + ' ' + cp2y.toFixed(1) + ', ' +
                     p2.x.toFixed(1) + ' ' + p2.y.toFixed(1);
            }

            var curveEl = document.getElementById('biostream-curve');
            if (curveEl) curveEl.setAttribute('d', d);

            var topP = points[0];
            var botP = points[points.length - 1];

            var rightArea = d + ' L ' + centerX + ' ' + botP.y.toFixed(1) + ' L ' + centerX + ' ' + topP.y.toFixed(1) + ' Z';
            var leftArea = d + ' L ' + centerX + ' ' + botP.y.toFixed(1) + ' L ' + centerX + ' ' + topP.y.toFixed(1) + ' Z';

            var rightEl = document.getElementById('biostream-right-area');
            if (rightEl) rightEl.setAttribute('d', rightArea);

            var leftEl = document.getElementById('biostream-left-area');
            if (leftEl) leftEl.setAttribute('d', leftArea);
        }

        // Render Time Axis Rungs
        var rungsGroup = document.getElementById('biostream-rungs');
        if (rungsGroup) {
            rungsGroup.innerHTML = '';
            var ratios = [0.25, 0.5, 0.75];
            ratios.forEach(function (ratio) {
                var yVal = 24 + ratio * (svgHeight - 48);
                var tVal = yToTime(yVal);
                var tObj = formatTime(tVal);

                var line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                line.setAttribute('x1', '20');
                line.setAttribute('y1', yVal);
                line.setAttribute('x2', String(svgWidth - 20));
                line.setAttribute('y2', yVal);
                line.setAttribute('stroke', '#334155');
                line.setAttribute('stroke-width', '0.75');
                line.setAttribute('stroke-dasharray', '2 6');
                line.setAttribute('opacity', '0.5');
                rungsGroup.appendChild(line);

                var txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                txt.setAttribute('x', '24');
                txt.setAttribute('y', String(yVal - 6));
                txt.setAttribute('fill', '#64748B');
                txt.setAttribute('font-size', '10');
                txt.setAttribute('font-family', 'monospace');
                txt.textContent = tObj.full12;
                rungsGroup.appendChild(txt);
            });
        }

        // Render Event Nodes
        var nodesGroup = document.getElementById('biostream-nodes');
        if (nodesGroup) {
            nodesGroup.innerHTML = '';
            filteredEvents.forEach(function (evt) {
                var evtTime = evt.time_min || 0;
                var evtVal = typeof evt.value === 'number' ? evt.value : 60;
                var yPos = timeToY(evtTime);
                var xPos = centerX + (evtVal / 100) * maxDeviation;

                var cat = CATEGORIES[evt.category] || CATEGORIES.strength;
                var color = cat.color;

                var g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
                g.setAttribute('class', 'cursor-pointer');
                g.style.cursor = 'pointer';

                // Polarity connector to center
                var conn = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                conn.setAttribute('x1', String(centerX));
                conn.setAttribute('y1', String(yPos));
                conn.setAttribute('x2', String(xPos));
                conn.setAttribute('y2', String(yPos));
                conn.setAttribute('stroke', color);
                conn.setAttribute('stroke-width', '1');
                conn.setAttribute('stroke-dasharray', '2 2');
                conn.setAttribute('opacity', '0.4');
                g.appendChild(conn);

                // Glow ripple
                var ripple = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                ripple.setAttribute('cx', String(xPos));
                ripple.setAttribute('cy', String(yPos));
                ripple.setAttribute('r', '13');
                ripple.setAttribute('fill', color);
                ripple.setAttribute('fill-opacity', '0.22');
                g.appendChild(ripple);

                // Outer Node Circle
                var outer = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                outer.setAttribute('cx', String(xPos));
                outer.setAttribute('cy', String(yPos));
                outer.setAttribute('r', '8');
                outer.setAttribute('fill', '#0F172A');
                outer.setAttribute('stroke', color);
                outer.setAttribute('stroke-width', '2.5');
                g.appendChild(outer);

                // Core Dot
                var core = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                core.setAttribute('cx', String(xPos));
                core.setAttribute('cy', String(yPos));
                core.setAttribute('r', '3');
                core.setAttribute('fill', color);
                g.appendChild(core);

                // Click event
                g.onclick = function (e) {
                    e.stopPropagation();
                    if (!evt.synthetic) {
                        if (typeof window.playButtonTap === 'function') window.playButtonTap();
                        if (typeof window.haptic === 'function') window.haptic(25);
                        window.showTimelineDetail(evt.id);
                    }
                };

                nodesGroup.appendChild(g);
            });
        }

        // Attach Interactive Scrubber Listeners
        setupScrubberListeners(svg, svgWidth, svgHeight, currentNow, events);
    }

    function setupScrubberListeners(svg, svgWidth, svgHeight, currentNow, events) {
        var scrubber = document.getElementById('biostream-scrubber');
        var scrubberLine = document.getElementById('scrubber-line');
        var scrubberDot = document.getElementById('scrubber-dot');
        var tooltip = document.getElementById('biostream-tooltip');
        var timeEl = document.getElementById('tooltip-time');
        var scoreEl = document.getElementById('tooltip-score');
        var labelEl = document.getElementById('tooltip-label');
        var dotEl = document.getElementById('tooltip-cat-dot');

        function handleMove(clientX, clientY) {
            var rect = svg.getBoundingClientRect();
            var relY = clientY - rect.top;
            var scaleY = svgHeight / rect.height;
            var scaledY = relY * scaleY;

            var points = window._timelineState.points;
            if (!points || points.length === 0) return;

            // Find closest sample point
            var closest = points[0];
            var minDiff = Infinity;
            points.forEach(function (p) {
                var diff = Math.abs(p.y - scaledY);
                if (diff < minDiff) {
                    minDiff = diff;
                    closest = p;
                }
            });

            // Find closest event
            var nearbyEvent = events.find(function (ev) {
                return Math.abs((ev.time_min || 0) - closest.timeMin) < 30;
            });

            // Position Scrubber
            if (scrubber) scrubber.classList.remove('hidden');
            if (scrubberLine) {
                scrubberLine.setAttribute('y1', String(closest.y));
                scrubberLine.setAttribute('y2', String(closest.y));
            }
            if (scrubberDot) {
                scrubberDot.setAttribute('cx', String(closest.x));
                scrubberDot.setAttribute('cy', String(closest.y));
            }

            // Position Tooltip HUD
            if (tooltip) {
                tooltip.classList.remove('hidden');
                var leftPct = (closest.x / svgWidth) * 100;
                var topPct = (closest.y / svgHeight) * 100;
                tooltip.style.left = leftPct + '%';
                tooltip.style.top = topPct + '%';

                var tObj = formatTime(closest.timeMin);
                if (timeEl) timeEl.textContent = tObj.full12;

                var score = Math.round(closest.score);
                if (scoreEl) {
                    scoreEl.textContent = (score >= 0 ? 'Vitality +' : 'Decay ') + score;
                    scoreEl.className = 'font-bold ' + (score >= 0 ? 'text-emerald-400' : 'text-rose-400');
                }

                if (nearbyEvent) {
                    var cat = CATEGORIES[nearbyEvent.category] || CATEGORIES.strength;
                    if (dotEl) dotEl.style.backgroundColor = cat.color;
                    if (labelEl) labelEl.textContent = nearbyEvent.title || nearbyEvent.label || 'Activity Event';
                } else {
                    if (dotEl) dotEl.style.backgroundColor = '#06B6D4';
                    if (labelEl) labelEl.textContent = score >= 0 ? 'Vitality maintenance flow' : 'Metabolic decay & recovery drain';
                }
            }
        }

        function handleEnd() {
            if (scrubber) scrubber.classList.add('hidden');
            if (tooltip) tooltip.classList.add('hidden');
        }

        svg.onmousemove = function (e) {
            handleMove(e.clientX, e.clientY);
        };
        svg.onmouseleave = handleEnd;

        svg.ontouchmove = function (e) {
            if (e.touches && e.touches.length > 0) {
                handleMove(e.touches[0].clientX, e.touches[0].clientY);
            }
        };
        svg.ontouchend = handleEnd;
        svg.ontouchcancel = handleEnd;
    }

    // ------------------------------------------------------------------
    // Day Section Builder (Itemized Cards Feed)
    // ------------------------------------------------------------------
    function buildDaySection(day) {
        var wrap = document.createElement('div');
        wrap.className = 'timeline-day-group';

        // 1. Sticky Daily Header & Vitals Bar
        var header = document.createElement('div');
        header.className = 'timeline-day-header p-3.5 rounded-2xl bg-slate-900/90 border border-slate-800 backdrop-blur-md mb-3 shadow-md';

        var titleRow = document.createElement('div');
        titleRow.className = 'flex items-center justify-between gap-2 mb-2';

        var titleHtml = '<div class="flex items-center gap-2">' +
            '<span class="text-sm font-black text-white tracking-tight">' + escapeHtml(day.display_title) + '</span>' +
            '<span class="text-xs font-semibold text-slate-400">' + escapeHtml(day.formatted_date) + '</span>' +
            '</div>';

        var dayXp = day.totals && day.totals.total_xp;
        if (dayXp > 0) {
            titleHtml += '<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-black bg-amber-500/10 text-amber-300 border border-amber-500/30">' +
                '<i class="fa-solid fa-bolt text-[10px]"></i> +' + dayXp + ' XP' +
                '</span>';
        }
        titleRow.innerHTML = titleHtml;

        // Vitals Strip
        var vitalsStrip = document.createElement('div');
        vitalsStrip.className = 'flex items-center flex-wrap gap-1.5 text-xs font-semibold text-slate-300 pt-2 border-t border-slate-800/80';

        var t = day.totals || {};
        var vitalsHtml = '';

        if (t.workout_count > 0) {
            vitalsHtml += '<span class="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg bg-slate-800/80 border border-slate-700/60 text-flamingo">' +
                '<i class="fa-solid fa-dumbbell"></i> ' + t.workout_count + ' workout' + (t.workout_count > 1 ? 's' : '') +
                (t.workout_volume_lbs > 0 ? ' • ' + Math.round(t.workout_volume_lbs).toLocaleString() + ' lbs' : '') +
                '</span>';
        }
        if (t.calories > 0) {
            vitalsHtml += '<span class="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg bg-slate-800/80 border border-slate-700/60 text-emerald-400">' +
                '<i class="fa-solid fa-bowl-food"></i> ' + Math.round(t.calories) + ' kcal' +
                (t.protein > 0 ? ' • ' + Math.round(t.protein) + 'g P' : '') +
                '</span>';
        }
        if (t.water_oz > 0) {
            vitalsHtml += '<span class="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg bg-slate-800/80 border border-slate-700/60 text-cyan-400">' +
                '<i class="fa-solid fa-glass-water"></i> ' + Math.round(t.water_oz) + ' oz' +
                '</span>';
        }
        if (t.sleep_hours > 0) {
            vitalsHtml += '<span class="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg bg-slate-800/80 border border-slate-700/60 text-purple-300">' +
                '<i class="fa-solid fa-moon"></i> ' + t.sleep_hours + 'h sleep' +
                (t.sleep_score ? ' • Score ' + t.sleep_score : '') +
                '</span>';
        }

        vitalsStrip.innerHTML = vitalsHtml;
        header.appendChild(titleRow);
        if (vitalsHtml) header.appendChild(vitalsStrip);
        wrap.appendChild(header);

        // 2. Events Rail
        var railWrap = document.createElement('div');
        railWrap.className = 'relative pl-6 sm:pl-8 border-l-2 border-slate-800 ml-3 sm:ml-4 space-y-4 my-2';
        var events = day.events || [];
        events.forEach(function (ev) {
            window._timelineState.eventsById[ev.id] = ev;
            railWrap.appendChild(buildEventCard(ev));
        });
        wrap.appendChild(railWrap);
        return wrap;
    }

    // ------------------------------------------------------------------
    // Event Card Component
    // ------------------------------------------------------------------
    function buildEventCard(ev) {
        var item = document.createElement('div');
        item.className = 'relative group';

        // 1. Timeline Node Indicator
        var node = document.createElement('div');
        node.className = 'absolute -left-[31px] sm:-left-[39px] top-4 w-7 h-7 rounded-full flex items-center justify-center text-xs shadow-md border ' + getNodeColorClass(ev.category);
        node.innerHTML = '<i class="fa-solid ' + getCategoryIcon(ev.category) + '"></i>';
        item.appendChild(node);

        // 2. Card Content
        var card = document.createElement('div');
        card.className = 'timeline-event-card p-4 rounded-2xl bg-slate-900/80 border border-slate-800/80 hover:border-slate-600 hover:bg-slate-800 active:scale-[0.99] transition-all cursor-pointer shadow-sm';
        card.onclick = function () {
            if (typeof window.playButtonTap === 'function') window.playButtonTap();
            if (typeof window.haptic === 'function') window.haptic(25);
            window.showTimelineDetail(ev.id);
        };

        // Top line: source tag + time + XP chip
        var topRow = document.createElement('div');
        topRow.className = 'flex items-center justify-between text-xs mb-1.5';

        var metaLeft = document.createElement('div');
        metaLeft.className = 'flex items-center gap-2';
        metaLeft.innerHTML = '<span class="text-[10px] font-black uppercase tracking-wider px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700">' +
            escapeHtml(ev.source_label || ev.source) + '</span>' +
            '<span class="text-slate-400 font-semibold text-[11px]">' + escapeHtml(ev.time_str) + '</span>';

        var xpBadge = document.createElement('div');
        if (ev.xp > 0) {
            xpBadge.className = 'inline-flex items-center gap-1 font-black text-xs text-amber-300';
            xpBadge.innerHTML = '<i class="fa-solid fa-bolt text-[10px]"></i> +' + ev.xp + ' XP';
        }

        topRow.appendChild(metaLeft);
        if (ev.xp > 0) topRow.appendChild(xpBadge);
        card.appendChild(topRow);

        // Title line
        var titleRow = document.createElement('div');
        titleRow.className = 'flex items-baseline justify-between gap-2';
        titleRow.innerHTML = '<h4 class="text-sm font-black text-white group-hover:text-cyan-300 transition-colors">' +
            escapeHtml(ev.title) + '</h4>';
        card.appendChild(titleRow);

        // Visual Section
        var visualSection = buildVisualSnippet(ev);
        if (visualSection) card.appendChild(visualSection);

        // Action prompt
        var actionHint = document.createElement('div');
        actionHint.className = 'mt-3 pt-2 border-t border-slate-800/70 flex items-center justify-between text-[11px] text-slate-400';
        actionHint.innerHTML = '<span>Tap for itemized details</span>' +
            '<i class="fa-solid fa-chevron-right text-slate-500 group-hover:text-cyan-400 group-hover:translate-x-1 transition-all text-[10px]"></i>';
        card.appendChild(actionHint);

        item.appendChild(card);
        return item;
    }

    function buildVisualSnippet(ev) {
        var wrap = document.createElement('div');
        wrap.className = 'mt-2.5';

        // 1. Macro Bar Snippet (Nutrition / Food)
        if (ev.category === 'food' || ev.category === 'nutrition') {
            var m = ev.metrics || {};
            var pro = m.protein || 0;
            var carbs = m.carbs || 0;
            var fat = m.fat || 0;
            var totalG = pro + carbs + fat;

            var proPct = totalG > 0 ? Math.round((pro / totalG) * 100) : 33;
            var carbPct = totalG > 0 ? Math.round((carbs / totalG) * 100) : 33;
            var fatPct = totalG > 0 ? Math.max(0, 100 - proPct - carbPct) : 34;

            wrap.innerHTML = '<div class="flex items-center gap-2 mb-1.5">' +
                '<span class="text-xs font-black text-emerald-400">' + Math.round(m.calories || 0) + ' kcal</span>' +
                '<span class="text-[11px] font-bold text-slate-400">• P:' + Math.round(pro) + 'g / C:' + Math.round(carbs) + 'g / F:' + Math.round(fat) + 'g</span>' +
                '</div>' +
                '<div class="w-full h-2 rounded-full bg-slate-800 overflow-hidden flex">' +
                '<div style="width:' + proPct + '%" class="bg-emerald-400" title="Protein"></div>' +
                '<div style="width:' + carbPct + '%" class="bg-cyan-400" title="Carbs"></div>' +
                '<div style="width:' + fatPct + '%" class="bg-amber-400" title="Fat"></div>' +
                '</div>';
            return wrap;
        }

        // 2. Chips Snippet
        var chips = ev.chips || [];
        if (chips.length > 0) {
            var chipsWrap = document.createElement('div');
            chipsWrap.className = 'flex items-center flex-wrap gap-1.5';
            chips.forEach(function (c) {
                var span = document.createElement('span');
                span.className = 'inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-bold ' + getChipColorClass(c.color);
                span.innerHTML = (c.icon ? '<i class="fa-solid ' + c.icon + ' text-[10px]"></i> ' : '') + escapeHtml(c.label);
                chipsWrap.appendChild(span);
            });
            wrap.appendChild(chipsWrap);
            return wrap;
        }
        return null;
    }

    // ------------------------------------------------------------------
    // Drilldown Modals
    // ------------------------------------------------------------------
    window.showTimelineDetail = function (eventId) {
        var ev = window._timelineState.eventsById[eventId];
        if (!ev) return;
        var modal = document.getElementById('timeline-detail-modal');
        if (!modal) return;

        var iconWrap = document.getElementById('td-modal-icon-wrap');
        var icon = document.getElementById('td-modal-icon');
        if (iconWrap && icon) {
            iconWrap.className = 'w-12 h-12 rounded-2xl flex items-center justify-center text-xl ' + getNodeColorClass(ev.category);
            icon.className = 'fa-solid ' + getCategoryIcon(ev.category);
        }
        document.getElementById('td-modal-title').textContent = ev.title;
        document.getElementById('td-modal-source').textContent = ev.source_label || ev.source;
        document.getElementById('td-modal-datetime').textContent = ev.time_str;
        document.getElementById('td-modal-xp').textContent = ev.xp > 0 ? ('+' + ev.xp + ' XP') : 'Completed';
        document.getElementById('td-modal-metrics').innerHTML = renderModalMetrics(ev);
        document.getElementById('td-modal-items').innerHTML = renderModalItems(ev, document.getElementById('td-modal-section-title'));
        
        modal.classList.remove('hidden');
        setTimeout(function () {
            modal.classList.remove('opacity-0');
            modal.querySelector('.transform').classList.remove('translate-y-full');
        }, 10);
    };

    window.closeTimelineDetail = function () {
        var modal = document.getElementById('timeline-detail-modal');
        modal.querySelector('.transform').classList.add('translate-y-full');
        modal.classList.add('opacity-0');
        setTimeout(function () { modal.classList.add('hidden'); }, 250);
    };

    function renderModalMetrics(ev) {
        var m = ev.metrics || {};
        var html = '';

        if (ev.category === 'strength' || ev.category === 'cardio' || ev.category === 'workout') {
            if (m.volume_lbs) {
                html += '<div class="p-3 rounded-xl bg-slate-800/80 border border-slate-700/60 text-center">' +
                    '<div class="text-[10px] uppercase font-bold text-slate-400">Total Volume</div>' +
                    '<div class="text-base font-black text-rose-400">' + Math.round(m.volume_lbs).toLocaleString() + ' lbs</div>' +
                    '</div>';
            }
            if (m.duration_minutes) {
                html += '<div class="p-3 rounded-xl bg-slate-800/80 border border-slate-700/60 text-center">' +
                    '<div class="text-[10px] uppercase font-bold text-slate-400">Duration</div>' +
                    '<div class="text-base font-black text-white">' + Math.round(m.duration_minutes) + ' min</div>' +
                    '</div>';
            }
            if (m.calories_burned) {
                html += '<div class="p-3 rounded-xl bg-slate-800/80 border border-slate-700/60 text-center">' +
                    '<div class="text-[10px] uppercase font-bold text-slate-400">Burned</div>' +
                    '<div class="text-base font-black text-orange-400">' + Math.round(m.calories_burned) + ' cal</div>' +
                    '</div>';
            }
        } else if (ev.category === 'food' || ev.category === 'nutrition') {
            html += '<div class="p-3 rounded-xl bg-slate-800/80 border border-slate-700/60 text-center">' +
                '<div class="text-[10px] uppercase font-bold text-slate-400">Calories</div>' +
                '<div class="text-base font-black text-emerald-400">' + Math.round(m.calories || 0) + '</div>' +
                '</div>';
            html += '<div class="p-3 rounded-xl bg-slate-800/80 border border-slate-700/60 text-center">' +
                '<div class="text-[10px] uppercase font-bold text-slate-400">Protein</div>' +
                '<div class="text-base font-black text-emerald-400">' + Math.round(m.protein || 0) + 'g</div>' +
                '</div>';
            html += '<div class="p-3 rounded-xl bg-slate-800/80 border border-slate-700/60 text-center">' +
                '<div class="text-[10px] uppercase font-bold text-slate-400">Carbs / Fat</div>' +
                '<div class="text-base font-black text-cyan-400">' + Math.round(m.carbs || 0) + 'g / ' + Math.round(m.fat || 0) + 'g</div>' +
                '</div>';
        } else if (ev.category === 'water' || ev.category === 'hydration') {
            html += '<div class="p-3 rounded-xl bg-slate-800/80 border border-slate-700/60 text-center">' +
                '<div class="text-[10px] uppercase font-bold text-slate-400">Intake</div>' +
                '<div class="text-base font-black text-cyan-400">' + (m.water_oz || 0) + ' oz</div>' +
                '</div>';
            if (m.water_goal) {
                html += '<div class="p-3 rounded-xl bg-slate-800/80 border border-slate-700/60 text-center">' +
                    '<div class="text-[10px] uppercase font-bold text-slate-400">Daily Goal</div>' +
                    '<div class="text-base font-black text-white">' + Math.round(m.water_goal) + ' oz</div>' +
                    '</div>';
            }
            if (m.water_pct) {
                html += '<div class="p-3 rounded-xl bg-slate-800/80 border border-slate-700/60 text-center">' +
                    '<div class="text-[10px] uppercase font-bold text-slate-400">Goal %</div>' +
                    '<div class="text-base font-black text-cyan-300">' + m.water_pct + '%</div>' +
                    '</div>';
            }
        } else if (ev.category === 'sleep') {
            html += '<div class="p-3 rounded-xl bg-slate-800/80 border border-slate-700/60 text-center">' +
                '<div class="text-[10px] uppercase font-bold text-slate-400">Sleep Duration</div>' +
                '<div class="text-base font-black text-purple-400">' + (m.sleep_hours || 0) + ' hrs</div>' +
                '</div>';
            if (m.sleep_score) {
                html += '<div class="p-3 rounded-xl bg-slate-800/80 border border-slate-700/60 text-center">' +
                    '<div class="text-[10px] uppercase font-bold text-slate-400">Sleep Score</div>' +
                    '<div class="text-base font-black text-white">' + m.sleep_score + '</div>' +
                    '</div>';
            }
            if (m.charge) {
                html += '<div class="p-3 rounded-xl bg-slate-800/80 border border-slate-700/60 text-center">' +
                    '<div class="text-[10px] uppercase font-bold text-slate-400">Body Battery</div>' +
                    '<div class="text-base font-black text-emerald-400">+' + m.charge + '</div>' +
                    '</div>';
            }
        }
        return html;
    }

    function renderModalItems(ev, sectionTitleEl) {
        var d = ev.details || {};
        var html = '';

        if (ev.category === 'strength' || ev.category === 'workout') {
            if (sectionTitleEl) sectionTitleEl.textContent = 'Itemized Exercises';
            var exercises = d.exercises || [];
            if (exercises.length === 0) {
                return '<div class="text-xs text-slate-400 italic">No exercise logs available.</div>';
            }

            html += '<div class="space-y-2">';
            exercises.forEach(function (ex) {
                var sets = ex.sets || 0;
                var reps = ex.reps || 0;
                var wt = ex.weight || 0;
                var unit = ex.unit || 'lb';
                var vol = ex.volume_lbs || (sets * reps * wt);

                html += '<div class="p-2.5 rounded-xl bg-slate-900/60 border border-slate-700/60 flex items-center justify-between gap-3">' +
                    '<div>' +
                    '<div class="text-xs font-bold text-white">' + escapeHtml(ex.name) + '</div>' +
                    '<div class="text-[11px] font-semibold text-slate-400">' + sets + ' sets &bull; ' + reps + ' reps @ ' + wt + ' ' + unit + '</div>' +
                    '</div>' +
                    '<div class="text-right">' +
                    (vol > 0 ? '<div class="text-xs font-bold text-rose-400">' + Math.round(vol).toLocaleString() + ' ' + unit + '</div>' : '') +
                    (ex.est_1rm ? '<div class="text-[10px] text-amber-300 font-semibold">1RM: ' + Math.round(ex.est_1rm) + '</div>' : '') +
                    '</div>' +
                    '</div>';
            });
            html += '</div>';
            return html;
        }

        if (ev.category === 'food' || ev.category === 'nutrition') {
            if (sectionTitleEl) sectionTitleEl.textContent = 'Meal Breakdown';
            var foods = d.food_entries || [];
            if (foods.length === 0) {
                return '<div class="text-xs text-slate-400 italic">No food items detailed for this log.</div>';
            }

            html += '<div class="space-y-2">';
            foods.forEach(function (f) {
                html += '<div class="p-2.5 rounded-xl bg-slate-900/60 border border-slate-700/60 flex items-center justify-between gap-3">' +
                    '<div>' +
                    '<div class="text-xs font-bold text-white">' + escapeHtml(f.name) + '</div>' +
                    '<div class="text-[11px] font-semibold text-slate-400">P:' + Math.round(f.protein || 0) + 'g &bull; C:' + Math.round(f.carbs || 0) + 'g &bull; F:' + Math.round(f.fat || 0) + 'g</div>' +
                    '</div>' +
                    '<div class="text-xs font-bold text-emerald-400">' + Math.round(f.calories || 0) + ' kcal</div>' +
                    '</div>';
            });
            html += '</div>';
            return html;
        }

        if (ev.category === 'water' || ev.category === 'hydration') {
            if (sectionTitleEl) sectionTitleEl.textContent = 'Intake History';
            var waterEntries = d.water_entries || [];
            if (waterEntries.length === 0) {
                return '<div class="text-xs text-slate-400 italic">Quick hydration intake logged.</div>';
            }
            html += '<div class="space-y-2">';
            waterEntries.forEach(function (w) {
                html += '<div class="p-2.5 rounded-xl bg-slate-900/60 border border-slate-700/60 flex items-center justify-between">' +
                    '<div class="text-xs font-bold text-white">' + (w.time || 'Intake') + '</div>' +
                    '<div class="text-xs font-bold text-cyan-400">+' + w.amount + ' oz</div>' +
                    '</div>';
            });
            html += '</div>';
            return html;
        }

        if (ev.category === 'sleep') {
            if (sectionTitleEl) sectionTitleEl.textContent = 'Sleep Architecture';
            html += '<div class="grid grid-cols-2 gap-2">';
            if (d.deep_pct) {
                html += '<div class="p-2.5 rounded-xl bg-slate-900/60 border border-slate-700/60 text-center">' +
                    '<div class="text-[10px] text-slate-400 uppercase font-bold">Deep Sleep</div>' +
                    '<div class="text-sm font-black text-indigo-400">' + d.deep_pct + '%</div>' +
                    '</div>';
            }
            if (d.rem_pct) {
                html += '<div class="p-2.5 rounded-xl bg-slate-900/60 border border-slate-700/60 text-center">' +
                    '<div class="text-[10px] text-slate-400 uppercase font-bold">REM Sleep</div>' +
                    '<div class="text-sm font-black text-purple-400">' + d.rem_pct + '%</div>' +
                    '</div>';
            }
            html += '</div>' +
                '<div class="flex justify-between text-xs mt-3">' +
                '<span class="text-slate-400 font-semibold">Quality Status</span>' +
                '<span class="font-bold text-purple-400 uppercase tracking-wide">' + escapeHtml(d.status_label || 'Optimal') + '</span>' +
                '</div>';
            return html;
        }

        if (sectionTitleEl) sectionTitleEl.textContent = 'Details';
        return '<div class="text-xs text-slate-400">No additional details recorded for this entry.</div>';
    }

    // ------------------------------------------------------------------
    // Helpers & Color Resolvers
    // ------------------------------------------------------------------
    function getCategoryIcon(cat) {
        switch (cat) {
            case 'strength':
            case 'workout': return 'fa-dumbbell';
            case 'cardio':
            case 'endurance': return 'fa-fire';
            case 'food':
            case 'nutrition': return 'fa-utensils';
            case 'water':
            case 'hydration': return 'fa-droplet';
            case 'sleep': return 'fa-moon';
            default: return 'fa-bolt';
        }
    }

    function getNodeColorClass(cat) {
        switch (cat) {
            case 'strength':
            case 'workout':
                return 'bg-rose-500/20 text-rose-400 border-rose-500/40 shadow-[0_0_10px_rgba(244,63,94,0.3)]';
            case 'cardio':
            case 'endurance':
                return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40 shadow-[0_0_10px_rgba(16,185,129,0.3)]';
            case 'food':
            case 'nutrition':
                return 'bg-amber-500/20 text-amber-400 border-amber-500/40 shadow-[0_0_10px_rgba(245,158,11,0.3)]';
            case 'water':
            case 'hydration':
                return 'bg-cyan-500/20 text-cyan-400 border-cyan-500/40 shadow-[0_0_10px_rgba(6,182,212,0.3)]';
            case 'sleep':
                return 'bg-indigo-500/20 text-indigo-400 border-indigo-500/40 shadow-[0_0_10px_rgba(129,140,248,0.3)]';
            default:
                return 'bg-slate-700 text-slate-300 border-slate-600';
        }
    }

    function getChipColorClass(color) {
        switch (color) {
            case 'pink':
                return 'bg-pink-500/20 text-pink-300 border border-pink-500/30';
            case 'emerald':
                return 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30';
            case 'cyan':
                return 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30';
            case 'purple':
                return 'bg-purple-500/20 text-purple-300 border border-purple-500/30';
            case 'amber':
                return 'bg-amber-500/20 text-amber-300 border border-amber-500/30';
            case 'blue':
                return 'bg-blue-500/20 text-blue-300 border border-blue-500/30';
            case 'orange':
                return 'bg-orange-500/20 text-orange-300 border border-orange-500/30';
            default:
                return 'bg-slate-800 text-slate-300 border border-slate-700';
        }
    }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

})();
