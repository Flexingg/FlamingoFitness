/* Flamingo Club controller (Step 26). */
(function () {
    'use strict';
    var BASE_URL = '/base/';
    var audioCtx = null;
    function csrfToken() {
        var m = document.querySelector('meta[name="csrf-token"]');
        return m ? m.getAttribute('content') : '';
    }
    function ensureAudio() {
        if (!audioCtx) {
            try { audioCtx = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { audioCtx = null; }
        }
        return audioCtx;
    }
    function playTone(freq, type, duration) {
        try {
            var ctx = ensureAudio(); if (!ctx) return;
            var osc = ctx.createOscillator(); var gain = ctx.createGain();
            osc.type = type || 'sine'; osc.frequency.value = freq || 440;
            gain.gain.value = 0.08;
            osc.connect(gain); gain.connect(ctx.destination);
            osc.start();
            gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + (duration || 0.12));
            osc.stop(ctx.currentTime + (duration || 0.12) + 0.02);
        } catch (e) {}
    }
    function playCollect() { playTone(660, 'sine', 0.1); }
    function playCrit() { playTone(880, 'triangle', 0.18); }
    function haptic(ms) { if (navigator.vibrate) { navigator.vibrate(ms || 50); } }
    function hapticCrit() { if (navigator.vibrate) { navigator.vibrate([100, 50, 100]); } }
    function applyDayNight() {
        var h = new Date().getHours();
        if (h >= 18 || h < 6) { document.body.classList.add('theme-night'); }
        else { document.body.classList.remove('theme-night'); }
    }
    function postBase(path, body) {
        return fetch(BASE_URL + path, {
            method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
            body: JSON.stringify(body || {}),
        });
    }
    // Phase 8 (docs/13 §7.3): staff with REAL friends via the picker modal
    // (openFriendPicker is provided by leagues.js). Falls back to the legacy
    // prompt when leagues.js is not loaded.
    function postStaff(buildingId, friendId) {
        postBase('staff', { id: buildingId, friend_id: friendId })
            .then(function (r) { return r.json(); })
            .then(function (d) {
                if (d.ok) window.renderBase(d);
                else if (d.error) alert(d.error);
            })
            .catch(function () { alert('Staff failed.'); });
    }
    function staffWithFriendPicker(buildingId) {
        if (!window.openFriendPicker) {
            var fid = prompt('Staff with friend ID (leave blank to un-staff):', '');
            if (fid === null) return;
            postStaff(buildingId, fid ? parseInt(fid, 10) : null);
            return;
        }
        fetch('/api/v1/social/', { credentials: 'same-origin' })
            .then(function (res) { return res.ok ? res.json() : Promise.reject(res.status); })
            .then(function (social) {
                window.openFriendPicker({
                    title: 'Staff this building',
                    friends: social.friends || [],
                    allowClear: true,
                    onPick: function (friend) {
                        postStaff(buildingId, friend ? friend.id : null);
                    }
                });
            })
            .catch(function () { alert('Could not load your friends.'); });
    }
    window.backToBasePlan = function () {
        var view = document.getElementById('base-view');
        if (view) view.classList.add('hidden');
        // Single-panel navigation: hide ALL panels, then show only the skill tree.
        window.ensureSinglePanelVisible('skill-tree');
    };
    window.loadBase = function () {
        console.log('[base] loadBase start');
        var view = document.getElementById('base-view');
        var content = document.getElementById('base-content');
        var empty = document.getElementById('base-empty');
        var tree = document.getElementById('skill-tree');
        if (!view) return;
        applyDayNight();
        // Single-panel navigation: hide ALL panels, then show only the base.
        window.ensureSinglePanelVisible('base-view');
        content.classList.add('hidden');
        empty.classList.add('hidden');
        fetch(BASE_URL, { credentials: 'same-origin' })
            .then(function (res) {
                if (res.status === 401 || res.status === 403) throw new Error('not-authenticated');
                return res.ok ? res.json() : Promise.reject(res.status);
            })
            .then(function (data) {
                console.log('[base] state loaded, buildings=', data.buildings && data.buildings.length);
                window.renderBase(data);
            })
            .catch(function (err) {
                console.error('[base] fetch failed:', err);
                content.classList.remove('hidden');
                content.innerHTML = err && err.message === 'not-authenticated'
                    ? '<p class="error-hint">Please log in to view your base.</p>'
                    : '<p class="error-hint">Could not load base data (error ' + err + ').</p>';
            });
    };

    window.renderBase = function (data) {
        var content = document.getElementById('base-content');
        var empty = document.getElementById('base-empty');
        if (!content) return;
        var res = data.resources || {};
        var buildings = data.buildings || [];
        var unlockable = data.unlockable || [];
        var matEl = document.getElementById('stat-materials');
        var nrgEl = document.getElementById('stat-energy');
        if (matEl) matEl.querySelector('span').textContent = res.materials;
        if (nrgEl) nrgEl.querySelector('span').textContent = res.energy;
        if (!buildings.length && !unlockable.length) {
            content.classList.add('hidden'); empty.classList.remove('hidden'); return;
        }
        empty.classList.add('hidden');
        content.classList.remove('hidden');
        content.innerHTML = '';
        if (unlockable.length) {
            var uLabel = document.createElement('div');
            uLabel.className = 'base-section-title'; uLabel.textContent = 'Build';
            content.appendChild(uLabel);
            var uRow = document.createElement('div'); uRow.className = 'base-scroll-row';
            unlockable.forEach(function (u) {
                var card = document.createElement('div');
                card.className = 'building-card' + (u.locked ? ' building-locked' : '');
                card.innerHTML =
                    '<div class="building-name">' + esc(u.name) + '</div>' +
                    '<div class="building-cost">' + esc(u.base_cost_materials) + ' <i class="fa-solid fa-gem"></i> · ' + esc(u.base_cost_energy) + ' <i class="fa-solid fa-bolt"></i></div>' +
                    (u.locked ? '<div class="building-lock-reason"><i class="fa-solid fa-lock"></i> ' + esc(u.locked_reason || 'Locked') + '</div>' : '');
                if (!u.locked) {
                    card.style.cursor = 'pointer';
                    card.addEventListener('click', function () {
                        postBase('start', { slug: u.slug }).then(function (r) { return r.json(); })
                            .then(function (d) { if (d.ok) { playCollect(); haptic(50); window.renderBase(d); } })
                            .catch(function () { alert('Build failed.'); });
                    });
                }
                uRow.appendChild(card);
            });
            content.appendChild(uRow);
        }
        if (buildings.length) {
            var oLabel = document.createElement('div');
            oLabel.className = 'base-section-title'; oLabel.textContent = 'Your Club';
            content.appendChild(oLabel);
            var grid = document.createElement('div'); grid.className = 'base-grid';
            buildings.forEach(function (b) {
                var card = document.createElement('div');
                card.className = 'building-card building-owned';
                if (b.custom_color) { card.style.boxShadow = '0 0 0 3px ' + esc(b.custom_color) + '44'; }
                var statusText = b.status || '';
                if (b.is_constructing && b.construction_duration_hours) {
                    statusText = 'Constructing ' + b.construction_duration_hours + 'h';
                } else if (b.level >= 3 && b.branch_choices && Object.keys(b.branch_choices).length) {
                    statusText = 'Ready to evolve';
                }
                card.innerHTML =
                    '<div class="building-header">' +
                        '<div class="building-name">' + esc(b.name) + ' <span class="building-level">Lv' + esc(b.level) + '</span></div>' +
                        '<input type="color" class="building-color" value="' + esc(b.custom_color || '#FF69B4') + '" data-id="' + esc(b.id) + '">' +
                    '</div>' +
                    '<div class="building-status">' + esc(statusText) + '</div>' +
                    '<div class="building-accrued"><i class="fa-solid fa-gem"></i> ' + esc(b.accrued_materials) + ' ready</div>' +
                    '<div class="building-actions">' +
                        (b.level > 0 && !b.is_constructing ? '<button class="btn-flamingo btn-sm" data-action="collect" data-id="' + esc(b.id) + '">Collect</button>' : '') +
                        (b.is_constructing ? '<button class="btn-flamingo btn-sm btn-orange" data-action="speedup" data-id="' + esc(b.id) + '">Speed Up</button>' : '') +
                        (b.level >= 3 && b.branch_choices && Object.keys(b.branch_choices).length ? '<button class="btn-flamingo btn-sm btn-purple" data-action="evolve" data-id="' + esc(b.id) + '">Evolve</button>' : '') +
                        '<button class="btn-flamingo btn-sm btn-teal" data-action="staff" data-id="' + esc(b.id) + '">Staff</button>' +
                    '</div>' +
                    '<div class="staff-circle" data-id="' + esc(b.id) + '">' + (b.staff_friend_id ? '<i class="fa-solid fa-user"></i>' : '<i class="fa-solid fa-plus"></i>') + '</div>';

                var colorInput = card.querySelector('.building-color');
                if (colorInput) {
                    colorInput.addEventListener('change', function (e) {
                        postBase('customize', { id: b.id, color: e.target.value })
                            .then(function (r) { return r.json(); })
                            .then(function (d) { if (d.ok) window.renderBase(d); });
                    });
                }
                card.querySelectorAll('button[data-action]').forEach(function (btn) {
                    btn.addEventListener('click', function (e) {
                        e.stopPropagation();
                        var action = btn.getAttribute('data-action');
                        var id = parseInt(btn.getAttribute('data-id'), 10);
                        if (action === 'collect') {
                            postBase('collect', { id: id }).then(function (r) { return r.json(); })
                                .then(function (d) {
                                    if (d.ok) {
                                        if (d.was_crit) { playCrit(); hapticCrit(); } else { playCollect(); haptic(50); }
                                        window.renderBase(d);
                                    }
                                })
                                .catch(function () { alert('Collect failed.'); });
                        } else if (action === 'speedup') {
                            var hours = prompt('Speed up by how many hours?', '3');
                            if (hours === null) return;
                            postBase('speedup', { id: id, hours: parseInt(hours, 10) || 1 })
                                .then(function (r) { return r.json(); })
                                .then(function (d) { if (d.ok) { playCollect(); haptic(50); window.renderBase(d); } })
                                .catch(function () { alert('Speedup failed.'); });
                        } else if (action === 'evolve') {
                            var keys = Object.keys(b.branch_choices || {});
                            var choice = prompt('Evolve into: ' + keys.join(' / '), keys[0] || '');
                            if (!choice) return;
                            postBase('evolve', { id: id, chosen_slug: choice })
                                .then(function (r) { return r.json(); })
                                .then(function (d) { if (d.ok) { playCollect(); haptic(50); window.renderBase(d); } })
                                .catch(function () { alert('Evolve failed.'); });
                        } else if (action === 'staff') {
                            staffWithFriendPicker(id);
                        }
                    });
                });
                var staffCircle = card.querySelector('.staff-circle');
                if (staffCircle) {
                    staffCircle.addEventListener('click', function () {
                        staffWithFriendPicker(b.id);
                    });
                }
                grid.appendChild(card);
            });
            content.appendChild(grid);
        }
        if (data.base_level >= 5 && data.base_level % 5 === 0) {
            postBase('milestone', {})
                .then(function (r) { return r.json(); })
                .then(function (d) {
                    if (d && d.celebrated) {
                        if (typeof confetti === 'function') {
                            confetti({ particleCount: 120, spread: 70, origin: { y: 0.6 } });
                        }
                        playCrit(); hapticCrit();
                    }
                })
                .catch(function () {});
        }
    };
    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\"/g, '&quot;');
    }
    applyDayNight();
    setInterval(applyDayNight, 60000);
})();

