/* Top-nav stat explainer controller.
 * Clicking the streak / materials / energy badges in the top nav fetches
 * GET /api/v1/stats/<stat>/ (core/views.py stat_info) and shows what the
 * stat means, how to earn it, and recent history of earning it.
 * Payload shape comes from core/services/stat_explainers.py.
 */
(function () {
    'use strict';

    var STAT_URL = '/api/v1/stats/';

    // Display metadata used before (and if) the fetch resolves.
    var STAT_META = {
        streak: { name: 'Streak', icon: 'fa-fire', color: '#f97316' },
        tokens: { name: 'Tokens', icon: 'fa-coins', color: '#fbbf24' },
        stamina: { name: 'Stamina', icon: 'fa-bolt', color: '#facc15' }
    };

    function esc(s) { return window.escHtml(s); }

    // Parse an ISO "YYYY-MM-DD" string without timezone drift.
    function fmtDate(iso) {
        if (!iso) return '';
        var parts = String(iso).slice(0, 10).split('-');
        if (parts.length !== 3) return String(iso);
        var d = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
        try {
            return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
        } catch (e) { return String(iso); }
    }

    function openStatModal() {
        document.getElementById('statModal').classList.add('show-modal');
    }

    window.closeStatModal = function () {
        document.getElementById('statModal').classList.remove('show-modal');
    };

    function setModalHeader(stat, valueText) {
        var meta = STAT_META[stat] || {};
        var icon = document.getElementById('stat-modal-icon');
        icon.innerHTML = '<i class="fa-solid ' + esc(meta.icon || 'fa-circle-info') + '"></i>';
        icon.style.color = meta.color || 'var(--primary-pink)';
        document.getElementById('stat-modal-title').textContent = meta.name || stat;
        document.getElementById('stat-modal-value').textContent =
            valueText == null ? '' : valueText;
        document.getElementById('stat-modal-value').style.color =
            meta.color || 'var(--primary-pink)';
    }

    var HISTORY_PREVIEW = 5; // rows shown before "Show all"

    function historyRowHtml(h, color) {
        var gain = String(h.amount || '').indexOf('+') === 0;
        return '<div class="stat-history-row">' +
            '<span class="stat-history-amount' + (gain ? ' gain' : ' neutral') +
            '" style="' + (gain ? 'color:' + color : '') + '">' + esc(h.amount) + '</span>' +
            '<span class="stat-history-main"><span class="stat-history-label">' + esc(h.label) + '</span>' +
            (h.detail ? '<span class="stat-history-detail">' + esc(h.detail) + '</span>' : '') +
            '</span>' +
            '<span class="stat-history-date">' + esc(fmtDate(h.date)) + '</span>' +
            '</div>';
    }

    function accSectionHtml(id, title, count, bodyHtml) {
        return '<div class="stat-acc" id="' + id + '">' +
            '<div class="stat-acc-head" role="button" tabindex="0" aria-expanded="false">' +
            '<span class="stat-acc-title">' + esc(title) +
            (count ? '<span class="stat-acc-count">' + count + '</span>' : '') +
            '</span>' +
            '<i class="fa-solid fa-chevron-down stat-acc-chev"></i>' +
            '</div>' +
            '<div class="stat-acc-body">' + bodyHtml + '</div>' +
            '</div>';
    }

    function toggleAcc(acc) {
        var opening = !acc.classList.contains('open');
        // Accordion behaviour: only one section open at a time.
        Array.prototype.forEach.call(document.querySelectorAll('.stat-acc.open'), function (o) {
            o.classList.remove('open');
            o.querySelector('.stat-acc-head').setAttribute('aria-expanded', 'false');
        });
        if (opening) {
            acc.classList.add('open');
            acc.querySelector('.stat-acc-head').setAttribute('aria-expanded', 'true');
        }
    }

    function bindAccordions(body) {
        Array.prototype.forEach.call(body.querySelectorAll('.stat-acc-head'), function (head) {
            var activate = function () { toggleAcc(head.parentNode); };
            head.addEventListener('click', activate);
            head.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activate(); }
            });
        });
    }

    function renderStat(data) {
        var meta = STAT_META[data.stat] || {};
        setModalHeader(data.stat, (data.value == null ? '-' : data.value) +
            (data.value_note ? ' ' + data.value_note : ''));
        document.getElementById('stat-modal-title').textContent = data.name || meta.name || data.stat;
        document.getElementById('stat-modal-desc').textContent = data.description || '';

        var body = document.getElementById('stat-modal-body');
        var color = meta.color || 'var(--primary-pink)';
        var html = '';

        // "Right now" facts (collapsed by default).
        if (data.facts && data.facts.length) {
            var factsHtml = '';
            data.facts.forEach(function (f) {
                factsHtml += '<div class="stat-fact-row"><span>' + esc(f.label) +
                    '</span><span class="stat-fact-value">' + esc(f.value) + '</span></div>';
            });
            html += accSectionHtml('acc-facts', 'Right now', '', factsHtml);
        }

        // "How to earn it" (collapsed by default).
        if (data.how_to_earn && data.how_to_earn.length) {
            var howHtml = '<ul class="stat-howto">';
            data.how_to_earn.forEach(function (line) {
                howHtml += '<li>' + esc(line) + '</li>';
            });
            howHtml += '</ul>';
            html += accSectionHtml('acc-howto', 'How to earn it', '', howHtml);
        }

        // Recent history: preview of HISTORY_PREVIEW rows + "Show all".
        var history = data.history || [];
        var histSection = '<div class="stat-section-title">Recent history</div>';
        if (history.length) {
            var previewHtml = '';
            history.slice(0, HISTORY_PREVIEW).forEach(function (h) {
                previewHtml += historyRowHtml(h, color);
            });
            var restHtml = '';
            history.slice(HISTORY_PREVIEW).forEach(function (h) {
                restHtml += historyRowHtml(h, color);
            });
            histSection += '<div class="stat-hist-preview">' + previewHtml + '</div>';
            if (restHtml) {
                histSection += '<div class="stat-hist-rest hidden">' + restHtml + '</div>' +
                    '<button class="stat-show-more" type="button">' +
                    'Show all ' + history.length + ' <i class="fa-solid fa-chevron-down"></i></button>';
            }
            html += histSection;
        } else {
            html += '<p class="stat-modal-empty">' +
                esc(data.empty_hint || 'Nothing recorded yet.') + '</p>';
        }

        body.innerHTML = html;
        bindAccordions(body);

        var more = body.querySelector('.stat-show-more');
        if (more) {
            more.addEventListener('click', function () {
                var rest = body.querySelector('.stat-hist-rest');
                rest.classList.remove('hidden');
                more.remove();
            });
        }
    }

    window.showStatInfo = function (stat) {
        if (!STAT_META[stat]) return;
        if (window.closeModal) window.closeModal(); // never stack over the action modal
        setModalHeader(stat, '\u2026');
        document.getElementById('stat-modal-desc').textContent = '';
        document.getElementById('stat-modal-body').innerHTML =
            '<p class="stat-modal-empty"><i class="fa-solid fa-spinner fa-spin"></i> Loading...</p>';
        openStatModal();

        fetch(STAT_URL + encodeURIComponent(stat) + '/', { credentials: 'same-origin' })
            .then(function (res) {
                if (res.status === 401 || res.status === 403) throw new Error('not-authenticated');
                return res.ok ? res.json() : Promise.reject(res.status);
            })
            .then(renderStat)
            .catch(function (err) {
                document.getElementById('stat-modal-body').innerHTML =
                    '<p class="stat-modal-empty error-hint">' +
                    (err && err.message === 'not-authenticated'
                        ? 'Please log in to see your stats.'
                        : 'Could not load this stat (error ' + err + ').') + '</p>';
            });
    };

    // Bind the three top-nav badges (click + keyboard).
    Array.prototype.forEach.call(document.querySelectorAll('.stat-clickable'), function (el) {
        var stat = el.getAttribute('data-stat');
        el.addEventListener('click', function () { window.showStatInfo(stat); });
        el.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                window.showStatInfo(stat);
            }
        });
    });

    // Dismiss on backdrop click or Escape.
    var overlay = document.getElementById('statModal');
    if (overlay) {
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) window.closeStatModal();
        });
    }
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && overlay && overlay.classList.contains('show-modal')) {
            window.closeStatModal();
        }
    });
})();

