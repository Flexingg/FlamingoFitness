/* ============================================================
   Flamingo Fitness - Synthesized Web Audio Effects (Roadmap #9)
   Pure Web Audio API oscillator synthesis (zero external audio files).
   Includes sound toggle and persistent mute preferences.
   ============================================================ */
(function () {
    'use strict';

    var AudioContextClass = window.AudioContext || window.webkitAudioContext;
    var ctx = null;
    var isMuted = localStorage.getItem('flamingo_sound_muted') === 'true';

    function getContext() {
        if (!ctx && AudioContextClass) {
            try {
                ctx = new AudioContextClass();
            } catch (e) {
                // AudioContext not supported
            }
        }
        if (ctx && ctx.state === 'suspended') {
            ctx.resume().catch(function () {});
        }
        return ctx;
    }

    // Auto-resume on first user gesture
    document.addEventListener('click', function unlockAudio() {
        if (ctx && ctx.state === 'suspended') {
            ctx.resume().catch(function () {});
        }
    }, { once: true });

    window.ffAudioMuted = function () {
        return isMuted;
    };

    window.ffAudioToggle = function () {
        isMuted = !isMuted;
        localStorage.setItem('flamingo_sound_muted', isMuted ? 'true' : 'false');
        updateAudioUI();
        if (!isMuted) {
            window.playButtonTap();
            if (window.showToast) window.showToast('Sound effects enabled 🔊', 'info');
        } else {
            if (window.showToast) window.showToast('Sound effects muted 🔇', 'info');
        }
        return isMuted;
    };

    function updateAudioUI() {
        var icons = document.querySelectorAll('.sound-toggle-icon, #sound-icon');
        icons.forEach(function (icon) {
            if (isMuted) {
                icon.className = 'fa-solid fa-volume-xmark text-slate-500';
            } else {
                icon.className = 'fa-solid fa-volume-high text-yellow-400';
            }
        });
    }
    window.updateAudioUI = updateAudioUI;

    // --- Sound Synthesis Helpers ---

    function playTone(freq, type, duration, gainVal, delay) {
        if (isMuted) return;
        var audioCtx = getContext();
        if (!audioCtx) return;

        try {
            delay = delay || 0;
            gainVal = gainVal || 0.15;
            var startTime = audioCtx.currentTime + delay;

            var osc = audioCtx.createOscillator();
            var gain = audioCtx.createGain();

            osc.type = type || 'sine';
            osc.frequency.setValueAtTime(freq, startTime);

            gain.gain.setValueAtTime(0.001, startTime);
            gain.gain.exponentialRampToValueAtTime(gainVal, startTime + 0.02);
            gain.gain.exponentialRampToValueAtTime(0.0001, startTime + duration);

            osc.connect(gain);
            gain.connect(audioCtx.destination);

            osc.start(startTime);
            osc.stop(startTime + duration + 0.05);
        } catch (e) {
            // Guard against audio context state errors
        }
    }

    // 1. XP Gain Chime (ascending arpeggio C5 -> E5 -> G5 -> C6)
    window.playXpChime = function () {
        if (isMuted) return;
        var notes = [523.25, 659.25, 783.99, 1046.50];
        notes.forEach(function (freq, i) {
            playTone(freq, 'sine', 0.18, 0.12, i * 0.07);
        });
    };

    // 2. Level Up Fanfare (triumphant melodic cadence with rich triangle/sine harmonics)
    window.playLevelUpFanfare = function () {
        if (isMuted) return;
        var chords = [
            { freqs: [523.25, 659.25], dur: 0.15, delay: 0.0 },   // C5 + E5
            { freqs: [587.33, 698.46], dur: 0.15, delay: 0.14 },  // D5 + F5
            { freqs: [659.25, 783.99], dur: 0.18, delay: 0.28 },  // E5 + G5
            { freqs: [783.99, 1046.50, 1318.51], dur: 0.55, delay: 0.44 } // G5 + C6 + E6 (Power Finale)
        ];
        chords.forEach(function (c) {
            c.freqs.forEach(function (f) {
                playTone(f, 'triangle', c.dur, 0.18, c.delay);
            });
        });
    };

    // 3. Badge Unlock Fanfare (sparkling high pitch fanfare)
    window.playBadgeFanfare = function () {
        if (isMuted) return;
        var notes = [587.33, 739.99, 880.00, 1174.66];
        notes.forEach(function (freq, i) {
            playTone(freq, 'sine', 0.25, 0.15, i * 0.08);
            playTone(freq * 1.5, 'triangle', 0.18, 0.06, i * 0.08);
        });
        // Finale sparkle
        setTimeout(function () {
            if (!isMuted) {
                playTone(1318.51, 'sine', 0.4, 0.18, 0);
                playTone(1567.98, 'sine', 0.45, 0.14, 0.05);
            }
        }, 360);
    };

    // 4. Gacha Roll / Dice Roll (tension ticks + reveal)
    window.playGachaRoll = function () {
        if (isMuted) return;
        for (var i = 0; i < 8; i++) {
            playTone(300 + (i * 45), 'triangle', 0.04, 0.08, i * 0.05);
        }
        setTimeout(function () {
            if (!isMuted) {
                playTone(659.25, 'sine', 0.35, 0.2, 0);
                playTone(1046.50, 'triangle', 0.45, 0.2, 0.05);
            }
        }, 450);
    };

    // 5. Button Tap / Click UI Sound
    window.playButtonTap = function () {
        if (isMuted) return;
        playTone(800, 'sine', 0.05, 0.08, 0);
    };

    // 6. Attack / Hit Sound (PvE Boss)
    window.playAttackHit = function () {
        if (isMuted) return;
        playTone(220, 'sawtooth', 0.12, 0.14, 0);
        playTone(110, 'sine', 0.2, 0.2, 0.02);
    };

    // Initialize UI on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', updateAudioUI);
    } else {
        updateAudioUI();
    }
})();
