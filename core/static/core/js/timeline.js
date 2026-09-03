/**
 * Flamingo Fitness - Activity Timeline Controller (timeline.js)
 * -----------------------------------------------------------
 * Visual-first life & training activity feed.
 * Features:
 * - Day-by-day chronological grouping with sticky summary vitals.
 * - Glanceable visual cards (workouts, nutrition/macros, hydration, sleep).
 * - Instant category filtering (All, Workouts, Food, Water, Sleep).
 * - 1-tap interactive drilldown modal with itemized sets, reps, macros & XP.
 */
(function () {
    'use strict';

    window._timelineState = {
        filter: 'all',
        days: 14,
        data: null,
        eventsById: {}
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

    // ------------------------------------------------------------------
    // Filters & Range Selectors
    // ------------------------------------------------------------------
    window.filterTimeline = function (category) {
        window._timelineState.filter = category;

        // Update pill UI active states
        var pills = document.querySelectorAll('.timeline-filter-pill');
        pills.forEach(function (pill) {
            var f = pill.getAttribute('data-filter');
            if (f === category) {
                pill.classList.add('active');
            } else {
                pill.classList.remove('active');
            }
        });

        fetchTimelineData(category, window._timelineState.days);
    };

    window.onTimelineDaysChange = function (days) {
        window._timelineState.days = parseInt(days, 10) || 14;
        fetchTimelineData(window._timelineState.filter, window._timelineState.days);
    };

    // ------------------------------------------------------------------
    // Data Fetching
    // ------------------------------------------------------------------
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
    // Rendering Stream
    // ------------------------------------------------------------------
    function renderTimeline(data) {
        var loadingEl = document.getElementById('timeline-loading');
        var streamEl = document.getElementById('timeline-stream');
        var emptyEl = document.getElementById('timeline-empty');

        if (loadingEl) loadingEl.classList.add('hidden');
        if (!streamEl) return;

        window._timelineState.eventsById = {};

        var days = (data && data.days) || [];
        if (days.length === 0) {
            streamEl.classList.add('hidden');
            if (emptyEl) emptyEl.classList.remove('hidden');
            return;
        }

        emptyEl.classList.add('hidden');
        streamEl.classList.remove('hidden');
        streamEl.innerHTML = '';

        days.forEach(function (day) {
            var dayGroup = buildDaySection(day);
            streamEl.appendChild(dayGroup);
        });
    }

    function buildDaySection(day) {
        var wrap = document.createElement('div');
        wrap.className = 'timeline-day-group';

        var t = day.totals || {};

        // 1. Sticky Day Vitals Header
        var header = document.createElement('div');
        header.className = 'timeline-day-header sticky top-14 z-20 bg-slate-900/90 backdrop-blur-md py-2.5 mb-3 border-b border-slate-800/80';

        var titleRow = document.createElement('div');
        titleRow.className = 'flex items-center justify-between gap-2 mb-1.5';

        var leftTitle = document.createElement('div');
        leftTitle.className = 'flex items-baseline gap-2';
        leftTitle.innerHTML = '<h3 class="text-base font-black text-white">' + escapeHtml(day.display_title) + '</h3>' +
            '<span class="text-xs font-semibold text-slate-400">' + escapeHtml(day.formatted_date) + '</span>';

        var rightXp = document.createElement('div');
        if (t.total_xp > 0) {
            rightXp.className = 'inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-black bg-amber-500/20 text-amber-300 border border-amber-500/30';
            rightXp.innerHTML = '<i class="fa-solid fa-bolt text-[10px]"></i> +' + t.total_xp + ' XP';
        }

        titleRow.appendChild(leftTitle);
        if (t.total_xp > 0) titleRow.appendChild(rightXp);

        // Daily Vitals Summary Strip
        var vitalsStrip = document.createElement('div');
        vitalsStrip.className = 'flex items-center gap-2 overflow-x-auto scrollbar-none text-[11px] font-bold text-slate-300';

        var vitalsHtml = '';
        if (t.workout_count > 0) {
            vitalsHtml += '<span class="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg bg-slate-800/80 border border-slate-700/60 text-flamingo">' +
                '<i class="fa-solid fa-dumbbell"></i> ' + t.workout_count + ' workout' + (t.workout_count > 1 ? 's' : '') +
                (t.workout_volume_lbs > 0 ? ' • ' + Math.round(t.workout_volume_lbs).toLocaleString() + ' lbs' : '') +
                '</span>';
        }
        if (t.calories > 0) {
            vitalsHtml += '<span class="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg bg-slate-800/80 border border-slate-700/60 text-emerald-300">' +
                '<i class="fa-solid fa-fire"></i> ' + Math.round(t.calories) + ' kcal' +
                (t.protein > 0 ? ' • ' + Math.round(t.protein) + 'g P' : '') +
                '</span>';
        }
        if (t.water_oz > 0) {
            vitalsHtml += '<span class="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg bg-slate-800/80 border border-slate-700/60 text-cyan-300">' +
                '<i class="fa-solid fa-glass-water"></i> ' + t.water_oz + ' oz' +
                '</span>';
        }
        if (t.sleep_hours > 0) {
            vitalsHtml += '<span class="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg bg-slate-800/80 border border-slate-700/60 text-purple-300">' +
                '<i class="fa-solid fa-moon"></i> ' + t.sleep_hours + 'h sleep' +
                (t.sleep_score ? ' • Score ' + t.sleep_score : '') +
                '</span>';
        }

        // Based discipline badges
        if (t.workout_volume_lbs >= 10000) {
            vitalsHtml += '<span class="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-pink-950/40 border border-pink-500/40 text-pink-300 font-black text-[10px] uppercase shadow-[0_0_8px_rgba(255,94,154,0.2)]">' +
                '🔱 Titan Volume' +
                '</span>';
        }
        if (t.protein >= 140) {
            vitalsHtml += '<span class="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-emerald-950/40 border border-emerald-500/40 text-emerald-300 font-black text-[10px] uppercase shadow-[0_0_8px_rgba(52,211,153,0.2)]">' +
                '🥩 Synthesis Maxed' +
                '</span>';
        }
        if (t.water_oz >= 80) {
            vitalsHtml += '<span class="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-cyan-950/40 border border-cyan-500/40 text-cyan-300 font-black text-[10px] uppercase shadow-[0_0_8px_rgba(34,211,238,0.2)]">' +
                '💧 Hydro Chad' +
                '</span>';
        }

        vitalsStrip.innerHTML = vitalsHtml;

        header.appendChild(titleRow);
        if (vitalsHtml) header.appendChild(vitalsStrip);
        wrap.appendChild(header);

        // 2. Vertical Timeline Rail & Events
        var railWrap = document.createElement('div');
        railWrap.className = 'relative pl-6 sm:pl-8 border-l-2 border-slate-800 ml-3 sm:ml-4 space-y-4 my-2';

        var events = day.events || [];
        events.forEach(function (ev) {
            window._timelineState.eventsById[ev.id] = ev;
            var eventCard = buildEventCard(ev);
            railWrap.appendChild(eventCard);
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

        // 1. Timeline Node Indicator on the rail
        var node = document.createElement('div');
        node.className = 'absolute -left-[31px] sm:-left-[39px] top-4 w-7 h-7 rounded-full flex items-center justify-center text-xs shadow-md border ' +
            getNodeColorClass(ev.category);
        node.innerHTML = '<i class="fa-solid ' + getCategoryIcon(ev.category) + '"></i>';
        item.appendChild(node);

        // 2. Card Content
        var card = document.createElement('div');
        card.className = 'timeline-event-card p-4 rounded-2xl bg-slate-800/70 border border-slate-700/70 hover:border-slate-500 hover:bg-slate-800 active:scale-[0.99] transition-all cursor-pointer shadow-sm';
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
        metaLeft.innerHTML = '<span class="text-[10px] font-black uppercase tracking-wider px-2 py-0.5 rounded-full bg-slate-700/80 text-slate-300 border border-slate-600/60">' +
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
        var titleHtml = '<h4 class="text-sm font-black text-white group-hover:text-cyan-300 transition-colors">' +
            escapeHtml(ev.title) + '</h4>';
        if (ev.subtitle) {
            titleHtml += '<span class="text-xs font-semibold text-slate-400 truncate">' + escapeHtml(ev.subtitle) + '</span>';
        }
        titleRow.innerHTML = titleHtml;
        card.appendChild(titleRow);

        // Visual Glanceable Section (No reading required)
        var visualSection = buildVisualSnippet(ev);
        if (visualSection) {
            card.appendChild(visualSection);
        }

        // Action prompt
        var actionHint = document.createElement('div');
        actionHint.className = 'mt-3 pt-2 border-t border-slate-700/50 flex items-center justify-between text-[11px] text-slate-400';
        actionHint.innerHTML = '<span>Tap for itemized details</span>' +
            '<i class="fa-solid fa-chevron-right text-slate-500 group-hover:text-cyan-400 group-hover:translate-x-1 transition-all text-[10px]"></i>';
        card.appendChild(actionHint);

        item.appendChild(card);
        return item;
    }

    function buildVisualSnippet(ev) {
        var wrap = document.createElement('div');
        wrap.className = 'mt-2.5';

        // 1. Macro Bar Snippet (Nutrition)
        if (ev.category === 'nutrition') {
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
                '<div class="w-full h-2 rounded-full bg-slate-700 overflow-hidden flex">' +
                '<div style="width:' + proPct + '%" class="bg-emerald-400" title="Protein"></div>' +
                '<div style="width:' + carbPct + '%" class="bg-cyan-400" title="Carbs"></div>' +
                '<div style="width:' + fatPct + '%" class="bg-amber-400" title="Fat"></div>' +
                '</div>';
            return wrap;
        }

        // 2. Chips Snippet (Workouts, Hydration, Sleep)
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
    // Detail Drilldown Modal Handler
    // ------------------------------------------------------------------
    window.showTimelineDetail = function (eventId) {
        var ev = window._timelineState.eventsById[eventId];
        if (!ev) return;

        var modal = document.getElementById('timeline-detail-modal');
        if (!modal) return;

        // Set Header
        var iconWrap = document.getElementById('td-modal-icon-wrap');
        var icon = document.getElementById('td-modal-icon');
        if (iconWrap && icon) {
            iconWrap.className = 'w-12 h-12 rounded-2xl flex items-center justify-center text-xl ' + getNodeColorClass(ev.category);
            icon.className = 'fa-solid ' + getCategoryIcon(ev.category);
        }

        var titleEl = document.getElementById('td-modal-title');
        if (titleEl) titleEl.textContent = ev.title;

        var sourceEl = document.getElementById('td-modal-source');
        if (sourceEl) sourceEl.textContent = ev.source_label || ev.source;

        var dtEl = document.getElementById('td-modal-datetime');
        if (dtEl) dtEl.textContent = ev.time_str + ' • ' + (ev.subtitle || ev.event_type.toUpperCase());

        var xpEl = document.getElementById('td-modal-xp');
        if (xpEl) xpEl.textContent = ev.xp > 0 ? ('+' + ev.xp + ' XP') : 'Completed';

        // Render Metrics Cards
        var metricsEl = document.getElementById('td-modal-metrics');
        if (metricsEl) {
            metricsEl.innerHTML = renderModalMetrics(ev);
        }

        // Render Itemized Breakdown List
        var itemsEl = document.getElementById('td-modal-items');
        var sectionTitleEl = document.getElementById('td-modal-section-title');
        if (itemsEl) {
            itemsEl.innerHTML = renderModalItems(ev, sectionTitleEl);
        }

        // Notes
        var notesWrap = document.getElementById('td-modal-notes-wrap');
        var notesEl = document.getElementById('td-modal-notes');
        var notesText = (ev.details && ev.details.notes) || '';
        if (notesWrap && notesEl) {
            if (notesText) {
                notesEl.textContent = notesText;
                notesWrap.classList.remove('hidden');
            } else {
                notesWrap.classList.add('hidden');
            }
        }

        // Open animation
        modal.classList.remove('hidden');
        setTimeout(function () {
            modal.classList.remove('opacity-0');
            var sheet = modal.querySelector('.transform');
            if (sheet) sheet.classList.remove('translate-y-full');
        }, 10);
    };

    window.closeTimelineDetail = function () {
        var modal = document.getElementById('timeline-detail-modal');
        if (!modal) return;

        var sheet = modal.querySelector('.transform');
        if (sheet) sheet.classList.add('translate-y-full');
        modal.classList.add('opacity-0');

        setTimeout(function () {
            modal.classList.add('hidden');
        }, 250);
    };

    function renderModalMetrics(ev) {
        var m = ev.metrics || {};
        var html = '';

        if (ev.category === 'workout') {
            if (m.volume_lbs) {
                html += '<div class="p-3 rounded-xl bg-slate-800/80 border border-slate-700/60 text-center">' +
                    '<div class="text-[10px] uppercase font-bold text-slate-400">Total Volume</div>' +
                    '<div class="text-base font-black text-flamingo">' + Math.round(m.volume_lbs).toLocaleString() + ' lbs</div>' +
                    '</div>';
            }
            if (m.duration_minutes) {
                html += '<div class="p-3 rounded-xl bg-slate-800/80 border border-slate-700/60 text-center">' +
                    '<div class="text-[10px] uppercase font-bold text-slate-400">Duration</div>' +
                    '<div class="text-base font-black text-white">' + Math.round(m.duration_minutes) + ' min</div>' +
                    '</div>';
            }
            if (m.total_sets) {
                html += '<div class="p-3 rounded-xl bg-slate-800/80 border border-slate-700/60 text-center">' +
                    '<div class="text-[10px] uppercase font-bold text-slate-400">Sets Done</div>' +
                    '<div class="text-base font-black text-amber-400">' + m.total_sets + ' sets</div>' +
                    '</div>';
            }
            if (m.calories_burned) {
                html += '<div class="p-3 rounded-xl bg-slate-800/80 border border-slate-700/60 text-center">' +
                    '<div class="text-[10px] uppercase font-bold text-slate-400">Burned</div>' +
                    '<div class="text-base font-black text-orange-400">' + Math.round(m.calories_burned) + ' cal</div>' +
                    '</div>';
            }
        } else if (ev.category === 'nutrition') {
            html += '<div class="p-3 rounded-xl bg-slate-800/80 border border-slate-700/60 text-center">' +
                '<div class="text-[10px] uppercase font-bold text-slate-400">Calories</div>' +
                '<div class="text-base font-black text-emerald-400">' + Math.round(m.calories || 0) + '</div>' +
                '</div>' +
                '<div class="p-3 rounded-xl bg-slate-800/80 border border-slate-700/60 text-center">' +
                '<div class="text-[10px] uppercase font-bold text-slate-400">Protein</div>' +
                '<div class="text-base font-black text-emerald-300">' + Math.round(m.protein || 0) + 'g</div>' +
                '</div>' +
                '<div class="p-3 rounded-xl bg-slate-800/80 border border-slate-700/60 text-center">' +
                '<div class="text-[10px] uppercase font-bold text-slate-400">Carbs / Fat</div>' +
                '<div class="text-sm font-black text-cyan-300 mt-0.5">' + Math.round(m.carbs || 0) + 'g / ' + Math.round(m.fat || 0) + 'g</div>' +
                '</div>';
        } else if (ev.category === 'hydration') {
            html += '<div class="p-3 rounded-xl bg-slate-800/80 border border-slate-700/60 text-center">' +
                '<div class="text-[10px] uppercase font-bold text-slate-400">Water Logged</div>' +
                '<div class="text-base font-black text-cyan-400">' + m.water_oz + ' oz</div>' +
                '</div>';
            if (m.water_goal) {
                html += '<div class="p-3 rounded-xl bg-slate-800/80 border border-slate-700/60 text-center">' +
                    '<div class="text-[10px] uppercase font-bold text-slate-400">Goal Progress</div>' +
                    '<div class="text-base font-black text-slate-200">' + (m.water_pct || 0) + '%</div>' +
                    '</div>';
            }
        } else if (ev.category === 'sleep') {
            html += '<div class="p-3 rounded-xl bg-slate-800/80 border border-slate-700/60 text-center">' +
                '<div class="text-[10px] uppercase font-bold text-slate-400">Duration</div>' +
                '<div class="text-base font-black text-purple-300">' + m.sleep_hours + ' hrs</div>' +
                '</div>';
            if (m.sleep_score) {
                html += '<div class="p-3 rounded-xl bg-slate-800/80 border border-slate-700/60 text-center">' +
                    '<div class="text-[10px] uppercase font-bold text-slate-400">Sleep Score</div>' +
                    '<div class="text-base font-black text-purple-400">' + m.sleep_score + ' / 100</div>' +
                    '</div>';
            }
            if (m.charge) {
                html += '<div class="p-3 rounded-xl bg-slate-800/80 border border-slate-700/60 text-center">' +
                    '<div class="text-[10px] uppercase font-bold text-slate-400">Body Battery</div>' +
                    '<div class="text-base font-black text-emerald-400">+' + m.charge + '</div>' +
                    '</div>';
            }
        }

        return html || '<div class="col-span-3 text-center text-xs text-slate-400">Activity logged successfully</div>';
    }

    function renderModalItems(ev, sectionTitleEl) {
        var d = ev.details || {};
        var html = '';

        if (ev.category === 'workout') {
            if (sectionTitleEl) sectionTitleEl.textContent = 'Exercises & Sets';
            var exercises = d.exercises || [];
            if (exercises.length === 0) {
                return '<div class="text-xs text-slate-400">No exercise breakdown recorded for this session.</div>';
            }
            exercises.forEach(function (ex) {
                html += '<div class="flex items-center justify-between py-2 border-b border-slate-700/40 last:border-0">' +
                    '<div>' +
                    '<div class="text-sm font-bold text-white">' + escapeHtml(ex.name) + '</div>' +
                    '<div class="text-xs text-slate-400">' + (ex.sets || 1) + ' sets × ' + (ex.reps || 0) + ' reps @ ' + (ex.weight || 0) + ' ' + (ex.unit || 'lb') + '</div>' +
                    '</div>' +
                    '<div class="text-right">' +
                    (ex.est_1rm ? '<div class="text-xs font-bold text-amber-400">1RM ~' + Math.round(ex.est_1rm) + ' lb</div>' : '') +
                    (ex.volume_lbs ? '<div class="text-[11px] text-slate-400">' + Math.round(ex.volume_lbs).toLocaleString() + ' lbs</div>' : '') +
                    '</div>' +
                    '</div>';
            });
            return html;
        }

        if (ev.category === 'nutrition') {
            if (sectionTitleEl) sectionTitleEl.textContent = 'Food Entries';
            var foods = d.food_entries || [];
            if (foods.length === 0) {
                return '<div class="text-xs text-slate-400">Macro totals logged via integration.</div>';
            }
            foods.forEach(function (f) {
                html += '<div class="flex items-center justify-between py-2 border-b border-slate-700/40 last:border-0">' +
                    '<div>' +
                    '<div class="text-sm font-bold text-white">' + escapeHtml(f.name || f.food_name || 'Food item') + '</div>' +
                    '<div class="text-xs text-slate-400">P:' + Math.round(f.protein || 0) + 'g • C:' + Math.round(f.carbs || 0) + 'g • F:' + Math.round(f.fat || 0) + 'g</div>' +
                    '</div>' +
                    '<div class="text-right font-black text-emerald-400 text-sm">' +
                    Math.round(f.calories || 0) + ' kcal' +
                    '</div>' +
                    '</div>';
            });
            return html;
        }

        if (ev.category === 'hydration') {
            if (sectionTitleEl) sectionTitleEl.textContent = 'Intake History';
            var waters = d.water_entries || [];
            if (waters.length === 0) {
                return '<div class="text-xs text-slate-400">Direct water volume logged.</div>';
            }
            waters.forEach(function (w) {
                html += '<div class="flex items-center justify-between py-1.5 border-b border-slate-700/40 last:border-0">' +
                    '<span class="text-xs text-slate-300 font-semibold">' + escapeHtml(w.time || 'Logged') + '</span>' +
                    '<span class="text-xs font-black text-cyan-400">+' + w.amount + ' oz</span>' +
                    '</div>';
            });
            return html;
        }

        if (ev.category === 'sleep') {
            if (sectionTitleEl) sectionTitleEl.textContent = 'Sleep Composition';
            html += '<div class="space-y-2">' +
                '<div class="flex justify-between text-xs">' +
                '<span class="text-slate-400 font-semibold">Deep Sleep</span>' +
                '<span class="font-bold text-white">' + (d.deep_pct || 20) + '%</span>' +
                '</div>' +
                '<div class="flex justify-between text-xs">' +
                '<span class="text-slate-400 font-semibold">REM Sleep</span>' +
                '<span class="font-bold text-white">' + (d.rem_pct || 22) + '%</span>' +
                '</div>' +
                '<div class="flex justify-between text-xs">' +
                '<span class="text-slate-400 font-semibold">Quality Status</span>' +
                '<span class="font-bold text-purple-400 uppercase tracking-wide">' + escapeHtml(d.status_label || 'Optimal') + '</span>' +
                '</div>' +
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
            case 'workout': return 'fa-dumbbell';
            case 'nutrition': return 'fa-bowl-food';
            case 'hydration': return 'fa-glass-water';
            case 'sleep': return 'fa-moon';
            default: return 'fa-clock';
        }
    }

    function getNodeColorClass(cat) {
        switch (cat) {
            case 'workout':
                return 'bg-pink-500/20 text-flamingo border-pink-500/40 shadow-[0_0_10px_rgba(255,94,154,0.3)]';
            case 'nutrition':
                return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40 shadow-[0_0_10px_rgba(52,211,153,0.3)]';
            case 'hydration':
                return 'bg-cyan-500/20 text-cyan-400 border-cyan-500/40 shadow-[0_0_10px_rgba(34,211,238,0.3)]';
            case 'sleep':
                return 'bg-purple-500/20 text-purple-400 border-purple-500/40 shadow-[0_0_10px_rgba(192,132,252,0.3)]';
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
