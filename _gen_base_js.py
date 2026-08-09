part1 = "head = open('core/static/core/js/base.js', encoding='utf-8').read()\n"
part2 = "tail = '''\n"
part3 = "    window.renderBase = function (data) {\n"
part4 = "        var content = document.getElementById('base-content');\n"
part5 = "        var empty = document.getElementById('base-empty');\n"

import os
head = open('core/static/core/js/base.js', encoding='utf-8').read()
chunk = '\n    window.renderBase = function (data) {\n        var content = document.getElementById("base-content");\n        var empty = document.getElementById("base-empty");\n        if (!content) return;\n        var res = data.resources || {};\n        var buildings = data.buildings || [];\n        var unlockable = data.unlockable || [];\n        var matEl = document.getElementById("stat-materials");\n        var nrgEl = document.getElementById("stat-energy");\n        if (matEl) matEl.querySelector("span").textContent = res.materials;\n        if (nrgEl) nrgEl.querySelector("span").textContent = res.energy;\n        if (!buildings.length && !unlockable.length) {\n            content.classList.add("hidden"); empty.classList.remove("hidden"); return;\n        }\n        empty.classList.add("hidden");\n        content.classList.remove("hidden");\n        content.innerHTML = "";\n        if (unlockable.length) {\n            var uLabel = document.createElement("div");\n            uLabel.className = "base-section-title"; uLabel.textContent = "Build";\n            content.appendChild(uLabel);\n            var uRow = document.createElement("div"); uRow.className = "base-scroll-row";\n            unlockable.forEach(function (u) {\n                var card = document.createElement("div");\n                card.className = "building-card" + (u.locked ? " building-locked" : "");\n                card.innerHTML =\n                    "<div class=\\"building-name\\">" + esc(u.name) + "</div>" +\n                    "<div class=\\"building-cost\\">" + esc(u.base_cost_materials) + " <i class=\\"fa-solid fa-gem\\"></i> · " + esc(u.base_cost_energy) + " <i class=\\"fa-solid fa-bolt\\"></i></div>" +\n                    (u.locked ? "<div class=\\"building-lock-reason\\"><i class=\\"fa-solid fa-lock\\"></i> " + esc(u.locked_reason || "Locked") + "</div>" : "");\n                if (!u.locked) {\n                    card.style.cursor = "pointer";\n                    card.addEventListener("click", function () {\n                        postBase("start", { slug: u.slug }).then(function (r) { return r.json(); })\n                            .then(function (d) { if (d.ok) { playCollect(); haptic(50); window.renderBase(d); } })\n                            .catch(function () { alert("Build failed."); });\n                    });\n                }\n                uRow.appendChild(card);\n            });\n            content.appendChild(uRow);\n        }\n'
with open('_tail1.txt', 'w', encoding='utf-8') as f:
    f.write(chunk)
print('wrote tail1', len(chunk))

head = """/* Flamingo Club controller (Step 26). */
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
    window.backToBasePlan = function () {
        var view = document.getElementById('base-view');
        if (view) view.classList.add('hidden');
        var tree = document.getElementById('skill-tree');
        if (tree) tree.classList.remove('hidden');
    };
    window.loadBase = function () {
        console.log('[base] loadBase start');
        var view = document.getElementById('base-view');
        var content = document.getElementById('base-content');
        var empty = document.getElementById('base-empty');
        var tree = document.getElementById('skill-tree');
        if (!view) return;
        applyDayNight();
        if (tree) tree.classList.add('hidden');
        view.classList.remove('hidden');
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
"""

with open('core/static/core/js/base.js', 'w', encoding='utf-8') as f:
    f.write(head)
print('wrote head')
