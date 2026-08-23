/* Achievement Badges panel controller (Duolingo-styled 3D Gamification).
 * Opens from the "Badges" bottom-nav tab.
 * Consumes GET /api/v1/badges/ (core/views.py badges_state), which lazily
 * grants any newly-earned badges and serializes the catalog with points,
 * awarded timestamps and live progress.
 */
(function () {
    'use strict';

    var BADGES_URL = '/api/v1/badges/';
    var lastData = null;
    var activeCategory = 'all';
    var activeStatus = 'all'; // 'all' | 'earned' | 'locked'
    var searchQuery = '';

    var CATEGORY_ICONS = {
        'all': 'fa-asterisk',
        'Milestones': 'fa-flag-checkered',
        'Streaks': 'fa-fire',
        'Nutrition': 'fa-utensils',
        'Weight': 'fa-weight-scale',
        'Burn': 'fa-fire-flame-curved',
        'Sleep': 'fa-moon',
        'PvE': 'fa-dragon',
        'PvP': 'fa-hand-fist',
        'Shop': 'fa-box-open',
        'Leagues': 'fa-ranking-star',
        'Skill': 'fa-bolt',
        'Habits': 'fa-sun'
    };

    function esc(s) {
        return window.escHtml ? window.escHtml(s) : String(s || '').replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function haptic(ms) {
        if (typeof window.haptic === 'function') window.haptic(ms || 25);
    }

    function confetti() {
        if (typeof window.confettiBurst === 'function') window.confettiBurst();
    }

    function normalizeIcon(icon) {
        if (!icon) return 'fa-solid fa-medal';
        var clean = String(icon).trim();
        if (clean === 'fa-swords' || clean === 'swords') clean = 'fa-skull-crossbones';
        if (!clean.startsWith('fa-') && !clean.startsWith('fa ')) clean = 'fa-' + clean;
        if (!clean.includes('fa-solid') && !clean.includes('fa-regular') && !clean.includes('fa-brands')) {
            clean = 'fa-solid ' + clean;
        }
        return clean;
    }

    window.backToBadgesPlan = function () {
        if (typeof window.goBack === 'function') {
            window.goBack();
            return;
        }
        var view = document.getElementById('badges-view');
        if (view) view.classList.add('hidden');
        var hint = document.getElementById('loading-hint');
        if (hint) hint.classList.add('hidden');
        window.ensureSinglePanelVisible('skill-tree');
    };

    window.loadBadges = function () {
        window.ffLog('[badges] loadBadges start');
        if (window.closeModal) window.closeModal();
        closeBadgeModal();

        var runLoad = function () {
            var view = document.getElementById('badges-view');
            var content = document.getElementById('badges-content');
            var empty = document.getElementById('badges-empty');
            if (!view) { window.ffWarn('[badges] badges-view not found, aborting'); return; }
            window.ensureSinglePanelVisible('badges-view');
            if (window.setActiveNav) window.setActiveNav('nav-badges');
            if (content) content.classList.add('hidden');
            if (empty) empty.classList.add('hidden');

            fetch(BADGES_URL, { credentials: 'same-origin' })
                .then(function (res) {
                    if (res.status === 401 || res.status === 403) throw new Error('not-authenticated');
                    return res.ok ? res.json() : Promise.reject(res.status);
                })
                .then(function (data) {
                    window.ffLog('[badges] earned=', data.earned, 'of', data.total);
                    lastData = data;
                    if (data.newly_awarded && data.newly_awarded.length > 0) {
                        setTimeout(confetti, 350);
                    }
                    window.renderBadges(data);
                })
                .catch(function (err) {
                    window.ffError('[badges] fetch failed:', err);
                    if (content) {
                        content.classList.remove('hidden');
                        content.innerHTML = err && err.message === 'not-authenticated'
                            ? '<p class="text-center text-slate-400 py-8 font-bold">Please log in to view your badges.</p>'
                            : '<p class="text-center text-slate-400 py-8 font-bold">Could not load badges (error ' + esc(err) + ').</p>';
                    }
                    if (empty) empty.classList.add('hidden');
                });
        };

        if (typeof window.ensurePanelLoaded === 'function') {
            return window.ensurePanelLoaded('badges-view').then(runLoad);
        } else {
            return runLoad();
        }
    };

    // Main render function
    window.renderBadges = function (data) {
        lastData = data;
        var content = document.getElementById('badges-content');
        var empty = document.getElementById('badges-empty');
        if (!content) return;
        content.classList.remove('hidden');
        content.innerHTML = '';

        var allBadges = data.badges || [];
        if (!allBadges.length) {
            if (empty) empty.classList.remove('hidden');
            return;
        }
        if (empty) empty.classList.add('hidden');

        var earnedCount = data.earned || 0;
        var totalCount = data.total || allBadges.length;
        var earnedPts = data.earned_points || 0;
        var totalPts = data.total_points || 0;
        var pctComplete = totalCount > 0 ? Math.round((earnedCount / totalCount) * 100) : 0;

        // 1. Hero Progress Section
        var hero = document.createElement('div');
        hero.className = 'duo-badge-hero';
        hero.innerHTML =
            '<div class="duo-badge-hero-top">' +
                '<div class="duo-badge-hero-title">' +
                    '<i class="fa-solid fa-award text-yellow-400 text-lg"></i>' +
                    '<span>Mastery Progress</span>' +
                '</div>' +
                '<div class="duo-badge-points-pill">' +
                    '<i class="fa-solid fa-star text-amber-400"></i> ' +
                    '<strong>' + earnedPts + '</strong> / ' + totalPts + ' pts' +
                '</div>' +
            '</div>' +
            '<div class="duo-badge-track">' +
                '<div class="duo-badge-fill" style="width: ' + Math.min(100, Math.max(0, pctComplete)) + '%;"></div>' +
            '</div>' +
            '<div class="duo-badge-hero-stats">' +
                '<span><strong>' + earnedCount + '</strong> of <strong>' + totalCount + '</strong> Badges Unlocked</span>' +
                '<span><strong>' + pctComplete + '%</strong> Complete</span>' +
            '</div>';
        content.appendChild(hero);

        // 2. Newly Awarded Celebration Banner
        if (data.newly_awarded && data.newly_awarded.length > 0) {
            var banner = document.createElement('div');
            banner.className = 'badges-new-banner';
            banner.setAttribute('role', 'button');
            banner.setAttribute('tabindex', '0');
            banner.innerHTML =
                '<i class="fa-solid fa-wand-magic-sparkles text-yellow-300 text-xl"></i>' +
                '<div class="flex-1">' +
                    '<div class="font-extrabold">' + data.newly_awarded.length + ' New Badge' + (data.newly_awarded.length > 1 ? 's' : '') + ' Earned!</div>' +
                    '<div class="text-xs opacity-90 font-semibold">Tap here to view your achievements</div>' +
                '</div>' +
                '<i class="fa-solid fa-chevron-right text-xs opacity-75"></i>';
            banner.addEventListener('click', function () {
                haptic(30);
                activeStatus = 'earned';
                renderGridOnly();
            });
            content.appendChild(banner);
        }

        // 3. Search & Filter Controls Container
        var controls = document.createElement('div');
        controls.className = 'badge-controls-wrap';

        // Search Input
        var searchBox = document.createElement('div');
        searchBox.className = 'badge-search-box';
        searchBox.innerHTML =
            '<i class="fa-solid fa-magnifying-glass search-icon"></i>' +
            '<input type="text" class="badge-search-input" placeholder="Search achievements..." value="' + esc(searchQuery) + '" aria-label="Search badges">' +
            (searchQuery ? '<button class="badge-search-clear" aria-label="Clear search"><i class="fa-solid fa-xmark"></i></button>' : '');

        var searchInput = searchBox.querySelector('.badge-search-input');
        searchInput.addEventListener('input', function (e) {
            searchQuery = e.target.value;
            var clearBtn = searchBox.querySelector('.badge-search-clear');
            if (searchQuery && !clearBtn) {
                var btn = document.createElement('button');
                btn.className = 'badge-search-clear';
                btn.setAttribute('aria-label', 'Clear search');
                btn.innerHTML = '<i class="fa-solid fa-xmark"></i>';
                btn.addEventListener('click', function () {
                    searchQuery = '';
                    searchInput.value = '';
                    btn.remove();
                    renderGridOnly();
                });
                searchBox.appendChild(btn);
            } else if (!searchQuery && clearBtn) {
                clearBtn.remove();
            }
            renderGridOnly();
        });

        var existingClear = searchBox.querySelector('.badge-search-clear');
        if (existingClear) {
            existingClear.addEventListener('click', function () {
                searchQuery = '';
                searchInput.value = '';
                existingClear.remove();
                renderGridOnly();
            });
        }
        controls.appendChild(searchBox);

        // Status Tabs (All / Earned / Locked)
        var statusBar = document.createElement('div');
        statusBar.className = 'badge-status-bar';

        var earnedTotal = allBadges.filter(function (b) { return b.granted; }).length;
        var lockedTotal = allBadges.length - earnedTotal;

        var statusOptions = [
            { id: 'all', label: 'All (' + allBadges.length + ')' },
            { id: 'earned', label: '<i class="fa-solid fa-check mr-1 text-emerald-400"></i> Earned (' + earnedTotal + ')' },
            { id: 'locked', label: '<i class="fa-solid fa-lock mr-1 text-slate-400"></i> Locked (' + lockedTotal + ')' }
        ];

        statusOptions.forEach(function (opt) {
            var btn = document.createElement('button');
            btn.className = 'badge-status-btn' + (activeStatus === opt.id ? ' active' : '');
            btn.innerHTML = opt.label;
            btn.addEventListener('click', function () {
                haptic(20);
                activeStatus = opt.id;
                statusBar.querySelectorAll('.badge-status-btn').forEach(function (b) { b.classList.remove('active'); });
                btn.classList.add('active');
                renderGridOnly();
            });
            statusBar.appendChild(btn);
        });
        controls.appendChild(statusBar);

        // Category Filter Pills (Horizontal Scrolling)
        var categoryScroll = document.createElement('div');
        categoryScroll.className = 'badge-filter-scroll';

        var categoriesMap = {};
        allBadges.forEach(function (b) {
            var cat = b.category || 'Milestones';
            if (!categoriesMap[cat]) categoriesMap[cat] = { total: 0, earned: 0 };
            categoriesMap[cat].total++;
            if (b.granted) categoriesMap[cat].earned++;
        });

        var categoryList = ['all'].concat(Object.keys(categoriesMap));
        categoryList.forEach(function (catKey) {
            var pill = document.createElement('button');
            pill.className = 'badge-filter-pill' + (activeCategory === catKey ? ' active' : '');

            var iconClass = CATEGORY_ICONS[catKey] || 'fa-tag';
            var labelText = catKey === 'all' ? 'All Badges' : catKey;
            var countHTML = '';
            if (catKey === 'all') {
                countHTML = '<span class="pill-count">' + earnedCount + '/' + totalCount + '</span>';
            } else if (categoriesMap[catKey]) {
                countHTML = '<span class="pill-count">' + categoriesMap[catKey].earned + '/' + categoriesMap[catKey].total + '</span>';
            }

            pill.innerHTML = '<i class="fa-solid ' + esc(iconClass) + '"></i><span>' + esc(labelText) + '</span>' + countHTML;
            pill.addEventListener('click', function () {
                haptic(20);
                activeCategory = catKey;
                categoryScroll.querySelectorAll('.badge-filter-pill').forEach(function (p) { p.classList.remove('active'); });
                pill.classList.add('active');
                renderGridOnly();
            });
            categoryScroll.appendChild(pill);
        });
        controls.appendChild(categoryScroll);

        content.appendChild(controls);

        // 4. Badges Grid Container Anchor
        var gridContainer = document.createElement('div');
        gridContainer.id = 'badge-items-container';
        content.appendChild(gridContainer);

        renderGridOnly();
    };

    // Filter and render the grid
    function renderGridOnly() {
        var container = document.getElementById('badge-items-container');
        if (!container || !lastData) return;
        container.innerHTML = '';

        var badges = lastData.badges || [];
        var query = searchQuery.trim().toLowerCase();

        var filtered = badges.filter(function (b) {
            // Category filter
            if (activeCategory !== 'all' && b.category !== activeCategory) return false;
            // Status filter
            if (activeStatus === 'earned' && !b.granted) return false;
            if (activeStatus === 'locked' && b.granted) return false;
            // Search query filter
            if (query) {
                var nameMatch = (b.name || '').toLowerCase().includes(query);
                var descMatch = (b.description || '').toLowerCase().includes(query);
                var catMatch = (b.category || '').toLowerCase().includes(query);
                if (!nameMatch && !descMatch && !catMatch) return false;
            }
            return true;
        });

        if (!filtered.length) {
            var noResults = document.createElement('div');
            noResults.className = 'text-center py-12 px-4';
            noResults.innerHTML =
                '<div class="w-16 h-16 rounded-full bg-slate-800 border border-slate-700 mx-auto flex items-center justify-center text-2xl text-slate-500 mb-3">' +
                    '<i class="fa-solid fa-filter-circle-xmark"></i>' +
                '</div>' +
                '<div class="text-base font-bold text-slate-200 mb-1">No matching badges</div>' +
                '<p class="text-xs text-slate-400 font-semibold mb-4">Try clearing filters or search terms.</p>' +
                '<button class="px-4 py-2 bg-slate-800 border border-slate-600 rounded-xl text-xs font-bold text-slate-200 hover:bg-slate-700 transition-all" id="clear-badge-filters-btn">' +
                    'Reset Filters' +
                '</button>';
            var clearBtn = noResults.querySelector('#clear-badge-filters-btn');
            if (clearBtn) {
                clearBtn.addEventListener('click', function () {
                    searchQuery = '';
                    activeCategory = 'all';
                    activeStatus = 'all';
                    window.renderBadges(lastData);
                });
            }
            container.appendChild(noResults);
            return;
        }

        var grid = document.createElement('div');
        grid.className = 'badge-grid';

        filtered.forEach(function (b) {
            var tile = document.createElement('div');
            tile.className = 'badge-tile ' + (b.granted ? 'earned' : 'locked');
            tile.setAttribute('role', 'button');
            tile.setAttribute('tabindex', '0');
            tile.setAttribute('aria-label', b.name + ' - ' + (b.granted ? 'Earned' : 'Locked') + ' - Tap for details');

            var iconClass = normalizeIcon(b.icon);
            var progress = b.progress || {};
            var pct = Math.min(100, Math.max(0, progress.pct || 0));

            var badgeHTML =
                '<div class="badge-medallion">' +
                    '<i class="' + esc(iconClass) + '"></i>' +
                    (b.granted
                        ? '<div class="badge-mini-check"><i class="fa-solid fa-check"></i></div>'
                        : '<div class="badge-mini-lock"><i class="fa-solid fa-lock"></i></div>') +
                '</div>' +
                '<div class="badge-name">' + esc(b.name) + '</div>' +
                '<div class="badge-cat">' + esc(b.category) + '</div>' +
                '<div class="badge-points"><i class="fa-solid fa-star"></i> ' + (b.points || 0) + ' pts</div>';

            if (!b.granted && pct > 0) {
                badgeHTML +=
                    '<div class="badge-tile-bar" title="' + pct + '% complete">' +
                        '<div class="badge-tile-bar-fill" style="width: ' + pct + '%;"></div>' +
                    '</div>';
            }

            tile.innerHTML = badgeHTML;

            tile.addEventListener('click', function () {
                haptic(20);
                window.showBadgeDetail(b);
            });
            tile.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    haptic(20);
                    window.showBadgeDetail(b);
                }
            });

            grid.appendChild(tile);
        });

        container.appendChild(grid);
    }

    // Duolingo-style Achievement Modal
    window.showBadgeDetail = function (b) {
        var modalRoot = document.getElementById('badges-modal-root');
        if (!modalRoot) return;

        var iconClass = normalizeIcon(b.icon);
        var whenAwarded = '';
        if (b.granted && b.awarded_at) {
            try {
                whenAwarded = new Date(b.awarded_at).toLocaleDateString(undefined, {
                    year: 'numeric', month: 'short', day: 'numeric'
                });
            } catch (e) { whenAwarded = ''; }
        }

        var progress = b.progress || {};
        var pct = Math.min(100, Math.max(0, progress.pct || 0));

        var modalOverlay = document.createElement('div');
        modalOverlay.className = 'duo-badge-modal-overlay';
        modalOverlay.setAttribute('role', 'dialog');
        modalOverlay.setAttribute('aria-modal', 'true');
        modalOverlay.setAttribute('aria-label', b.name);

        var modalContent =
            '<div class="duo-badge-modal-card">' +
                '<button class="duo-badge-modal-close" aria-label="Close modal"><i class="fa-solid fa-xmark"></i></button>' +
                '<div class="duo-badge-modal-medallion ' + (b.granted ? 'earned' : 'locked') + '">' +
                    '<i class="' + esc(iconClass) + '"></i>' +
                '</div>' +
                '<h3 class="duo-badge-modal-title">' + esc(b.name) + '</h3>' +
                '<div class="duo-badge-modal-pills">' +
                    '<span class="duo-badge-modal-pill"><i class="fa-solid ' + esc(CATEGORY_ICONS[b.category] || 'fa-tag') + ' mr-1"></i>' + esc(b.category) + '</span>' +
                    '<span class="duo-badge-modal-pill"><i class="fa-solid fa-star text-amber-400 mr-1"></i>' + (b.points || 0) + ' pts</span>' +
                '</div>' +
                '<p class="duo-badge-modal-desc">' + esc(b.description || '') + '</p>' +
                '<div class="duo-badge-modal-status-box">';

        if (b.granted) {
            modalContent +=
                '<div class="duo-badge-modal-status-title earned">' +
                    '<i class="fa-solid fa-circle-check text-emerald-400 text-base"></i> ' +
                    '<span>Unlocked & Earned!</span>' +
                '</div>' +
                '<div class="text-xs text-slate-300 font-bold">' +
                    (whenAwarded ? 'Earned on ' + esc(whenAwarded) : 'Congratulations on completing this goal!') +
                '</div>';
        } else {
            modalContent +=
                '<div class="duo-badge-modal-status-title locked">' +
                    '<i class="fa-solid fa-lock text-pink-400 text-base"></i> ' +
                    '<span>In Progress (' + pct + '%)</span>' +
                '</div>' +
                '<div class="duo-badge-modal-progress-text">' +
                    (progress.text ? esc(progress.text) : 'Keep logging activities to unlock.') +
                '</div>' +
                '<div class="duo-badge-track mb-1.5">' +
                    '<div class="duo-badge-fill" style="width: ' + pct + '%;"></div>' +
                '</div>' +
                '<div class="text-right text-[11px] font-extrabold text-slate-400">' + pct + '% to Goal</div>';
        }

        modalContent +=
                '</div>' +
                '<button class="duo-badge-modal-btn" id="duo-badge-modal-action-btn">' +
                    (b.granted ? 'Awesome!' : 'Got it!') +
                '</button>' +
            '</div>';

        modalOverlay.innerHTML = modalContent;

        function closeModalHandler() {
            haptic(15);
            modalOverlay.classList.remove('open');
            setTimeout(function () {
                if (modalOverlay.parentNode) modalOverlay.parentNode.removeChild(modalOverlay);
            }, 250);
            document.removeEventListener('keydown', handleKey);
        }

        function handleKey(e) {
            if (e.key === 'Escape') closeModalHandler();
        }

        modalOverlay.querySelector('.duo-badge-modal-close').addEventListener('click', closeModalHandler);
        modalOverlay.querySelector('#duo-badge-modal-action-btn').addEventListener('click', closeModalHandler);
        modalOverlay.addEventListener('click', function (e) {
            if (e.target === modalOverlay) closeModalHandler();
        });

        document.addEventListener('keydown', handleKey);
        modalRoot.innerHTML = '';
        modalRoot.appendChild(modalOverlay);

        // Trigger transition
        requestAnimationFrame(function () {
            modalOverlay.classList.add('open');
        });

        if (b.granted && b.newly_awarded) {
            confetti();
        }
    };

    function closeBadgeModal() {
        var modalRoot = document.getElementById('badges-modal-root');
        if (modalRoot) modalRoot.innerHTML = '';
    }
})();



