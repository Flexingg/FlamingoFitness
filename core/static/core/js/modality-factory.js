/* ============================================================
   Flamingo Fitness - Modality Controller Factory (Phase 6, docs/19 #22)
   Provides window.createModalityController(config) to eliminate
   boilerplate across modality detail controllers.
   ============================================================ */
(function () {
    'use strict';

    window.createModalityController = function (config) {
        var name = config.name; // e.g. 'nutrition', 'hydration', 'endurance', 'strength', 'recovery'
        var title = config.title;
        var capName = name.charAt(0).toUpperCase() + name.slice(1);
        var viewId = name + '-view';
        var contentId = name + '-content';
        var emptyId = name + '-empty';
        var apiUrl = config.apiUrl || ('/api/v1/' + name + '/');

        // 1. Back button handler
        var backFnName = 'backTo' + capName + 'Plan';
        window[backFnName] = function () {
            var view = document.getElementById(viewId);
            if (view) view.classList.add('hidden');
            window.ensureSinglePanelVisible('skill-tree');
        };

        // 2. Load handler
        var loadFnName = 'load' + capName;
        window[loadFnName] = function () {
            window.ffLog('[' + name + '] ' + loadFnName + ' start');
            if (window.closeModal) window.closeModal();

            var runFetch = function () {
                var content = document.getElementById(contentId);
                var empty = document.getElementById(emptyId);

                window.ensureSinglePanelVisible(viewId);
                if (empty) empty.classList.add('hidden');

                if (content && typeof window.renderSkeleton === 'function') {
                    window.renderSkeleton(content, 2);
                }

                window.ffLog('[' + name + '] fetching', apiUrl);
                return fetch(apiUrl, { credentials: 'same-origin' })
                    .then(function (res) {
                        window.ffLog('[' + name + '] fetch response status:', res.status);
                        if (res.status === 401 || res.status === 403) {
                            throw new Error('not-authenticated');
                        }
                        return res.ok ? res.json() : Promise.reject(res.status);
                    })
                    .then(function (data) {
                        window[renderFnName](data);
                    })
                    .catch(function (err) {
                        window.ffError('[' + name + '] fetch failed:', err);
                        if (content) {
                            content.classList.remove('hidden');
                            if (err && err.message === 'not-authenticated') {
                                content.innerHTML = '<p class="error-hint">Please log in to view ' + name + '.</p>';
                            } else {
                                content.innerHTML = '<p class="error-hint">Could not load ' + name + ' data (error ' + err + ').</p>';
                            }
                        }
                    });
            };

            if (typeof window.ensurePanelLoaded === 'function') {
                return window.ensurePanelLoaded(viewId).then(runFetch);
            } else {
                return runFetch();
            }
        };

        // 3. Render handler
        var renderFnName = 'render' + capName;
        window[renderFnName] = function (data) {
            var content = document.getElementById(contentId);
            var empty = document.getElementById(emptyId);
            if (!content) return;

            // Empty state check
            var hasData = data && (data.linked !== false) && (data.today || (data.history && data.history.length) || (data.entries && data.entries.length) || (data.workouts && data.workouts.length));
            if (!hasData) {
                content.classList.add('hidden');
                if (empty) {
                    window.showEmptyState(empty, config.emptyState || {
                        icon: config.icon || 'fa-circle-info',
                        title: 'No ' + name + ' data yet',
                        desc: 'Link a provider to start tracking ' + name + '.',
                        ctaText: 'Link Provider',
                        ctaHref: '/profile/'
                    });
                    empty.classList.remove('hidden');
                }
                return;
            }

            if (empty) empty.classList.add('hidden');
            content.classList.remove('hidden');
            content.innerHTML = '';

            // Skill tree progress card
            var st = data.skill_tree || {};
            var skillSection = document.createElement('div');
            skillSection.className = 'modality-skill-section ' + name + '-skill-section';

            var iconClass = config.icon || 'fa-star';
            var currentLevel = st.level || 1;
            var currentXp = st.xp || 0;
            var totalXp = st.total_xp || 0;
            var progressPct = Math.min(100, Math.max(0, st.progress_pct !== undefined ? st.progress_pct : Math.round((currentXp / 100) * 100)));

            skillSection.innerHTML = 
                '<div class="skill-card-head">' +
                    '<div class="skill-card-title">' +
                        '<span class="skill-icon-wrap ' + name + '-icon-wrap"><i class="fa-solid ' + iconClass + '"></i></span>' +
                        '<div>' +
                            '<div class="skill-card-name">' + title + ' Skill Tree</div>' +
                            '<div class="skill-card-sub">Level Progress & Mastery</div>' +
                        '</div>' +
                    '</div>' +
                    '<div class="skill-level-badge ' + name + '-level-badge">Lv ' + currentLevel + '</div>' +
                '</div>' +
                '<div class="skill-xp-meta">' +
                    '<span class="skill-total-xp"><i class="fa-solid fa-trophy"></i> ' + totalXp.toLocaleString() + ' Total XP</span>' +
                    '<span class="skill-xp-fraction"><strong>' + currentXp + '</strong> / 100 XP <span class="skill-pct">(' + progressPct + '%)</span></span>' +
                '</div>' +
                '<div class="skill-xp-track">' +
                    '<div class="skill-xp-fill ' + name + '-xp-fill" style="width: ' + progressPct + '%;"></div>' +
                '</div>' +
                (config.guidanceText ? 
                    ('<div class="skill-guidance-box ' + name + '-guidance">' +
                        '<i class="fa-solid fa-circle-info"></i>' +
                        '<span>' + config.guidanceText + '</span>' +
                    '</div>') : '');

            content.appendChild(skillSection);

            // Custom modality-specific rendering
            if (typeof config.renderCustomContent === 'function') {
                config.renderCustomContent(content, data);
            }
        };

        return {
            load: window[loadFnName],
            render: window[renderFnName],
            back: window[backFnName]
        };
    };

})();
