/* ============================================================
   Flamingo Fitness - vanilla JS dashboard controller
   Fetches /api/v1/dashboard/state and renders the shell.
   Reference: docs/02_api_contracts.md, docs/04_frontend_architecture.md
   ============================================================ */

(function () {
    'use strict';

    var MODALITY_META = {
        strength:  { node: 'node-strength',  cls: 'node-strength' },
        endurance: { node: 'node-endurance', cls: 'node-endurance' },
        nutrition: { node: 'node-nutrition', cls: 'node-nutrition' },
        hydration: { node: 'node-hydration', cls: 'node-hydration' },
        recovery:  { node: 'node-recovery',  cls: 'node-recovery' }
    };

    // Every panel that can be opened from the bottom nav / skill-tree nodes.
    var PANEL_IDS = ['skill-tree', 'nutrition-view', 'hydration-view',
        'endurance-view', 'strength-view', 'boss-view', 'recovery-view',
        'shop-view', 'loadout-view', 'battle-view', 'pvp-view',
        'badges-view', 'leagues-view'];

    // Maps each panel to the bottom-nav tab it belongs to (used when restoring
    // a previous view so the active nav highlight stays in sync).
    var PANEL_NAV = {
        'skill-tree': 'nav-path',
        'nutrition-view': 'nav-path', 'hydration-view': 'nav-path',
        'endurance-view': 'nav-path', 'strength-view': 'nav-path',
        'boss-view': 'nav-path', 'recovery-view': 'nav-path',
        'shop-view': 'nav-shop', 'loadout-view': 'nav-loadout',
        'battle-view': 'nav-battle', 'pvp-view': 'nav-pvp',
        'badges-view': 'nav-badges', 'leagues-view': 'nav-leagues'
    };

    // Panel history is tracked by the browser via AppRouter (router.js), which
    // records the active panel in the URL fragment so back/forward work naturally.
    // Hide ALL panels so opening a new one REPLACES the current view instead
    // of stacking underneath it (Phase 8 bug-fix).
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

    // Bottom-nav active-tab management. The four combat views (Shop/Loadout/
    // Battle/PvP) live behind the center "Game" FAB, so opening any of them
    // highlights the Game button instead of a (now removed) standalone tab.
    window.setActiveNav = function (id) {
        var remap = {
            'nav-shop': 'nav-game', 'nav-loadout': 'nav-game',
            'nav-battle': 'nav-game', 'nav-pvp': 'nav-game'
        };
        var target = remap[id] || id;
        var items = document.querySelectorAll('.bottom-nav .nav-item');
        for (var i = 0; i < items.length; i++) {
            items[i].classList.toggle('active', items[i].id === target);
        }
        var gameBtn = document.getElementById('nav-game');
        if (gameBtn) gameBtn.classList.toggle('active', target === 'nav-game');
        var menu = document.getElementById('game-menu');
        if (menu) menu.classList.add('hidden');
        if (gameBtn) gameBtn.classList.remove('open');
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
        if (wrap && wrap.contains(ev.target)) return;
        closeGameMenu();
    }
    document.addEventListener('click', onDocClick);

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
        var panel = document.getElementById(visiblePanelId);
        if (panel) {
            panel.classList.remove('hidden');
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
        // Top nav stats
        document.querySelector('#stat-streak span').textContent = data.user.streak;
        document.querySelector('#stat-tokens span').textContent = data.resources.tokens;
        document.querySelector('#stat-stamina span').textContent = data.resources.stamina;
        document.getElementById('avatar-img').src = data.user.avatar || 'https://api.dicebear.com/7.x/avataaars/svg?seed=Flamingo';
        // Add onerror fallback so broken uploaded images revert to the cartoon default.
        document.getElementById('avatar-img').onerror = function () {
            this.onerror = null;
            this.src = 'https://api.dicebear.com/7.x/avataaars/svg?seed=Flamingo';
        };

        // Skill tree nodes - every node is always unlocked/clickable. The UI
        // must never present a locked skill tree, so we force-clear any lock
        // styling/icons regardless of whether the API returns data for the
        // modality yet.
        var bossUnlocked = false;
        for (var key in MODALITY_META) {
            if (!MODALITY_META.hasOwnProperty(key)) continue;
            var meta = MODALITY_META[key];
            var btn = document.getElementById(meta.node);
            if (!btn) continue;
            var tree = (data.skill_trees && data.skill_trees[key]) || null;

            btn.classList.add(meta.cls);
            btn.classList.remove('node-locked', 'opacity-70');
            var lockIcon = btn.querySelector('.fa-lock');
            if (lockIcon) lockIcon.remove();

            // Clean up any old injected badges/bars before re-adding
            var oldBadge = btn.querySelector('.node-level');
            if (oldBadge) oldBadge.remove();
            var oldXpWrap = btn.querySelector('.node-xp-wrap');
            if (oldXpWrap) oldXpWrap.remove();

            if (tree && tree.level !== undefined) {
                var badge = document.createElement('span');
                badge.className = 'node-level';
                badge.textContent = 'Lv ' + tree.level;
                btn.appendChild(badge);
            }
            // Add XP progress bar under each skill tree node
            if (tree && tree.xp !== undefined) {
                var xpWrap = document.createElement('div');
                xpWrap.className = 'node-xp-wrap';
                var xpBar = document.createElement('div');
                xpBar.className = 'node-xp-bar';
                var xpFill = document.createElement('div');
                xpFill.className = 'node-xp-fill';
                xpFill.style.width = Math.min(100, Math.max(0, tree.progress_pct || 0)) + '%';
                xpBar.appendChild(xpFill);
                xpWrap.appendChild(xpBar);
                var xpText = document.createElement('div');
                xpText.className = 'node-xp-text';
                xpText.textContent = (tree.xp || 0) + ' / 100 XP';
                xpWrap.appendChild(xpText);
                btn.appendChild(xpWrap);
            }
            if (tree && tree.progress_pct >= 100 && key === 'strength') {
                bossUnlocked = true;
            }
        }
        var boss = document.getElementById('node-boss');
        if (boss) {
            // The PR Boss is always visible/clickable too (no lock).
            boss.classList.remove('node-locked', 'opacity-70');
            var bossLock = boss.querySelector('.fa-lock');
            if (bossLock) bossLock.remove();
            if (bossUnlocked) {
                boss.classList.add('node-strength');
            }
        }

        // Determine which node is worst today (lowest XP today).
        // Tiebreaker priority: Recovery 1st, Strength 2nd, Endurance 3rd, Hydration 4th, Nutrition 5th, PR Boss last.
        var PRIORITY = ['recovery', 'strength', 'endurance', 'hydration', 'nutrition', 'boss'];
        var lowestKey = 'recovery';
        var lowestXP = Infinity;

        for (var p = 0; p < PRIORITY.length; p++) {
            var currKey = PRIORITY[p];
            var xpToday = 0;
            if (currKey === 'boss') {
                xpToday = (data.skill_trees && data.skill_trees['boss']) ? (data.skill_trees['boss'].today_xp || 0) : 0;
            } else {
                xpToday = (data.skill_trees && data.skill_trees[currKey]) ? (data.skill_trees[currKey].today_xp || 0) : 0;
            }
            if (xpToday < lowestXP) {
                lowestXP = xpToday;
                lowestKey = currKey;
            }
        }

        // Reset pulse/bounce classes from all nodes
        PRIORITY.forEach(function (k) {
            var b = document.getElementById('node-' + k);
            if (b) {
                b.classList.remove('animate-bounce-slight');
                var circle = b.querySelector('.node-circle') || b.querySelector('div');
                if (circle) {
                    circle.classList.remove('ring-4', 'ring-flamingo/30', 'shadow-[0_0_25px_rgba(255,94,154,0.5)]');
                }
            }
        });

        // Apply pulse to the lowest XP node
        var targetNode = document.getElementById('node-' + lowestKey);
        if (targetNode) {
            targetNode.classList.add('animate-bounce-slight');
            var targetCircle = targetNode.querySelector('.node-circle') || targetNode.querySelector('div');
            if (targetCircle) {
                targetCircle.classList.add('ring-4', 'ring-flamingo/30', 'shadow-[0_0_25px_rgba(255,94,154,0.5)]');
            }
        }

        document.getElementById('loading-hint').classList.add('hidden');
        document.getElementById('skill-tree').classList.remove('hidden');

        // First-flight onboarding (docs/17 #91): show the walkthrough for any
        // account that has not completed it yet. Demo users are pre-marked
        // onboarded in create_demo_accounts so they never see it.
        if (data.onboarded === false && window.startOnboarding) {
            window.startOnboarding();
        }

    }

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
    function escHtml(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

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
    function csrfToken() {
        var m = document.querySelector('meta[name="csrf-token"]');
        return m ? m.content : '';
    }
    window.csrfToken = csrfToken;

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
    function fmoney(n) {
        return String(Number(n) || 0).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    }
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

    // ---- Boot: fetch dashboard state + campaign focus on page load ----
    window.refreshDashboardState();
    if (window.refreshCampaignFocus) window.refreshCampaignFocus();
})();

