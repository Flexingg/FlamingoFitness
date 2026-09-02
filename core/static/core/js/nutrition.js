/* Nutrition detail panel controller & Snap-to-Log System (Sparky Fitness Backend).
 * Uses window.createModalityController() factory.
 */
(function () {
    'use strict';

    function formatMacro(value, goal) {
        return Math.round(value || 0) + (goal !== undefined ? '/' + Math.round(goal || 0) : '');
    }

    function getCookie(name) {
        var cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            var cookies = document.cookie.split(';');
            for (var i = 0; i < cookies.length; i++) {
                var cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    function getStatusBadge(day) {
        if (!day) return { cls: 'imperfect-badge', text: 'Needs work' };
        if (day.perfect) {
            return { cls: 'perfect-badge', text: 'PERFECT' };
        }
        if (day.status === 'close' || (day.xp >= 35)) {
            return { cls: 'close-badge', text: 'NEAR GOAL' };
        }
        if (day.status === 'partial' || (day.xp > 0)) {
            return { cls: 'partial-badge', text: 'PROGRESS' };
        }
        return { cls: 'imperfect-badge', text: 'Needs work' };
    }

    function buildMacroBar(label, pct, valStr, color) {
        var row = document.createElement('div');
        row.style.marginBottom = '10px';
        var top = document.createElement('div');
        top.style.display = 'flex';
        top.style.justifyContent = 'space-between';
        top.style.fontSize = '0.82rem';
        top.style.fontWeight = '800';
        top.style.marginBottom = '4px';

        var lbl = document.createElement('span');
        lbl.textContent = label;
        lbl.style.color = '#e2e8f0';

        var val = document.createElement('span');
        val.textContent = valStr;
        val.style.color = color;

        top.appendChild(lbl);
        top.appendChild(val);
        row.appendChild(top);

        var track = document.createElement('div');
        track.className = 'hydration-track';
        track.style.height = '10px';
        track.style.marginBottom = '0';

        var fill = document.createElement('div');
        fill.className = 'hydration-fill';
        fill.style.width = Math.min(100, Math.max(0, pct || 0)) + '%';
        fill.style.background = color;
        fill.style.boxShadow = '0 0 10px ' + color;

        track.appendChild(fill);
        row.appendChild(track);
        return row;
    }

    // 1-Tap Quick Log food helper
    window.quickLogFood = function (food, qtyMultiplier) {
        var mult = qtyMultiplier || 1.0;
        var payload = {
            food_name: food.name,
            food_id: food.food_id || food.id,
            variant_id: food.variant_id,
            brand_name: food.brand || '',
            calories: Math.round((food.calories || 0) * mult),
            protein: Math.round((food.protein || 0) * mult * 10) / 10,
            carbs: Math.round((food.carbs || 0) * mult * 10) / 10,
            fat: Math.round((food.fat || 0) * mult * 10) / 10,
            quantity: mult,
            unit: food.serving || 'serving',
            meal_type: food.meal_type || 'Lunch',
        };

        fetch('/api/v1/nutrition/quick-log/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken') || ''
            },
            body: JSON.stringify(payload)
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.success) {
                if (window.showToast) {
                    window.showToast('Logged ' + payload.food_name + ' (+' + (data.xp_awarded || 0) + ' XP)');
                }
                if (window.loadNutrition) window.loadNutrition();
            } else {
                alert('Could not log food: ' + (data.error || 'Server error'));
            }
        })
        .catch(function (err) {
            console.error('Quick log error:', err);
            alert('Error logging food to Sparky.');
        });
    };

    // Open Snap & Note Modal
    window.openSnapMealModal = function () {
        if (window.closeModal) window.closeModal();

        var modalTitle = document.getElementById('modal-title');
        var modalDesc = document.getElementById('modal-desc');
        var modalAction = document.getElementById('modal-action');
        var modalIcon = document.querySelector('.modal-icon i');

        if (modalTitle) modalTitle.textContent = 'Snap & Note Meal';
        if (modalIcon) modalIcon.className = 'fa-solid fa-camera';
        if (modalAction) modalAction.style.display = 'none';

        var html = '<div style="text-align: left;">';
        html += '<p style="color: #94a3b8; font-size: 0.88rem; margin-bottom: 14px;">Take a picture and add a quick note. Sparky will match it to your recent foods, and you can review it before logging.</p>';

        html += '<div style="margin-bottom: 14px;">';
        html += '<label style="display: block; font-size: 0.78rem; font-weight: 800; color: #cbd5e1; text-transform: uppercase; margin-bottom: 8px;">Meal Photo</label>';
        html += '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px;">';
        html += '<button type="button" id="btn-snap-camera" style="padding: 12px; background: linear-gradient(135deg, #a855f7 0%, #7e22ce 100%); border: none; border-radius: 12px; color: #fff; font-weight: 800; font-size: 0.88rem; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 6px; box-shadow: 0 4px 12px rgba(168, 85, 247, 0.3);"><i class="fa-solid fa-camera"></i> Take Photo</button>';
        html += '<button type="button" id="btn-snap-gallery" style="padding: 12px; background: rgba(30, 41, 59, 0.9); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 12px; color: #e2e8f0; font-weight: 800; font-size: 0.88rem; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 6px;"><i class="fa-solid fa-image"></i> Choose File</button>';
        html += '</div>';
        html += '<input type="file" id="snap-file-input" accept="image/*" style="display: none;">';
        html += '<div id="snap-preview-container" style="display: none; margin-top: 10px; text-align: center; position: relative;">';
        html += '<img id="snap-preview-img" style="max-height: 160px; max-width: 100%; border-radius: 12px; border: 2px solid #a855f7; box-shadow: 0 4px 16px rgba(0,0,0,0.4);" />';
        html += '<div id="snap-preview-badge" style="margin-top: 6px; font-size: 0.75rem; color: #4ade80; font-weight: 800;"><i class="fa-solid fa-circle-check"></i> Photo Ready</div>';
        html += '</div>';
        html += '</div>';

        html += '<div style="margin-bottom: 12px;">';
        html += '<label style="display: block; font-size: 0.78rem; font-weight: 800; color: #cbd5e1; text-transform: uppercase; margin-bottom: 6px;">Quick Note / Details</label>';
        html += '<textarea id="snap-note-input" rows="2" placeholder="e.g. Chipotle chicken bowl with double brown rice and black beans" style="width: 100%; padding: 10px; background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; color: #fff; font-size: 0.9rem; resize: none;"></textarea>';
        html += '</div>';

        html += '<div style="display: flex; gap: 8px; margin-bottom: 18px;">';
        html += '<select id="snap-meal-type" style="flex: 1; padding: 10px; background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; color: #fff; font-weight: 700;">';
        html += '<option value="Breakfast">Breakfast</option>';
        html += '<option value="Lunch" selected>Lunch</option>';
        html += '<option value="Dinner">Dinner</option>';
        html += '<option value="Snack">Snack</option>';
        html += '</select>';
        html += '</div>';

        html += '<div style="display: flex; gap: 10px;">';
        html += '<button id="btn-snap-upload" style="flex: 1; padding: 14px; background: linear-gradient(135deg, #a855f7 0%, #7e22ce 100%); border: none; border-radius: 14px; color: #fff; font-weight: 800; font-size: 0.95rem; cursor: pointer; box-shadow: 0 4px 14px rgba(168, 85, 247, 0.4);"><i class="fa-solid fa-wand-magic-sparkles"></i> Analyze & Review</button>';
        html += '</div>';
        html += '</div>';

        if (modalDesc) modalDesc.innerHTML = html;
        if (window.openModal) window.openModal();

        var fileInput = document.getElementById('snap-file-input');
        var previewContainer = document.getElementById('snap-preview-container');
        var previewImg = document.getElementById('snap-preview-img');
        var capturedBase64 = null;

        window.onFoodPhotoCaptured = function (base64OrDataUri) {
            capturedBase64 = base64OrDataUri;
            if (previewImg) previewImg.src = base64OrDataUri;
            if (previewContainer) previewContainer.style.display = 'block';
        };

        var btnCamera = document.getElementById('btn-snap-camera');
        if (btnCamera) {
            btnCamera.onclick = function () {
                if (window.FlamingoNative && window.FlamingoNative.snapFoodPhoto) {
                    window.FlamingoNative.snapFoodPhoto('camera');
                } else if (fileInput) {
                    fileInput.setAttribute('capture', 'environment');
                    fileInput.click();
                }
            };
        }

        var btnGallery = document.getElementById('btn-snap-gallery');
        if (btnGallery) {
            btnGallery.onclick = function () {
                if (window.FlamingoNative && window.FlamingoNative.snapFoodPhoto) {
                    window.FlamingoNative.snapFoodPhoto('gallery');
                } else if (fileInput) {
                    fileInput.removeAttribute('capture');
                    fileInput.click();
                }
            };
        }

        if (fileInput) {
            fileInput.onchange = function () {
                if (fileInput.files && fileInput.files[0]) {
                    var reader = new FileReader();
                    reader.onload = function (e) {
                        capturedBase64 = e.target.result;
                        if (previewImg) previewImg.src = e.target.result;
                        if (previewContainer) previewContainer.style.display = 'block';
                    };
                    reader.readAsDataURL(fileInput.files[0]);
                }
            };
        }

        var btnUpload = document.getElementById('btn-snap-upload');
        if (btnUpload) {
            btnUpload.onclick = function () {
                var noteVal = document.getElementById('snap-note-input').value;
                var mealTypeVal = document.getElementById('snap-meal-type').value;

                if (!noteVal && !capturedBase64 && (!fileInput || !fileInput.files || !fileInput.files[0])) {
                    alert('Please capture a photo or enter a note about your meal.');
                    return;
                }

                btnUpload.disabled = true;
                btnUpload.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Analyzing...';

                var formData = new FormData();
                formData.append('note', noteVal);
                formData.append('meal_type', mealTypeVal);
                if (capturedBase64) {
                    formData.append('image_base64', capturedBase64);
                } else if (fileInput && fileInput.files && fileInput.files[0]) {
                    formData.append('image', fileInput.files[0]);
                }

                fetch('/api/v1/nutrition/snaps/upload/', {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCookie('csrftoken') || ''
                    },
                    body: formData
                })
                .then(function (res) { return res.json(); })
                .then(function (resData) {
                    if (resData.success && resData.draft) {
                        window.openSnapReviewModal(resData.draft);
                    } else {
                        alert('Upload failed: ' + (resData.error || 'Server error'));
                        btnUpload.disabled = false;
                        btnUpload.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Analyze & Review';
                    }
                })
                .catch(function (err) {
                    console.error('Snap error:', err);
                    alert('Error analyzing snap.');
                    btnUpload.disabled = false;
                    btnUpload.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Analyze & Review';
                });
            };
        }
    };

    // Open Snap Review Modal
    window.openSnapReviewModal = function (draft) {
        if (window.closeModal) window.closeModal();

        var modalTitle = document.getElementById('modal-title');
        var modalDesc = document.getElementById('modal-desc');
        var modalAction = document.getElementById('modal-action');
        var modalIcon = document.querySelector('.modal-icon i');

        if (modalTitle) modalTitle.textContent = 'Review & Log Meal';
        if (modalIcon) modalIcon.className = 'fa-solid fa-check-double';
        if (modalAction) modalAction.style.display = 'none';

        var items = draft.extracted_items || [];
        var html = '<div style="text-align: left;">';

        if (draft.image_url) {
            html += '<div style="text-align: center; margin-bottom: 12px;"><img src="' + draft.image_url + '" style="max-height: 120px; border-radius: 12px; border: 1px solid rgba(255, 255, 255, 0.1);" /></div>';
        }

        if (draft.note) {
            html += '<div style="background: rgba(30, 41, 59, 0.6); border-radius: 10px; padding: 8px 12px; font-size: 0.85rem; color: #cbd5e1; margin-bottom: 12px;"><strong>Note:</strong> ' + draft.note + '</div>';
        }

        html += '<div style="font-size: 0.8rem; font-weight: 800; text-transform: uppercase; color: #94a3b8; margin-bottom: 8px;">Matched Items</div>';
        html += '<div id="review-items-list" style="display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px;">';

        items.forEach(function (it, idx) {
            var badgeCls = 'recent';
            var badgeText = 'Recent Food';
            if (it.match_source === 'sparky_db') {
                badgeCls = 'db';
                badgeText = 'Database';
            } else if (it.match_source === 'vision_estimation') {
                badgeCls = 'ai';
                badgeText = 'AI Estimation';
            }

            html += '<div class="snap-review-item-row" id="review-item-' + idx + '">';
            html += '<div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px;">';
            html += '<div>';
            html += '<div style="font-weight: 800; font-size: 0.92rem; color: #fff;">' + it.name + '</div>';
            html += '<span class="snap-badge ' + badgeCls + '">' + badgeText + '</span>';
            html += '</div>';
            html += '<div style="text-align: right;">';
            html += '<div style="font-weight: 900; color: #c084fc;">' + Math.round(it.protein || 0) + 'g Protein</div>';
            html += '<div style="font-size: 0.8rem; color: #94a3b8;">' + Math.round(it.calories || 0) + ' kcal</div>';
            html += '</div>';
            html += '</div>';
            html += '</div>';
        });

        html += '</div>';

        html += '<div style="display: flex; gap: 10px;">';
        html += '<button id="btn-snap-commit" style="flex: 1; padding: 14px; background: linear-gradient(135deg, #10b981 0%, #059669 100%); border: none; border-radius: 14px; color: #fff; font-weight: 800; font-size: 0.95rem; cursor: pointer; box-shadow: 0 4px 14px rgba(16, 185, 129, 0.4);"><i class="fa-solid fa-cloud-arrow-up"></i> Commit to Sparky (+XP)</button>';
        html += '</div>';
        html += '</div>';

        if (modalDesc) modalDesc.innerHTML = html;
        if (window.openModal) window.openModal();

        var btnCommit = document.getElementById('btn-snap-commit');
        if (btnCommit) {
            btnCommit.onclick = function () {
                btnCommit.disabled = true;
                btnCommit.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Logging to Sparky...';

                fetch('/api/v1/nutrition/snaps/' + draft.id + '/commit/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCookie('csrftoken') || ''
                    },
                    body: JSON.stringify({
                        items: items,
                        meal_type: draft.meal_type || 'Lunch'
                    })
                })
                .then(function (res) { return res.json(); })
                .then(function (resData) {
                    if (resData.success) {
                        if (window.closeModal) window.closeModal();
                        if (window.showToast) {
                            window.showToast('Logged meal to SparkyFitness! (+' + (resData.xp_awarded || 0) + ' XP)');
                        }
                        if (window.loadNutrition) window.loadNutrition();
                    } else {
                        alert('Commit error: ' + (resData.error || 'Server error'));
                        btnCommit.disabled = false;
                    }
                })
                .catch(function (err) {
                    console.error('Commit error:', err);
                    alert('Error saving food entry.');
                    btnCommit.disabled = false;
                });
            };
        }
    };

    // Open Search Foods Modal
    window.openSearchFoodsModal = function () {
        if (window.closeModal) window.closeModal();

        var modalTitle = document.getElementById('modal-title');
        var modalDesc = document.getElementById('modal-desc');
        var modalAction = document.getElementById('modal-action');
        var modalIcon = document.querySelector('.modal-icon i');

        if (modalTitle) modalTitle.textContent = 'Search Sparky Foods';
        if (modalIcon) modalIcon.className = 'fa-solid fa-magnifying-glass';
        if (modalAction) modalAction.style.display = 'none';

        var html = '<div style="text-align: left;">';
        html += '<div class="food-search-input-wrap">';
        html += '<i class="fa-solid fa-magnifying-glass" style="color: #94a3b8;"></i>';
        html += '<input type="text" id="live-food-search-input" class="food-search-input" placeholder="Search chicken, eggs, rice, brand..." autofocus />';
        html += '</div>';
        html += '<div id="live-search-results-list" class="food-search-results"></div>';
        html += '</div>';

        if (modalDesc) modalDesc.innerHTML = html;
        if (window.openModal) window.openModal();

        var searchInput = document.getElementById('live-food-search-input');
        var resultsList = document.getElementById('live-search-results-list');

        function performSearch(q) {
            resultsList.innerHTML = '<div style="padding: 12px; text-align: center; color: #94a3b8;"><i class="fa-solid fa-spinner fa-spin"></i> Searching Sparky database...</div>';
            fetch('/api/v1/nutrition/search-foods/?q=' + encodeURIComponent(q))
                .then(function (res) { return res.json(); })
                .then(function (data) {
                    var items = data.results || [];
                    if (!items.length) {
                        resultsList.innerHTML = '<div style="padding: 12px; text-align: center; color: #64748b;">No matching foods found.</div>';
                        return;
                    }
                    resultsList.innerHTML = '';
                    items.forEach(function (f) {
                        var card = document.createElement('div');
                        card.className = 'food-result-item';
                        card.innerHTML = '<div>' +
                            '<div style="font-weight: 800; font-size: 0.9rem; color: #fff;">' + f.name + '</div>' +
                            '<div style="font-size: 0.75rem; color: #94a3b8;">' + (f.brand ? f.brand + ' • ' : '') + f.serving + '</div>' +
                            '</div>' +
                            '<div style="display: flex; align-items: center; gap: 10px;">' +
                            '<div style="text-align: right;">' +
                            '<div style="font-weight: 900; color: #c084fc; font-size: 0.85rem;">' + Math.round(f.protein || 0) + 'g P</div>' +
                            '<div style="font-size: 0.75rem; color: #94a3b8;">' + Math.round(f.calories || 0) + ' cal</div>' +
                            '</div>' +
                            '<button class="recent-food-add-btn" style="width: 32px; height: 32px;"><i class="fa-solid fa-plus"></i></button>' +
                            '</div>';

                        card.onclick = function () {
                            if (window.closeModal) window.closeModal();
                            window.quickLogFood(f, 1.0);
                        };
                        resultsList.appendChild(card);
                    });
                })
                .catch(function () {
                    resultsList.innerHTML = '<div style="padding: 12px; text-align: center; color: #ef4444;">Error querying foods.</div>';
                });
        }

        // Initial search for common foods
        performSearch('');

        var debounceTimer = null;
        if (searchInput) {
            searchInput.oninput = function () {
                clearTimeout(debounceTimer);
                debounceTimer = setTimeout(function () {
                    performSearch(searchInput.value);
                }, 300);
            };
        }
    };

    // Open Quick Log Modal
    window.openQuickLogModal = function () {
        if (window.closeModal) window.closeModal();

        var modalTitle = document.getElementById('modal-title');
        var modalDesc = document.getElementById('modal-desc');
        var modalAction = document.getElementById('modal-action');
        var modalIcon = document.querySelector('.modal-icon i');

        if (modalTitle) modalTitle.textContent = 'Quick Custom Log';
        if (modalIcon) modalIcon.className = 'fa-solid fa-bolt';
        if (modalAction) modalAction.style.display = 'none';

        var html = '<div style="text-align: left;">';
        html += '<div style="margin-bottom: 10px;"><label style="font-size: 0.78rem; font-weight: 800; color: #cbd5e1; text-transform: uppercase;">Meal / Food Name</label><input type="text" id="custom-food-name" placeholder="e.g. Protein Smoothie" style="width: 100%; padding: 10px; background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; color: #fff; font-weight: 700; margin-top: 4px;" /></div>';
        html += '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px;">';
        html += '<div><label style="font-size: 0.78rem; font-weight: 800; color: #c084fc; text-transform: uppercase;">Protein (g)</label><input type="number" id="custom-food-pro" placeholder="30" style="width: 100%; padding: 10px; background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; color: #fff; font-weight: 700; margin-top: 4px;" /></div>';
        html += '<div><label style="font-size: 0.78rem; font-weight: 800; color: #fb7185; text-transform: uppercase;">Calories</label><input type="number" id="custom-food-cal" placeholder="350" style="width: 100%; padding: 10px; background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; color: #fff; font-weight: 700; margin-top: 4px;" /></div>';
        html += '</div>';

        html += '<div style="margin-bottom: 16px;"><label style="font-size: 0.78rem; font-weight: 800; color: #cbd5e1; text-transform: uppercase;">Meal Slot</label><select id="custom-meal-slot" style="width: 100%; padding: 10px; background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; color: #fff; font-weight: 700; margin-top: 4px;"><option value="Breakfast">Breakfast</option><option value="Lunch" selected>Lunch</option><option value="Dinner">Dinner</option><option value="Snack">Snack</option></select></div>';

        html += '<button id="btn-custom-log" style="width: 100%; padding: 14px; background: linear-gradient(135deg, #a855f7 0%, #7e22ce 100%); border: none; border-radius: 14px; color: #fff; font-weight: 800; font-size: 0.95rem; cursor: pointer;"><i class="fa-solid fa-plus"></i> Log to SparkyFitness</button>';
        html += '</div>';

        if (modalDesc) modalDesc.innerHTML = html;
        if (window.openModal) window.openModal();

        var btnLog = document.getElementById('btn-custom-log');
        if (btnLog) {
            btnLog.onclick = function () {
                var nameVal = document.getElementById('custom-food-name').value;
                var proVal = parseFloat(document.getElementById('custom-food-pro').value) || 0;
                var calVal = parseFloat(document.getElementById('custom-food-cal').value) || 0;
                var slotVal = document.getElementById('custom-meal-slot').value;

                if (!nameVal) {
                    alert('Please enter a meal name.');
                    return;
                }
                if (window.closeModal) window.closeModal();
                window.quickLogFood({
                    name: nameVal,
                    protein: proVal,
                    calories: calVal,
                    meal_type: slotVal,
                    serving: '1 serving'
                }, 1.0);
            };
        }
    };

    function buildNutritionHero(content, data) {
        var hero = document.createElement('div');
        hero.className = 'nutrition-hero-card';

        // 1. Pending Snaps Banner (if any)
        if (data.pending_snaps_count && data.pending_snaps_count > 0) {
            var banner = document.createElement('div');
            banner.className = 'nutrition-snap-banner';
            banner.innerHTML = '<div style="display: flex; align-items: center; gap: 10px;">' +
                '<i class="fa-solid fa-camera text-purple-400 text-lg"></i>' +
                '<div>' +
                '<div style="font-weight: 800; color: #fff; font-size: 0.9rem;">' + data.pending_snaps_count + ' Meal Snap' + (data.pending_snaps_count > 1 ? 's' : '') + ' Ready</div>' +
                '<div style="font-size: 0.75rem; color: #d8b4fe;">Tap to review and commit to Sparky</div>' +
                '</div>' +
                '</div>' +
                '<i class="fa-solid fa-chevron-right text-purple-300"></i>';

            banner.onclick = function () {
                fetch('/api/v1/nutrition/snaps/')
                    .then(function (res) { return res.json(); })
                    .then(function (snapData) {
                        if (snapData.drafts && snapData.drafts.length) {
                            window.openSnapReviewModal(snapData.drafts[0]);
                        }
                    });
            };
            hero.appendChild(banner);
        }

        // 2. Header with Date & Status Badge
        var today = data.today || {};
        var head = document.createElement('div');
        head.style.display = 'flex';
        head.style.justifyContent = 'space-between';
        head.style.alignItems = 'center';
        head.style.marginBottom = '14px';

        var title = document.createElement('div');
        title.style.fontWeight = '900';
        title.style.fontSize = '1.1rem';
        title.style.color = '#fff';
        title.innerHTML = '<i class="fa-solid fa-utensils text-purple-400 mr-2"></i> Today\'s Macros';
        head.appendChild(title);

        var badgeInfo = getStatusBadge(today);
        var badge = document.createElement('span');
        badge.className = badgeInfo.cls;
        badge.textContent = badgeInfo.text;
        head.appendChild(badge);
        hero.appendChild(head);

        // 3. Macro Numbers Grid
        var macroGrid = document.createElement('div');
        macroGrid.className = 'nutrition-macro-grid';

        // Protein Box
        var proBox = document.createElement('div');
        proBox.className = 'nutrition-macro-box protein';
        proBox.innerHTML = '<div class="nutrition-macro-title">Protein</div>' +
            '<div class="nutrition-macro-numbers">' +
            '<span class="nutrition-macro-cur">' + Math.round(today.protein || 0) + 'g</span>' +
            '<span class="nutrition-macro-goal">/ ' + Math.round(today.protein_goal || 0) + 'g</span>' +
            '</div>';
        macroGrid.appendChild(proBox);

        // Calories Box
        var calBox = document.createElement('div');
        calBox.className = 'nutrition-macro-box calories';
        calBox.innerHTML = '<div class="nutrition-macro-title">Calories</div>' +
            '<div class="nutrition-macro-numbers">' +
            '<span class="nutrition-macro-cur">' + Math.round(today.calories || 0) + '</span>' +
            '<span class="nutrition-macro-goal">/ ' + Math.round(today.calorie_goal || 0) + '</span>' +
            '</div>';
        macroGrid.appendChild(calBox);
        hero.appendChild(macroGrid);

        // 4. Macro Progress Meters
        hero.appendChild(buildMacroBar('Protein Progress', today.protein_pct || 0, Math.round(today.protein || 0) + '/' + Math.round(today.protein_goal || 0) + 'g (' + (today.protein_pct || 0) + '%)', '#a855f7'));
        hero.appendChild(buildMacroBar('Calorie Budget', today.calorie_pct || 0, Math.round(today.calories || 0) + '/' + Math.round(today.calorie_goal || 0) + ' kcal (' + (today.calorie_pct || 0) + '%)', '#f43f5e'));

        // 5. Action Buttons (Snap Photo, Search DB, Quick Log)
        var actionsRow = document.createElement('div');
        actionsRow.className = 'nutrition-actions-row';

        var snapBtn = document.createElement('button');
        snapBtn.className = 'nutrition-action-btn snap-cta';
        snapBtn.innerHTML = '<i class="fa-solid fa-camera"></i> Snap Photo';
        snapBtn.onclick = function () {
            window.openSnapMealModal();
        };
        actionsRow.appendChild(snapBtn);

        var searchBtn = document.createElement('button');
        searchBtn.className = 'nutrition-action-btn search-cta';
        searchBtn.innerHTML = '<i class="fa-solid fa-magnifying-glass"></i> Search DB';
        searchBtn.onclick = function () {
            window.openSearchFoodsModal();
        };
        actionsRow.appendChild(searchBtn);

        var quickBtn = document.createElement('button');
        quickBtn.className = 'nutrition-action-btn quick-cta';
        quickBtn.innerHTML = '<i class="fa-solid fa-bolt"></i> Quick Log';
        quickBtn.onclick = function () {
            window.openQuickLogModal();
        };
        actionsRow.appendChild(quickBtn);

        hero.appendChild(actionsRow);

        // 6. Recent & Frequent Foods Section
        var recentSection = document.createElement('div');
        recentSection.className = 'nutrition-recent-section';
        recentSection.innerHTML = '<div class="nutrition-recent-header">' +
            '<span><i class="fa-solid fa-clock-rotate-left mr-1.5"></i> Recent & Favorite Foods</span>' +
            '<span style="font-size: 0.75rem; color: #a855f7; cursor: pointer;" onclick="openSearchFoodsModal()">All Foods &rarr;</span>' +
            '</div>';

        var recentGrid = document.createElement('div');
        recentGrid.className = 'nutrition-recent-grid';
        recentGrid.id = 'nutrition-recent-grid-container';
        recentSection.appendChild(recentGrid);
        hero.appendChild(recentSection);

        // Fetch recent foods asynchronously from Sparky
        fetch('/api/v1/nutrition/recent-foods/')
            .then(function (res) { return res.json(); })
            .then(function (resData) {
                var foods = resData.recent_foods || [];
                var grid = document.getElementById('nutrition-recent-grid-container');
                if (!grid) return;
                grid.innerHTML = '';
                foods.slice(0, 6).forEach(function (f) {
                    var card = document.createElement('div');
                    card.className = 'recent-food-card';
                    card.innerHTML = '<div>' +
                        '<div class="recent-food-name">' + f.name + '</div>' +
                        '<div class="recent-food-macros">' +
                        '<span class="recent-food-pro">' + Math.round(f.protein || 0) + 'g P</span>' +
                        '<span>' + Math.round(f.calories || 0) + ' cal</span>' +
                        '</div>' +
                        '</div>' +
                        '<div style="display: flex; justify-content: space-between; align-items: center; margin-top: 4px;">' +
                        '<span style="font-size: 0.7rem; color: #64748b;">' + (f.serving || '1 serv') + '</span>' +
                        '<div class="recent-food-add-btn"><i class="fa-solid fa-plus"></i></div>' +
                        '</div>';

                    card.onclick = function () {
                        window.quickLogFood(f, 1.0);
                    };
                    grid.appendChild(card);
                });
            });

        // 7. Today's Meals Timeline
        if (today.food_entries && today.food_entries.length) {
            var timeline = document.createElement('div');
            timeline.className = 'today-intake-timeline';
            var tlHeader = document.createElement('div');
            tlHeader.className = 'today-intake-header';
            tlHeader.innerHTML = '<span><i class="fa-solid fa-list-check mr-1.5"></i> Today\'s Logged Meals</span><span>' + today.food_entries.length + ' items</span>';
            timeline.appendChild(tlHeader);

            today.food_entries.forEach(function (f) {
                var item = document.createElement('div');
                item.className = 'today-intake-item';
                var nameStr = f.name || f.food_name || 'Food';
                item.innerHTML = '<span style="color: #f1f5f9;">' + nameStr + '</span>' +
                    '<span style="display: flex; gap: 8px;">' +
                    '<span style="color: #c084fc;">' + Math.round(f.protein || 0) + 'g P</span>' +
                    '<span style="color: #94a3b8;">' + Math.round(f.calories || 0) + ' cal</span>' +
                    '</span>';
                timeline.appendChild(item);
            });
            hero.appendChild(timeline);
        }

        content.appendChild(hero);
    }

    window.showDayDetailModal = function (day) {
        if (window.closeModal) window.closeModal();

        var modalTitle = document.getElementById('modal-title');
        var modalDesc = document.getElementById('modal-desc');
        var modalAction = document.getElementById('modal-action');
        var modalIcon = document.querySelector('.modal-icon i');

        if (modalTitle) modalTitle.textContent = 'Nutrition Detail';
        if (modalIcon) modalIcon.className = 'fa-solid fa-apple-whole';
        if (modalAction) {
            modalAction.textContent = 'Close';
            modalAction.onclick = function () {
                if (window.closeModal) window.closeModal();
            };
        }

        var badgeInfo = getStatusBadge(day);
        var detailHtml = '<div style="text-align: left;">';
        detailHtml += '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">';
        detailHtml += '<span style="font-weight: 800; font-size: 1.1rem; color: var(--text-main);">' + day.date + '</span>';
        detailHtml += '<span class="' + badgeInfo.cls + '" style="font-size: 0.8rem;">' + badgeInfo.text + '</span>';
        detailHtml += '</div>';

        var rewardTokens = day.tokens !== undefined ? day.tokens : day.materials;
        if (day.xp || rewardTokens) {
            detailHtml += '<div style="display: flex; gap: 14px; margin-bottom: 12px; flex-wrap: wrap;">';
            if (day.xp) {
                detailHtml += '<span class="reward xp" style="display: inline-flex; align-items: center; gap: 6px; font-weight: 800;"><i class="fa-solid fa-star"></i> +' + day.xp + ' XP</span>';
            }
            if (rewardTokens) {
                detailHtml += '<span class="reward mat" style="display: inline-flex; align-items: center; gap: 6px; font-weight: 800;"><i class="fa-solid fa-gem"></i> +' + rewardTokens + ' tokens</span>';
            }
            detailHtml += '</div>';
        }

        detailHtml += '<div style="margin-bottom: 8px;"><strong>Protein:</strong> ' + Math.round(day.protein || 0) + 'g / ' + Math.round(day.protein_goal || 0) + 'g (' + (day.protein_pct || 0) + '%)</div>';
        detailHtml += '<div style="margin-bottom: 8px;"><strong>Calories:</strong> ' + Math.round(day.calories || 0) + ' / ' + Math.round(day.calorie_goal || 0) + ' (' + (day.calorie_pct || 0) + '%)</div>';

        if (day.food_entries && day.food_entries.length) {
            detailHtml += '<div style="margin-top: 12px; border-top: 2px dashed var(--border-color); padding-top: 10px;">';
            detailHtml += '<div style="font-weight: 800; font-size: 0.8rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 8px;">Meals</div>';
            day.food_entries.forEach(function (f) {
                var fName = f.name || f.food_name || 'Food';
                detailHtml += '<div style="display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid var(--border-color); font-weight: 700; font-size: 0.9rem;">';
                detailHtml += '<span style="color: var(--text-main);">' + fName + '</span>';
                detailHtml += '<span style="color: var(--primary-purple);">' + Math.round(f.protein || 0) + 'g</span>';
                detailHtml += '<span style="color: var(--text-muted);">' + Math.round(f.calories || 0) + ' cal</span>';
                detailHtml += '</div>';
            });
            detailHtml += '</div>';
        }

        detailHtml += '</div>';

        if (modalDesc) modalDesc.innerHTML = detailHtml;
        if (window.openModal) window.openModal();
    };

    window.createModalityController({
        name: 'nutrition',
        title: 'Nutrition',
        icon: 'fa-apple-whole',
        apiUrl: '/api/v1/nutrition/',
        guidanceText: 'Hit your protein goal and calorie budget for max XP (+50) & tokens (+25). Being close or hitting individual goals earns tiered rewards!',
        emptyState: {
            icon: 'fa-apple-whole',
            title: 'No nutrition data yet',
            desc: 'Link SparkyFitness to start tracking your macros and hitting your protein goals.',
            hint: 'Nutrition XP flows in once your food syncs.',
            ctaText: 'Link SparkyFitness',
            ctaHref: '/profile/'
        },
        renderCustomContent: function (content, data) {
            // 0. Nutrition Hero & Logging Dashboard
            buildNutritionHero(content, data);

            // 1. Trends & Insights
            if (window.FFInsights) {
                window.FFInsights.createInsights(content, 'nutrition', data);
            }

            // 2. History List (at the very bottom)
            if (data.history && data.history.length) {
                var wrap = document.createElement('div');
                var title = document.createElement('div');
                title.className = 'history-title';
                title.innerHTML = '<i class="fa-solid fa-list"></i> History';
                wrap.appendChild(title);
                var ul = document.createElement('ul');
                ul.className = 'history-list';
                data.history.forEach(function (day) {
                    var li = document.createElement('li');
                    li.className = 'history-item' + (day.perfect ? ' perfect' : '');
                    li.style.cursor = 'pointer';
                    li.addEventListener('click', function () {
                        window.showDayDetailModal(day);
                    });
                    var left = document.createElement('span');
                    left.className = 'hist-macros';
                    left.textContent = day.date + '  ' + formatMacro(day.protein, day.protein_goal) + '  ' + formatMacro(day.calories, day.calorie_goal);
                    li.appendChild(left);
                    var right = document.createElement('span');
                    right.className = 'hist-reward';
                    var badgeInfo = getStatusBadge(day);
                    var tok = day.tokens !== undefined ? day.tokens : day.materials;
                    right.textContent = badgeInfo.text + ' ' + (day.xp ? '+' + day.xp + ' XP' : '') + (tok ? ', ' + tok + ' tok' : '');
                    li.appendChild(right);
                    ul.appendChild(li);
                });
                wrap.appendChild(ul);
                content.appendChild(wrap);
            }
        }
    });

    var nutNode = document.getElementById('node-nutrition');
    if (nutNode) {
        nutNode.addEventListener('click', function () {
            window.loadNutrition();
        });
    }
})();
