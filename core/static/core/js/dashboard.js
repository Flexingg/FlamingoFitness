/* ============================================================
   Flamingo Fitness - Main Dashboard Controller (dashboard.js)
   ------------------------------------------------------------
   Architecture Overview:
   - Primary orchestrator for the single-page application (SPA) shell.
   - Fetches and renders player gamification state from `GET /api/v1/dashboard/state`.
   - Renders the interactive Skill Tree (S-curve path connecting Recovery,
     Strength, Endurance, Hydration, Nutrition, and PR Boss nodes).
   - Manages top HUD: Streak, Level, Total XP, Energy, Tokens, Scraps, Buffs.
   - Orchestrates lazy panel loading (`/panel/<name>/`) and script injection
     via `ensurePanelLoaded` and `ensureSinglePanelVisible`.
   - Coordinates with `router.js` (`window.AppRouter`) for client URL hash syncing.
   - Integrates with the Flutter Native Bridge (`window.FlamingoNative`) for haptics,
     avatar updates, and notifications.
   ============================================================ */

(function () {
    'use strict';

    /**
     * Metadata mapping for the 5 primary fitness modalities and their DOM nodes.
     */
    var MODALITY_META = {
        strength:  { node: 'node-strength',  cls: 'node-strength' },
        endurance: { node: 'node-endurance', cls: 'node-endurance' },
        nutrition: { node: 'node-nutrition', cls: 'node-nutrition' },
        hydration: { node: 'node-hydration', cls: 'node-hydration' },
        recovery:  { node: 'node-recovery',  cls: 'node-recovery' }
    };

    /**
     * Complete list of registered panel view DOM IDs.
     * Used by `hideAllPanels()` to ensure mutual exclusivity when switching views.
     */
    var PANEL_IDS = ['skill-tree', 'nutrition-view', 'hydration-view',
        'endurance-view', 'strength-view', 'boss-view', 'recovery-view',
        'shop-view', 'loadout-view', 'battle-view', 'pvp-view',
        'badges-view', 'leagues-view', 'bounties-view'];

    /**
     * Maps each panel view to its corresponding bottom-nav highlight tab ID.
     */
    var PANEL_NAV = {
        'skill-tree': 'nav-path',
        'nutrition-view': 'nav-path', 'hydration-view': 'nav-path',
        'endurance-view': 'nav-path', 'strength-view': 'nav-path',
        'boss-view': 'nav-path', 'recovery-view': 'nav-path',
        'shop-view': 'nav-shop', 'loadout-view': 'nav-shop',
        'battle-view': 'nav-battle', 'pvp-view': 'nav-battle',
        'badges-view': 'nav-badges', 'leagues-view': 'nav-leagues',
        'bounties-view': 'nav-battle'
    };

    /**
     * Hides all open panel views and loading hints.
     * Prevents panels from stacking or bleeding underneath one another.
     */
    window.hideAllPanels = function () {
        PANEL_IDS.forEach(function (id) {
            var el = document.getElementById(id);
            if (el) el.classList.add('hidden');
        });
        var hint = document.getElementById('loading-hint');
        if (hint) hint.classList.add('hidden');
        var err = document.getElementById('error-hint');
        if (err) err.classList.add('hidden');
    };

    /**
     * Synchronizes active tab highlights on the bottom navigation bar.
     * Maps views to Command, Arena, Shop, Leagues, or Badges.
     * @param {string} id - Target navigation tab element ID (e.g. 'nav-path', 'nav-shop')
     */
    window.setActiveNav = function (id) {
        var remap = {
            'nav-loadout': 'nav-shop',
            'nav-pvp': 'nav-battle',
            'nav-bounties': 'nav-battle',
            'nav-game': 'nav-battle'
        };
        var target = remap[id] || id;
        var items = document.querySelectorAll('.bottom-nav .nav-item');
        for (var i = 0; i < items.length; i++) {
            items[i].classList.toggle('active', items[i].id === target);
        }
    };

    function closeGameMenu() {
        var menu = document.getElementById('game-menu');
        if (menu) menu.classList.add('hidden');
        var btn = document.getElementById('nav-game');
        if (btn) { btn.classList.remove('open'); btn.setAttribute('aria-expanded', 'false'); }
    }

    // Center FAB: open/close the radial Game menu (keeps the bottom bar a single
    // short row instead of two stacked rows of tabs).
    window.toggleGameMenu = function (event) {
        if (event) event.stopPropagation();
        var menu = document.getElementById('game-menu');
        if (!menu) return;
        if (menu.classList.contains('hidden')) {
            menu.classList.remove('hidden');
            var btn = document.getElementById('nav-game');
            if (btn) { btn.classList.add('open'); btn.setAttribute('aria-expanded', 'true'); }
        } else {
            closeGameMenu();
        }
    };

    window.gotoGame = function (fnName) {
        closeGameMenu();
        var fn = window[fnName];
        if (typeof fn === 'function') fn();
    };

    // Close the Game menu when tapping anywhere outside it.
    function onDocClick(ev) {
        var menu = document.getElementById('game-menu');
        var wrap = document.getElementById('game-btn-wrap');
        if (!menu || menu.classList.contains('hidden')) return;
        if ((wrap && wrap.contains(ev.target)) || menu.contains(ev.target)) return;
        closeGameMenu();
    }
    document.addEventListener('click', onDocClick);

    // Dynamic SVG S-curve path that connects exact center of each bubble
    window.updateSkillTreePath = function () {
        var tree = document.getElementById('skill-tree');
        if (!tree || tree.classList.contains('hidden')) return;
        var svg = tree.querySelector('.skill-tree-path-svg');
        var pathBg = tree.querySelector('.skill-path-bg');
        var pathFg = tree.querySelector('.skill-path-fg');
        if (!svg || !pathBg || !pathFg) return;

        var nodeIds = ['node-nutrition', 'node-hydration', 'node-endurance', 'node-strength', 'node-recovery', 'node-boss'];
        var treeRect = tree.getBoundingClientRect();
        if (treeRect.width <= 0 || treeRect.height <= 0) return;

        var points = [];
        for (var i = 0; i < nodeIds.length; i++) {
            var btn = document.getElementById(nodeIds[i]);
            if (!btn) continue;
            var circle = btn.querySelector('.node-circle') || btn;
            var rect = circle.getBoundingClientRect();
            var cx = rect.left + rect.width / 2 - treeRect.left;
            var cy = rect.top + rect.height / 2 - treeRect.top;
            points.push({ x: cx, y: cy });
        }

        if (points.length < 2) return;

        var d = 'M ' + points[0].x.toFixed(1) + ' ' + points[0].y.toFixed(1);
        for (var p = 0; p < points.length - 1; p++) {
            var p0 = points[p];
            var p1 = points[p + 1];
            var midY = (p0.y + p1.y) / 2;
            d += ' C ' + p0.x.toFixed(1) + ' ' + midY.toFixed(1) + ', ' +
                 p1.x.toFixed(1) + ' ' + midY.toFixed(1) + ', ' +
                 p1.x.toFixed(1) + ' ' + p1.y.toFixed(1);
        }

        svg.removeAttribute('viewBox');
        svg.style.width = treeRect.width + 'px';
        svg.style.height = treeRect.height + 'px';
        pathBg.setAttribute('d', d);
        pathFg.setAttribute('d', d);
    };

    // Path tab: return to the skill tree from anywhere. Because this is an
    // explicit "go home", clear the URL so a later back press doesn't
    // resurrect a deep page the user had already left.
    window.showPath = function () {
        if (window.closeModal) window.closeModal();
        window.hideAllPanels();
        var tree = document.getElementById('skill-tree');
        if (tree) tree.classList.remove('hidden');
        window.setActiveNav('nav-path');
        if (window.AppRouter) window.AppRouter.navigate('skill-tree');
        setTimeout(window.updateSkillTreePath, 40);
    };

    // Go back through the browser/app history. Falls back to the skill tree
    // when there is no history to walk (e.g. the view was opened directly).
    window.goBack = function () {
        if (window.closeModal) window.closeModal();
        if (window.AppRouter) { window.AppRouter.back(); return; }
        window.setActiveNav('nav-path');
    };

    // Ensure only one panel is visible at a time when navigating. This
    // replaces the stacking behavior where multiple panels could be visible.
    // Also records the switch in the browser history via the router so the
    // back button can return to the previous panel.
    window.ensureSinglePanelVisible = function (visiblePanelId) {
        window.hideAllPanels();
        var navId = PANEL_NAV[visiblePanelId] || 'nav-path';
        window.setActiveNav(navId);

        var showEl = function (panel) {
            if (panel) {
                panel.classList.remove('hidden');
                panel.classList.remove('panel-view-enter');
                void panel.offsetWidth; // trigger reflow
                panel.classList.add('panel-view-enter');
            }
        };

        var panel = document.getElementById(visiblePanelId);
        if (panel) {
            showEl(panel);
        } else if (typeof window.ensurePanelLoaded === 'function') {
            window.ensurePanelLoaded(visiblePanelId).then(function (loadedPanel) {
                showEl(loadedPanel || document.getElementById(visiblePanelId));
            });
        }
        if (window.AppRouter) window.AppRouter.navigate(visiblePanelId);
    };

    function showError(message) {
        var hint = document.getElementById('loading-hint');
        var err = document.getElementById('error-hint');
        if (hint) hint.classList.add('hidden');
        if (err) {
            err.textContent = message;
            err.classList.remove('hidden');
        }
    }

    function renderState(data) {
        // Top nav stats with smooth roll-up numbers
        var streakEl = document.querySelector('#stat-streak span');
        var tokensEl = document.querySelector('#stat-tokens span');
        var staminaEl = document.querySelector('#stat-stamina span');
        if (window.animateNumber) {
            window.animateNumber(streakEl, streakEl ? streakEl.textContent : 0, data.user.streak);
            window.animateNumber(tokensEl, tokensEl ? tokensEl.textContent : 0, data.resources.tokens);
            window.animateNumber(staminaEl, staminaEl ? staminaEl.textContent : 0, data.resources.stamina);
        } else {
            if (streakEl) streakEl.textContent = data.user.streak;
            if (tokensEl) tokensEl.textContent = data.resources.tokens;
            if (staminaEl) staminaEl.textContent = data.resources.stamina;
        }

        // Streak flame evolutions
        var streakBadge = document.getElementById('stat-streak');
        if (streakBadge) {
            streakBadge.classList.remove('streak-tier-1', 'streak-tier-2', 'streak-tier-3');
            var s = data.user.streak || 0;
            if (s >= 30) {
                streakBadge.classList.add('streak-tier-3');
                streakBadge.title = s + ' day streak! Supercharged!';
            } else if (s >= 7) {
                streakBadge.classList.add('streak-tier-2');
                streakBadge.title = s + ' day streak! On Fire!';
            } else {
                streakBadge.classList.add('streak-tier-1');
                streakBadge.title = s + ' day streak';
            }
        }

        var avSrc = data.user.avatar || 'https://api.dicebear.com/7.x/avataaars/svg?seed=Flamingo';
        document.getElementById('avatar-img').src = avSrc;
        document.getElementById('avatar-img').onerror = function () {
            this.onerror = null;
            this.src = 'https://api.dicebear.com/7.x/avataaars/svg?seed=Flamingo';
        };
        if (window.FlamingoNative && window.FlamingoNative.setAvatar) {
            window.FlamingoNative.setAvatar(avSrc);
        }

        // 1. Hero Readiness Gauge & Status Ring
        if (data.readiness) {
            var score = Math.round(Number(data.readiness.score) || 70);
            var scoreEl = document.getElementById('readiness-score-num');
            if (scoreEl) scoreEl.textContent = score;

            var gaugeRing = document.getElementById('readiness-gauge-ring');
            if (gaugeRing) {
                var circumference = 251.32; // 2 * PI * 40
                var offset = circumference * (1 - Math.min(100, Math.max(0, score)) / 100);
                gaugeRing.style.strokeDashoffset = offset;
                if (score >= 80) {
                    gaugeRing.style.stroke = '#22c55e'; // Emerald
                } else if (score >= 60) {
                    gaugeRing.style.stroke = '#FF5E9A'; // Flamingo
                } else {
                    gaugeRing.style.stroke = '#f59e0b'; // Amber
                }
            }

            var statusBadge = document.getElementById('readiness-status-text');
            var tierBadge = document.getElementById('readiness-tier-badge');
            if (statusBadge) {
                if (score >= 80) {
                    statusBadge.textContent = 'Prime Status';
                    if (tierBadge) tierBadge.className = 'inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-black bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 uppercase tracking-wide';
                } else if (score >= 60) {
                    statusBadge.textContent = 'Active Recovery';
                    if (tierBadge) tierBadge.className = 'inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-black bg-flamingo/20 text-flamingo border border-flamingo/30 uppercase tracking-wide';
                } else {
                    statusBadge.textContent = 'Rest Mandate';
                    if (tierBadge) tierBadge.className = 'inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-black bg-amber-500/20 text-amber-300 border border-amber-500/30 uppercase tracking-wide';
                }
            }

            var headingEl = document.getElementById('readiness-heading');
            if (headingEl) {
                headingEl.textContent = (score >= 80) ? 'High Readiness Primed' : ((score >= 60) ? 'Command Center Ready' : 'Rest Day Protocol');
            }

            var msgEl = document.getElementById('readiness-message');
            if (msgEl && data.readiness.message) {
                msgEl.textContent = data.readiness.message;
            }
        }

        // 2. Modality Cyber Cards & Status Bars
        var bossUnlocked = false;
        for (var key in MODALITY_META) {
            if (!MODALITY_META.hasOwnProperty(key)) continue;
            var meta = MODALITY_META[key];
            var card = document.getElementById(meta.node);
            if (!card) continue;
            var tree = (data.skill_trees && data.skill_trees[key]) || null;

            var lvlEl = document.getElementById('node-lvl-' + key);
            var barEl = document.getElementById('modality-bar-' + key);
            var pctEl = document.getElementById('modality-pct-' + key);
            var todayXpEl = document.getElementById('modality-today-xp-' + key);
            var checkEl = document.getElementById('node-check-' + key);
            var dotEl = document.getElementById('dot-' + key);

            if (tree) {
                var pct = Math.min(100, Math.max(0, tree.progress_pct || 0));
                var todayXp = tree.today_xp || 0;
                var isCompletedToday = todayXp > 0 || pct >= 100;

                if (lvlEl && tree.level !== undefined) {
                    lvlEl.textContent = 'Lv ' + tree.level;
                }
                if (barEl) {
                    barEl.style.width = pct + '%';
                }
                if (pctEl) {
                    pctEl.textContent = Math.round(pct) + '% to next Lv';
                }
                if (todayXpEl) {
                    todayXpEl.textContent = '+' + todayXp + ' XP today';
                    if (todayXp > 0) {
                        todayXpEl.classList.add('text-emerald-300');
                    }
                }
                if (checkEl) {
                    checkEl.classList.toggle('hidden', !isCompletedToday);
                }
                if (dotEl) {
                    if (isCompletedToday) {
                        dotEl.className = 'w-2.5 h-2.5 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.7)] transition-all';
                    } else {
                        dotEl.className = 'w-2.5 h-2.5 rounded-full bg-slate-700 transition-all';
                    }
                }
                card.classList.toggle('active-completed', isCompletedToday);
            }
            if (tree && tree.progress_pct >= 100 && key === 'strength') {
                bossUnlocked = true;
            }
        }

        // PR Boss card state
        var boss = document.getElementById('node-boss');
        if (boss && bossUnlocked) {
            boss.classList.add('border-amber-400/50');
        }

        // 3. Determine which node needs focus today (lowest XP today)
        var PRIORITY = ['recovery', 'strength', 'endurance', 'hydration', 'nutrition'];
        var lowestKey = 'recovery';
        var lowestXP = Infinity;

        for (var p = 0; p < PRIORITY.length; p++) {
            var currKey = PRIORITY[p];
            var xpToday = (data.skill_trees && data.skill_trees[currKey]) ? (data.skill_trees[currKey].today_xp || 0) : 0;
            if (xpToday < lowestXP) {
                lowestXP = xpToday;
                lowestKey = currKey;
            }
        }

        PRIORITY.forEach(function (k) {
            var b = document.getElementById('node-' + k);
            if (b) b.classList.remove('needs-focus');
        });

        // Highlight focus node with subtle glow
        var targetCard = document.getElementById('node-' + lowestKey);
        if (targetCard && lowestXP === 0) {
            targetCard.classList.add('needs-focus');
        }

        // Refresh campaign spotlight
        if (window.refreshCampaignFocus) {
            window.refreshCampaignFocus();
        }

        var loadingHint = document.getElementById('loading-hint');
        if (loadingHint) loadingHint.classList.add('hidden');
        var anyOtherPanelVisible = PANEL_IDS.some(function (id) {
            if (id === 'skill-tree') return false;
            var el = document.getElementById(id);
            return el && !el.classList.contains('hidden');
        });
        if (!anyOtherPanelVisible) {
            var tree = document.getElementById('skill-tree');
            if (tree) tree.classList.remove('hidden');
        }

        // First-flight onboarding
        if (data.onboarded === false && window.startOnboarding) {
            window.startOnboarding();
        }
    }

    // ------------------------------------------------------------------
    // Fast 1-Tap Quick Logging Dock & Milestone Toast
    // ------------------------------------------------------------------
    window.quickLogWater = function (amountOz) {
        amountOz = amountOz || 24;
        var btn = document.getElementById('btn-quick-water');
        var origHtml = btn ? btn.innerHTML : '';
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin text-cyan-400"></i><span class="text-xs font-black">Logging...</span>';
        }
        var csrf = window.csrfToken ? window.csrfToken() : '';
        if (!csrf) {
            var m = document.querySelector('meta[name="csrf-token"]');
            if (m && m.content && m.content !== 'NOTPROVIDED') csrf = m.content;
        }
        fetch('/api/v1/hydration/water/add', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrf
            },
            body: JSON.stringify({ amount_oz: amountOz })
        })
        .then(function (res) {
            if (!res.ok) throw new Error(res.status);
            return res.json();
        })
        .then(function () {
            if (window.showMilestoneToast) {
                window.showMilestoneToast('+' + amountOz + ' oz Logged! \uD83D\uDCA7');
            }
            if (window.haptic) window.haptic(30);
            if (window.refreshDashboardState) window.refreshDashboardState();
        })
        .catch(function (err) {
            window.ffWarn && window.ffWarn('[quickLogWater] failed:', err);
            if (window.showMilestoneToast) {
                window.showMilestoneToast('Could not log water');
            }
        })
        .finally(function () {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = origHtml;
            }
        });
    };

    window.showMilestoneToast = function (msg) {
        var toast = document.getElementById('milestone-toast');
        if (!toast) return;
        toast.textContent = msg;
        toast.classList.add('show');
        clearTimeout(toast._timer);
        toast._timer = setTimeout(function () {
            toast.classList.remove('show');
        }, 2200);
    };

    // ---- Simple modal helpers ----
    function addModal(title, desc, actionText) {
        document.getElementById('modal-title').textContent = title;
        document.getElementById('modal-desc').textContent = desc;
        document.getElementById('modal-action').textContent = actionText || 'OK';
        openModal();
    }
    window.addModal = addModal;

    function openModal() {
        document.getElementById('actionModal').classList.add('show-modal');
    }
    window.closeModal = function () {
        document.getElementById('actionModal').classList.remove('show-modal');
    };
    window.openModal = openModal;

    document.getElementById('actionModal').addEventListener('click', function (e) {
        if (e.target === this) window.closeModal();
    });
    document.getElementById('modal-action').addEventListener('click', function () {
        var btn = this;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Polling...';
        setTimeout(function () {
            btn.textContent = 'Saved \u2705';
            window.closeModal();
            setTimeout(function () { btn.textContent = 'Log via Liftosaur'; }, 800);
        }, 1200);
    });
    document.getElementById('nav-leagues').addEventListener('click', function (e) {
        // Phase 8 (docs/13): open the full Leagues/Challenges/Flock panel.
        // Safety net for the inline onclick on #nav-leagues (keeps the anchor
        // from scrolling to "#" if that handler is ever removed).
        if (window.loadLeagues) {
            e.preventDefault();
            window.loadLeagues();
            window.setActiveNav('nav-leagues');
        }
    });

    // ---- Help popovers (tap an info icon for a small explainer) ----
    function escHtml(s) { return window.escHtml(s); }

    window.closeHelpBubble = function () {
        var b = document.getElementById('help-bubble');
        if (b) b.remove();
        var bd = document.getElementById('help-backdrop');
        if (bd) bd.remove();
    };

    window.showHelpAt = function (anchor, htmlContent) {
        window.closeHelpBubble();
        var backdrop = document.createElement('div');
        backdrop.id = 'help-backdrop';
        backdrop.className = 'help-backdrop';
        backdrop.addEventListener('click', function (e) {
            e.stopPropagation();
            window.closeHelpBubble();
        });
        document.body.appendChild(backdrop);

        var bubble = document.createElement('div');
        bubble.id = 'help-bubble';
        bubble.className = 'help-bubble';
        bubble.setAttribute('role', 'tooltip');
        bubble.innerHTML = '<div class="help-bubble-head"><span class="help-bubble-title"><i class="fa-solid fa-circle-info mr-1"></i>Tip</span>' +
            '<button type="button" class="help-close" aria-label="Close help" onclick="window.closeHelpBubble()"><i class="fa-solid fa-xmark"></i></button></div>' +
            '<div class="help-bubble-body">' + htmlContent + '</div>';
        document.body.appendChild(bubble);

        var rect = anchor.getBoundingClientRect();
        var vw = document.documentElement.clientWidth || 360;
        var bw = Math.min(300, vw - 24);
        bubble.style.maxWidth = bw + 'px';
        var left = Math.max(12, Math.min(vw - bw - 12, rect.left));
        var top = rect.bottom + 8;
        var bh = bubble.offsetHeight || 130;
        if (top + bh > (window.innerHeight - 12)) top = Math.max(12, rect.top - bh - 8);
        bubble.style.left = left + 'px';
        bubble.style.top = Math.max(12, top) + 'px';
    };

    window.bindHelp = function (root) {
        if (!root) return;
        Array.prototype.forEach.call(root.querySelectorAll('[data-help]'), function (el) {
            el.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
                window.showHelpAt(el, el.getAttribute('data-help'));
            });
        });
    };

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            if (document.getElementById('help-bubble')) window.closeHelpBubble();
            if (document.getElementById('onboarding-overlay')) window.finishOnboarding();
        }
    });

    // ---- Shared empty-state component (docs/17 #92) ----
    // Builds a consistent "why no data + what to do" card with an optional CTA.
    // Most panel controllers call window.showEmptyState() in their render*()
    // empty branches; string-building controllers use window.emptyStateHTML().

    window.emptyStateHTML = function (opts) {
        opts = opts || {};
        var ctaHtml = '';
        if (opts.ctaText) {
            var cls = 'empty-state-cta' + (opts.secondary ? ' secondary' : '');
            if (typeof opts.ctaAction === 'function') {
                ctaHtml = '<button type="button" class="' + cls + '" data-empty-cta="1">' + escHtml(opts.ctaText) + '</button>';
            } else if (opts.ctaOnClick) {
                ctaHtml = '<button type="button" class="' + cls + '" onclick="' + opts.ctaOnClick + '">' + escHtml(opts.ctaText) + '</button>';
            } else if (opts.ctaHref) {
                ctaHtml = '<a href="' + escHtml(opts.ctaHref) + '" class="' + cls + '">' + escHtml(opts.ctaText) + '</a>';
            }
        }
        return '<div class="empty-state">' +
            (opts.icon ? '<div class="empty-state-icon"><i class="fa-solid ' + escHtml(opts.icon) + '"></i></div>' : '') +
            (opts.title ? '<p class="empty-state-title">' + escHtml(opts.title) + '</p>' : '') +
            (opts.desc ? '<p class="empty-state-desc">' + escHtml(opts.desc) + '</p>' : '') +
            (opts.hint ? '<p class="empty-state-hint">' + escHtml(opts.hint) + '</p>' : '') +
            ctaHtml + '</div>';
    };

    // Inject the empty-state card into a container (typically the *-empty divs).
    // When opts.ctaAction is a function it is bound to the rendered CTA button.
    window.showEmptyState = function (el, opts) {
        if (!el) return;
        opts = opts || {};
        el.innerHTML = window.emptyStateHTML(opts);
        if (typeof opts.ctaAction === 'function') {
            var btn = el.querySelector('[data-empty-cta]');
            if (btn) btn.addEventListener('click', function (e) {
                e.preventDefault();
                opts.ctaAction();
            });
        }
    };

    var onboardingShown = false;
    var onboardingEl = null;
    var onboardingIndex = 0;

    var ONBOARDING_STEPS = [
        {
            icon: 'fa-seedling',
            kicker: 'Welcome to Flamingo Fitness',
            title: 'Your training, turned into a game',
            desc: 'Everything you already do - lifting, cardio, nutrition, hydration and sleep - earns XP for your skill trees. This is the loop you will be living in.',
            hint: 'Five skill trees. One daily loop.'
        },
        {
            icon: 'fa-sitemap',
            kicker: '1 / Skill trees',
            title: 'Train hard, level up',
            desc: 'Each modality is its own skill tree. Log a workout, drink water or hit your macros and you earn XP toward the next level of that tree.',
            hint: 'Tap any colored node on the home screen.'
        },
        {
            icon: 'fa-dice-d6',
            kicker: '2 / Tokens & loot',
            title: 'Spend tokens, pull gear',
            desc: 'Earned XP can turn into tokens. Open packs in the Shop (the Game button) to pull gear that boosts your damage and stats.',
            hint: 'Tokens buy packs. Packs drop gear.',
            ctaText: 'Open the Shop',
            action: 'shop'
        },
        {
            icon: 'fa-dragon',
            kicker: '3 / Sieges',
            title: 'Beat the campaign bosses',
            desc: 'Use stamina to attack PvE siege bosses. Your daily activity provides the damage and your loadout multiplies it.',
            hint: 'Each attack costs 1 stamina.',
            ctaText: 'Open the Battle',
            action: 'battle'
        },
        {
            icon: 'fa-shield-halved',
            kicker: '4 / PvP',
            title: 'Claim and defend gyms',
            desc: 'Take rival gyms, hold the turf and climb the ladder. Consistency and gear decide every fight.',
            hint: 'You are all set. Go train!',
            ctaText: 'Open PvP',
            action: 'pvp'
        }
    ];
    // ---- Guided first-flight onboarding (docs/17 #91) ----
    // A walkthrough modal sequence built on .modal-overlay/.modal-content
    // (styled in dashboard.css). ONBOARDING_STEPS drive the copy; steps with an
    // `action` deep-link to that REAL panel so first-time users touch the Shop,
    // Battle and PvP screens before the tour ends.

    function onboardingActionMap(name) {
        var map = { shop: 'loadShop', battle: 'loadBattle', pvp: 'loadPvP' };
        return map[name] || null;
    }

    function renderOnboardingOverlay() {
        if (!onboardingEl) return;
        if (onboardingIndex < 0 || onboardingIndex >= ONBOARDING_STEPS.length) return;
        var step = ONBOARDING_STEPS[onboardingIndex];
        var last = onboardingIndex === ONBOARDING_STEPS.length - 1;

        var dotsHtml = '';
        for (var d = 0; d < ONBOARDING_STEPS.length; d++) {
            dotsHtml += '<span class="onboarding-dot' + (d === onboardingIndex ? ' active' : '') + '" aria-hidden="true"></span>';
        }

        var bodyHtml = '<div class="onboarding-card">' +
            '<div class="onboarding-icon"><i class="fa-solid ' + escHtml(step.icon || 'fa-dice-d6') + '"></i></div>' +
            '<div class="onboarding-kicker">' + escHtml(step.kicker || '') + '</div>' +
            '<div class="onboarding-title">' + escHtml(step.title || '') + '</div>' +
            '<div class="onboarding-desc">' + escHtml(step.desc || '') +
            (step.hint ? '<br><br><i>' + escHtml(step.hint) + '</i>' : '') + '</div>' +
            '<div class="onboarding-dots">' + dotsHtml + '</div>';

        var actionsHtml;
        if (step.action) {
            actionsHtml = '<div class="onboarding-actions">' +
                '<button type="button" class="onboarding-next" id="onboarding-cta">' + escHtml(step.ctaText || 'Lets go') + '</button>' +
                '<button type="button" class="onboarding-skip" id="onboarding-skip">Skip</button>' +
                '</div>';
        } else {
            actionsHtml = '<div class="onboarding-actions">' +
                '<button type="button" class="onboarding-next" id="onboarding-next">' + (last ? 'Finish' : 'Next') + '</button>' +
                '<button type="button" class="onboarding-skip" id="onboarding-skip">Skip</button>' +
                '</div>';
        }

        var body = document.getElementById('onboarding-body');
        if (body) body.innerHTML = bodyHtml + actionsHtml;

        var nextBtn = document.getElementById('onboarding-next');
        var ctaBtn = document.getElementById('onboarding-cta');
        var skipBtn = document.getElementById('onboarding-skip');
        if (nextBtn) nextBtn.onclick = function () { window.advanceOnboarding(); };
        if (skipBtn) skipBtn.onclick = function () { window.finishOnboarding(); };
        if (ctaBtn) ctaBtn.onclick = function () {
            var fn = onboardingActionMap(step.action);
            if (fn && window[fn]) {
                window[fn]();
                setTimeout(window.advanceOnboarding, 400);
            } else {
                window.advanceOnboarding();
            }
        };
    }

    window.advanceOnboarding = function () {
        if (onboardingIndex < ONBOARDING_STEPS.length - 1) {
            onboardingIndex++;
            renderOnboardingOverlay();
        } else {
            window.finishOnboarding();
        }
    };

    // Persist completion (POST /api/v1/onboarded) whether the user finishes or
    // skips, then tear down the overlay so the tour never reappears this session.
    window.finishOnboarding = function () {
        onboardingShown = true;
        var overlay = document.getElementById('onboarding-overlay');
        if (overlay) { overlay.classList.remove('show-modal'); overlay.remove(); }
        onboardingEl = null;
        var csrf = window.csrfToken ? window.csrfToken() : '';
        fetch('/api/v1/onboarded', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'X-CSRFToken': csrf, 'Content-Type': 'application/json' }
        }).catch(function () { /* best-effort; persisted on the next load */ });
    };

    window.startOnboarding = function () {
        if (onboardingShown || onboardingEl || !ONBOARDING_STEPS.length) return;
        onboardingShown = true;
        onboardingIndex = 0;
        var overlay = document.createElement('div');
        overlay.id = 'onboarding-overlay';
        overlay.className = 'modal-overlay';
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');
        overlay.setAttribute('aria-label', 'Welcome to Flamingo Fitness - guided tour');
        overlay.innerHTML = '<div class="modal-content onboarding-content rounded-[2rem] p-6 border border-slate-600 shadow-2xl w-[90%] max-w-sm m-auto"><div id="onboarding-body"></div></div>';
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) window.finishOnboarding();
        });
        document.body.appendChild(overlay);
        requestAnimationFrame(function () { overlay.classList.add('show-modal'); });
        onboardingEl = overlay;
        renderOnboardingOverlay();
    };

    // ---- Path page: active campaign focus bar ----
    function focusCampaignIcon(c) {
        return { cardio: 'fa-heart-pulse', strength: 'fa-dumbbell', nutrition: 'fa-apple-whole',
            hydration: 'fa-droplet', sleep: 'fa-moon' }[c] || 'fa-dragon';
    }
    function fmoney(n) { return window.fmoney(n); }
    function vulnChipLite(v) {
        v = Number(v) || 1;
        if (v >= 1.99) return '<span class="vuln-chip weak"><i class="fa-solid fa-bullseye"></i>2&times; weak</span>';
        if (v <= 0.51) return '<span class="vuln-chip resist"><i class="fa-solid fa-shield"></i>&frac12; resists</span>';
        return '';
    }

    function renderCampaignFocus(slot, data) {
        slot.innerHTML = '';
        if (!data || !data.campaigns) return;
        var wallet = data.wallet || {};
        var stamina = (wallet.stamina == null ? 0 : wallet.stamina);
        var cap = (wallet.stamina_cap == null ? 3 : wallet.stamina_cap);
        var camps = data.campaigns || [];
        var active = camps.filter(function (c) { return c.engaged && !c.conquered; });
        var html;

        if (active.length === 0) {
            var allDone = camps.length > 0 && camps.every(function (c) { return c.conquered; });
            if (allDone) {
                html = '<div class="path-focus-card done">' +
                    '<div class="path-focus-head" style="justify-content:center"><i class="fa-solid fa-trophy text-yellow-400"></i>' +
                    '<span class="path-focus-title">All campaigns conquered!</span></div>' +
                    '<p class="path-focus-desc">You cleared every boss. New battles arrive over time - keep training to stay sharp.</p></div>';
                slot.innerHTML = html;
                return;
            }
            var best = null;
            camps.forEach(function (c) {
                if (c.conquered || !c.boss || !c.boss.slug) return;
                if (!best || (c.est_damage_per_attack || 0) > (best.est_damage_per_attack || 0)) best = c;
            });
            if (!best) return;
            var bhelp = 'No boss is engaged yet. Best opening: the ' + escHtml(best.label) + ' camp, which deals the most damage from today tracked activity. Tap Fight now, then Engage and Attack (1 stamina each).';
            html = '<div class="path-focus-card">' +
                '<div class="path-focus-head">' +
                    '<i class="fa-solid ' + focusCampaignIcon(best.campaign) + ' path-focus-icon"></i>' +
                    '<div class="flex-1"><div class="path-focus-title">Ready to start a siege</div>' +
                    '<div class="path-focus-sub">' + escHtml(best.label) + ' camp</div></div>' +
                    '<button type="button" class="help-trigger" data-help="' + escHtml(bhelp) + '" aria-label="Help"><i class="fa-solid fa-circle-question"></i></button>' +
                '</div>' +
                '<p class="path-focus-desc">Best opening: <b>' + escHtml(best.boss.name) + '</b> in the ' + escHtml(best.label) + ' camp - you deal ~' + fmoney(best.est_damage_per_attack) + ' per attack today.</p>' +
                '<div class="path-focus-actions"><button type="button" class="path-focus-fight" onclick="window.loadBattle(); return false;"><i class="fa-solid fa-dragon mr-1"></i>Fight now</button></div>' +
                '</div>';
            slot.innerHTML = html;
            window.bindHelp(slot);
            return;
        }

        var chosen = active[0];
        active.forEach(function (c) {
            var a = (c.attacks_to_win == null ? Infinity : c.attacks_to_win);
            var b = (chosen.attacks_to_win == null ? Infinity : chosen.attacks_to_win);
            if (a < b) chosen = c;
            else if (a === b && (c.est_damage_per_attack || 0) > (chosen.est_damage_per_attack || 0)) chosen = c;
        });
        var rem = Math.max(0, (chosen.total_hp || 0) - (chosen.damage_dealt || 0));
        var progPct = chosen.total_hp ? Math.max(0, Math.min(100, Math.round(((chosen.damage_dealt || 0) / chosen.total_hp) * 100))) : 0;
        var atkText = (chosen.attacks_to_win == null) ? 'keep attacking' : '~' + chosen.attacks_to_win + ' hits left at this power';
        var fhelp = 'This is the boss closest to falling. Keep attacking (1 stamina each) to stack damage on its HP. Your damage per hit comes from today tracked ' + escHtml(chosen.label) + ' activity times your gear. Stamina refills each morning (cap ' + cap + ').';
        html = '<div class="path-focus-card active">' +
            '<div class="path-focus-head">' +
                '<i class="fa-solid ' + focusCampaignIcon(chosen.campaign) + ' path-focus-icon"></i>' +
                '<div class="flex-1"><div class="path-focus-title">Focus: ' + escHtml(chosen.boss.name) + '</div>' +
                '<div class="path-focus-sub">' + escHtml(chosen.label) + ' campaign &middot; ' + atkText + '</div></div>' +
                '<button type="button" class="help-trigger" data-help="' + escHtml(fhelp) + '" aria-label="Help"><i class="fa-solid fa-circle-question"></i></button>' +
            '</div>' +
            '<div class="mt-3 h-3 bg-slate-700 rounded-full overflow-hidden border border-slate-600">' +
                '<div class="h-full rounded-full bg-red-500" style="width:' + progPct + '%"></div></div>' +
            '<div class="flex justify-between text-xs mt-1">' +
                '<span class="text-slate-400 font-semibold">' + fmoney(rem) + ' / ' + fmoney(chosen.total_hp) + ' HP</span>' +
                '<span class="text-slate-300 font-bold">' + fmoney(chosen.est_damage_per_attack) + ' dmg/atk</span></div>' +
            '<p class="path-focus-desc">To beat it: build today ' + escHtml(chosen.label) + ' activity, then Attack with stamina (' + stamina + '/' + cap + ' now). ' + vulnChipLite(chosen.vulnerability) + '</p>' +
            '<div class="path-focus-actions"><button type="button" class="path-focus-fight" onclick="window.loadBattle(); return false;"><i class="fa-solid fa-bolt mr-1"></i>Fight now</button></div>' +
            '</div>';
        slot.innerHTML = html;
        window.bindHelp(slot);
    }

    window.refreshCampaignFocus = function () {
        var slot = document.getElementById('path-campaign-focus');
        if (!slot) return;
        fetch('/api/v1/battle/state', { credentials: 'same-origin' })
            .then(function (res) { return res.ok ? res.json() : null; })
            .then(function (data) { renderCampaignFocus(slot, data); })
            .catch(function () { slot.innerHTML = ''; });
    };

    // Refresh the top-nav shell (streak / tokens / stamina) after any mutation
    // in the Shop / Battle / PvP controllers. Always returns the parsed state.
    window.refreshDashboardState = function () {
        return fetch('/api/v1/dashboard/state', { credentials: 'same-origin' })
            .then(function (res) {
                if (res.status === 401 || res.status === 403) {
                    throw new Error('not-authenticated');
                }
                return res.ok ? res.json() : Promise.reject(res.status);
            })
            .then(renderState)
            .catch(function (err) {
                if (err && err.message === 'not-authenticated') {
                    showError('Please log in via the admin panel to view your dashboard.');
                } else {
                    showError('Could not load your dashboard. Is the API running? (Error ' + err + ')');
                }
            });
    };

    // ------------------------------------------------------------------
    // Pull-to-refresh handler (Phase 3, docs/19 #18)
    // ------------------------------------------------------------------
    function initPullToRefresh() {
        var scroller = document.querySelector('main');
        if (!scroller) return;

        var startY = 0;
        var currentY = 0;
        var isPulling = false;
        var threshold = 70;

        var indicator = document.createElement('div');
        indicator.className = 'ptr-indicator';
        indicator.innerHTML = '<div class="ptr-icon"><i class="fa-solid fa-arrows-rotate fa-spin"></i></div>';
        scroller.prepend(indicator);

        scroller.addEventListener('touchstart', function (e) {
            if (scroller.scrollTop <= 0) {
                startY = e.touches[0].clientY;
                isPulling = true;
            }
        }, { passive: true });

        scroller.addEventListener('touchmove', function (e) {
            if (!isPulling) return;
            currentY = e.touches[0].clientY;
            var deltaY = currentY - startY;
            if (deltaY > 0 && scroller.scrollTop <= 0) {
                if (deltaY > threshold) {
                    indicator.classList.add('ptr-pulling');
                } else {
                    indicator.classList.remove('ptr-pulling');
                }
            }
        }, { passive: true });

        scroller.addEventListener('touchend', function () {
            if (!isPulling) return;
            var deltaY = currentY - startY;
            isPulling = false;
            if (deltaY > threshold && scroller.scrollTop <= 0) {
                indicator.classList.add('ptr-refreshing');
                window.haptic(15);
                window.refreshDashboardState();
                if (window.refreshCampaignFocus) window.refreshCampaignFocus();
                setTimeout(function () {
                    indicator.classList.remove('ptr-refreshing', 'ptr-pulling');
                }, 800);
            } else {
                indicator.classList.remove('ptr-pulling');
            }
            startY = 0;
            currentY = 0;
        }, { passive: true });
    }

    // ------------------------------------------------------------------
    // Mobile Bottom Sheet swipe-to-dismiss gesture
    // ------------------------------------------------------------------
    function initBottomSheetGestures() {
        var overlays = document.querySelectorAll('.modal-overlay');
        overlays.forEach(function (overlay) {
            var content = overlay.querySelector('.modal-content');
            if (!content) return;

            var startY = 0;
            var currentY = 0;
            var isDragging = false;

            content.addEventListener('touchstart', function (e) {
                if (content.scrollTop <= 0) {
                    startY = e.touches[0].clientY;
                    isDragging = true;
                }
            }, { passive: true });

            content.addEventListener('touchmove', function (e) {
                if (!isDragging) return;
                currentY = e.touches[0].clientY;
                var deltaY = currentY - startY;
                if (deltaY > 0 && content.scrollTop <= 0) {
                    content.style.transform = 'translateY(' + deltaY + 'px)';
                }
            }, { passive: true });

            content.addEventListener('touchend', function () {
                if (!isDragging) return;
                var deltaY = currentY - startY;
                isDragging = false;
                if (deltaY > 90) {
                    content.style.transform = '';
                    overlay.classList.remove('show-modal');
                } else {
                    content.style.transform = '';
                }
                startY = 0;
                currentY = 0;
            }, { passive: true });
        });
    }

    // ---- Boot: fetch dashboard state + campaign focus on page load ----
    window.refreshDashboardState();
    if (window.refreshCampaignFocus) window.refreshCampaignFocus();
    initPullToRefresh();
    initBottomSheetGestures();
    window.addEventListener('resize', window.updateSkillTreePath);

    // ------------------------------------------------------------------
    // Lazy-load stubs for non-critical controllers (Phase 1, docs/19 #4).
    // These stub functions are replaced by the real controllers when their
    // scripts finish loading. The mapping comes from LAZY_SCRIPT_URLS in
    // the template and loadScript() from utils.js.
    // ------------------------------------------------------------------
    var LAZY_KEYS = ['shop', 'loadout', 'battle', 'pvp', 'badges', 'leagues', 'bounties'];
    LAZY_KEYS.forEach(function (key) {
        var fnName = 'load' + key.charAt(0).toUpperCase() + key.slice(1);
        if (key === 'loadout') fnName = 'loadLoadout';
        if (key === 'pvp') fnName = 'loadPvP';
        if (key === 'bounties') fnName = 'loadBounties';
        window[fnName] = window[fnName] || function () {
            var url = window.LAZY_SCRIPT_URLS && window.LAZY_SCRIPT_URLS[key];
            if (!url) return;
            window.loadScript(url).then(function () {
                if (typeof window[fnName] === 'function') window[fnName]();
            });
        };
    });

    window.closeStatModal = function () {
        var modal = document.getElementById('statModal');
        if (modal) modal.classList.remove('show-modal');
    };

    window.showStatInfo = function (stat) {
        var url = window.LAZY_SCRIPT_URLS && window.LAZY_SCRIPT_URLS.stat_info;
        if (!url) return;
        return window.loadScript(url).then(function () {
            if (typeof window.showStatInfo === 'function') {
                window.showStatInfo(stat);
            }
        });
    };
})();
