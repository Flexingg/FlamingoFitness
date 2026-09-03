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
    window.quickLogFood = function (food, qtyMultiplier, optDate) {
        var mult = (qtyMultiplier !== undefined && qtyMultiplier !== null) ? Number(qtyMultiplier) : (Number(food.quantity) || 1.0);
        if (isNaN(mult) || mult <= 0) mult = 1.0;

        var baseCal = food.base_calories !== undefined ? Number(food.base_calories) : Number(food.calories || 0);
        var basePro = food.base_protein !== undefined ? Number(food.base_protein) : Number(food.protein || 0);
        var baseCarb = food.base_carbs !== undefined ? Number(food.base_carbs) : Number(food.carbs || 0);
        var baseFat = food.base_fat !== undefined ? Number(food.base_fat) : Number(food.fat || 0);

        var targetDate = optDate || food.entry_date || food.date || window._activeNutritionDate || new Date().toISOString().split('T')[0];

        var payload = {
            food_name: food.food_name || food.name,
            food_id: food.food_id || food.id,
            variant_id: food.variant_id,
            brand_name: food.brand || food.brand_name || '',
            base_calories: baseCal,
            base_protein: basePro,
            base_carbs: baseCarb,
            base_fat: baseFat,
            calories: Math.round(baseCal * mult * 10) / 10,
            protein: Math.round(basePro * mult * 10) / 10,
            carbs: Math.round(baseCarb * mult * 10) / 10,
            fat: Math.round(baseFat * mult * 10) / 10,
            quantity: mult,
            unit: food.serving || food.unit || 'serving',
            meal_type: food.meal_type || 'Lunch',
            entry_date: targetDate,
            create_custom: Boolean(food.create_custom),
            source: food.source || (food.create_custom ? 'sparky_ai' : undefined),
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
                var refreshDate = data.entry_date || targetDate;
                if (window.loadNutrition) window.loadNutrition(refreshDate);
            } else {
                alert('Could not log food: ' + (data.error || 'Server error'));
            }
        })
        .catch(function (err) {
            console.error('Quick log error:', err);
            alert('Error logging food to Sparky.');
        });
    };

    // Open Portion Adjustment Modal before logging any food
    window.openPortionLogModal = function (food) {
        if (window.closeModal) window.closeModal();

        var modalTitle = document.getElementById('modal-title');
        var modalDesc = document.getElementById('modal-desc');
        var modalAction = document.getElementById('modal-action');
        var modalIcon = document.querySelector('.modal-icon i');

        if (modalTitle) modalTitle.textContent = 'Log Food to Sparky';
        if (modalIcon) modalIcon.className = 'fa-solid fa-utensils';
        if (modalAction) modalAction.style.display = 'none';

        var baseCal = food.base_calories !== undefined ? Number(food.base_calories) : Number(food.calories || 0);
        var basePro = food.base_protein !== undefined ? Number(food.base_protein) : Number(food.protein || 0);
        var baseCarb = food.base_carbs !== undefined ? Number(food.base_carbs) : Number(food.carbs || 0);
        var baseFat = food.base_fat !== undefined ? Number(food.base_fat) : Number(food.fat || 0);

        var html = '<div style="text-align: left;">';
        html += '<div style="background: rgba(168, 85, 247, 0.1); border: 1px solid rgba(168, 85, 247, 0.3); border-radius: 14px; padding: 12px; margin-bottom: 14px;">';
        html += '<div style="font-weight: 800; font-size: 1rem; color: #fff; margin-bottom: 2px;">' + (food.name || 'Food') + '</div>';
        html += '<div style="font-size: 0.78rem; color: #94a3b8;">1 Serving (' + (food.serving || '1 serving') + '): <span style="color: #4ade80; font-weight: 700;">' + Math.round(baseCal) + ' cal</span> • <span style="color: #c084fc; font-weight: 700;">' + Math.round(basePro) + 'g Protein</span></div>';
        html += '</div>';

        html += '<div style="margin-bottom: 12px;">';
        html += '<label style="display: block; font-size: 0.75rem; font-weight: 800; color: #cbd5e1; text-transform: uppercase; margin-bottom: 6px;">How many servings did you eat?</label>';
        html += '<div style="display: flex; align-items: center; justify-content: center; gap: 12px; margin-bottom: 10px;">';
        html += '<button type="button" id="portion-btn-minus" style="width: 44px; height: 44px; border-radius: 12px; background: rgba(30, 41, 59, 0.9); border: 1px solid rgba(255, 255, 255, 0.2); color: #fff; font-size: 1.2rem; font-weight: 900; cursor: pointer;">-</button>';
        html += '<input type="number" id="portion-qty-input" value="1.0" step="0.25" min="0.1" style="width: 90px; height: 44px; text-align: center; font-size: 1.25rem; font-weight: 900; color: #00F0FF; background: rgba(15, 23, 42, 0.9); border: 1px solid rgba(0, 240, 255, 0.4); border-radius: 12px;" />';
        html += '<button type="button" id="portion-btn-plus" style="width: 44px; height: 44px; border-radius: 12px; background: rgba(30, 41, 59, 0.9); border: 1px solid rgba(255, 255, 255, 0.2); color: #fff; font-size: 1.2rem; font-weight: 900; cursor: pointer;">+</button>';
        html += '</div>';

        html += '<div style="display: flex; gap: 6px; justify-content: center; margin-bottom: 14px;">';
        [0.5, 1.0, 1.5, 2.0, 3.0].forEach(function (preset) {
            html += '<button type="button" class="portion-preset-pill" data-val="' + preset + '" style="padding: 6px 12px; border-radius: 8px; border: 1px solid rgba(255, 255, 255, 0.15); background: rgba(30, 41, 59, 0.6); color: #cbd5e1; font-weight: 700; font-size: 0.78rem; cursor: pointer;">' + preset + 'x</button>';
        });
        html += '</div>';
        html += '</div>';

        var activeDateVal = window._activeNutritionDate || new Date().toISOString().split('T')[0];

        html += '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 14px;">';
        html += '<div>';
        html += '<label style="display: block; font-size: 0.75rem; font-weight: 800; color: #cbd5e1; text-transform: uppercase; margin-bottom: 4px;">Meal Slot</label>';
        html += '<select id="portion-meal-type" style="width: 100%; padding: 10px; background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 12px; color: #fff; font-weight: 700;">';
        html += '<option value="Breakfast">Breakfast</option><option value="Lunch" selected>Lunch</option><option value="Dinner">Dinner</option><option value="Snack">Snack</option>';
        html += '</select>';
        html += '</div>';
        html += '<div>';
        html += '<label style="display: block; font-size: 0.75rem; font-weight: 800; color: #cbd5e1; text-transform: uppercase; margin-bottom: 4px;"><i class="fa-regular fa-calendar text-purple-400 mr-1"></i> Date</label>';
        html += '<input type="date" id="portion-log-date" value="' + activeDateVal + '" style="width: 100%; padding: 9px 10px; background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 12px; color: #fff; font-weight: 700; font-size: 0.85rem;" />';
        html += '</div>';
        html += '</div>';

        html += '<div id="portion-total-card" style="background: rgba(15, 23, 42, 0.95); border: 1px solid rgba(0, 240, 255, 0.3); border-radius: 12px; padding: 12px; text-align: center; margin-bottom: 16px;">';
        html += '<div style="font-size: 0.75rem; color: #94a3b8; font-weight: 700; text-transform: uppercase; margin-bottom: 4px;">Total Being Logged:</div>';
        html += '<div id="portion-total-summary" style="font-size: 1.15rem; font-weight: 900; color: #fff;">';
        html += '<span style="color: #4ade80;">' + Math.round(baseCal) + ' cal</span> • <span style="color: #c084fc;">' + Math.round(basePro) + 'g P</span> • <span style="color: #38bdf8;">' + Math.round(baseCarb) + 'g C</span> • <span style="color: #fbbf24;">' + Math.round(baseFat) + 'g F</span>';
        html += '</div>';
        html += '</div>';

        html += '<button type="button" id="btn-portion-confirm" style="width: 100%; padding: 14px; background: linear-gradient(135deg, #10b981 0%, #059669 100%); border: none; border-radius: 12px; color: #fff; font-weight: 800; font-size: 0.95rem; cursor: pointer; box-shadow: 0 4px 14px rgba(16, 185, 129, 0.35);"><i class="fa-solid fa-cloud-arrow-up"></i> Log to Sparky (+XP)</button>';
        html += '</div>';

        if (modalDesc) modalDesc.innerHTML = html;
        if (window.openModal) window.openModal();

        var qtyInput = document.getElementById('portion-qty-input');
        var totalSummary = document.getElementById('portion-total-summary');
        var btnConfirm = document.getElementById('btn-portion-confirm');
        var btnMinus = document.getElementById('portion-btn-minus');
        var btnPlus = document.getElementById('portion-btn-plus');
        var mealSelect = document.getElementById('portion-meal-type');

        function updatePortionDisplay() {
            var q = parseFloat(qtyInput.value) || 1.0;
            if (q < 0.1) q = 0.1;
            var c = Math.round(baseCal * q);
            var p = Math.round(basePro * q * 10) / 10;
            var carb = Math.round(baseCarb * q * 10) / 10;
            var f = Math.round(baseFat * q * 10) / 10;

            if (totalSummary) {
                totalSummary.innerHTML = '<span style="color: #4ade80;">' + c + ' cal</span> • <span style="color: #c084fc;">' + p + 'g P</span> • <span style="color: #38bdf8;">' + carb + 'g C</span> • <span style="color: #fbbf24;">' + f + 'g F</span>';
            }
            if (btnConfirm) {
                btnConfirm.innerHTML = '<i class="fa-solid fa-cloud-arrow-up"></i> Log ' + q + ' Servings (' + c + ' cal / +XP)';
            }
        }

        if (btnMinus) {
            btnMinus.onclick = function () {
                var q = (parseFloat(qtyInput.value) || 1.0) - 0.5;
                if (q < 0.5) q = 0.25;
                qtyInput.value = q;
                updatePortionDisplay();
            };
        }
        if (btnPlus) {
            btnPlus.onclick = function () {
                var q = (parseFloat(qtyInput.value) || 1.0) + 0.5;
                qtyInput.value = q;
                updatePortionDisplay();
            };
        }
        if (qtyInput) {
            qtyInput.oninput = updatePortionDisplay;
        }

        document.querySelectorAll('.portion-preset-pill').forEach(function (pill) {
            pill.onclick = function () {
                qtyInput.value = pill.getAttribute('data-val');
                updatePortionDisplay();
            };
        });

        if (btnConfirm) {
            btnConfirm.onclick = function () {
                var q = parseFloat(qtyInput.value) || 1.0;
                var meal = mealSelect ? mealSelect.value : 'Lunch';
                var dateInp = document.getElementById('portion-log-date');
                var chosenDate = (dateInp && dateInp.value) ? dateInp.value : activeDateVal;
                btnConfirm.disabled = true;
                btnConfirm.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Logging to Sparky...';

                var logPayload = Object.assign({}, food, {
                    base_calories: baseCal,
                    base_protein: basePro,
                    base_carbs: baseCarb,
                    base_fat: baseFat,
                    calories: Math.round(baseCal * q * 10) / 10,
                    protein: Math.round(basePro * q * 10) / 10,
                    carbs: Math.round(baseCarb * q * 10) / 10,
                    fat: Math.round(baseFat * q * 10) / 10,
                    quantity: q,
                    meal_type: meal,
                    entry_date: chosenDate
                });

                if (window.closeModal) window.closeModal();
                window.quickLogFood(logPayload, q, chosenDate);
            };
        }

        updatePortionDisplay();
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
            html += '<div style="background: rgba(30, 41, 59, 0.6); border-radius: 10px; padding: 8px 12px; font-size: 0.85rem; color: #cbd5e1; margin-bottom: 12px;"><strong>Meal Note:</strong> ' + draft.note + '</div>';
        }

        var itemStates = items.map(function (it) {
            return {
                raw: it,
                selected: true,
                multiplier: it.quantity || 1.0,
                baseCal: it.calories || 0,
                basePro: it.protein || 0,
                baseCarb: it.carbs || 0,
                baseFat: it.fat || 0
            };
        });

        // Total Meal Macro Summary Card
        html += '<div id="snap-review-summary" style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(168, 85, 247, 0.3); border-radius: 12px; padding: 10px 14px; margin-bottom: 14px; display: flex; justify-content: space-around; text-align: center;">';
        html += '<div><div style="font-size: 0.68rem; color: #94a3b8; font-weight: 700;">TOTAL CAL</div><div id="sum-cal" style="font-weight: 900; font-size: 1.05rem; color: #fff;">0</div></div>';
        html += '<div><div style="font-size: 0.68rem; color: #c084fc; font-weight: 700;">PROTEIN</div><div id="sum-pro" style="font-weight: 900; font-size: 1.05rem; color: #c084fc;">0g</div></div>';
        html += '<div><div style="font-size: 0.68rem; color: #38bdf8; font-weight: 700;">CARBS</div><div id="sum-carb" style="font-weight: 900; font-size: 1.05rem; color: #38bdf8;">0g</div></div>';
        html += '<div><div style="font-size: 0.68rem; color: #fbbf24; font-weight: 700;">FAT</div><div id="sum-fat" style="font-weight: 900; font-size: 1.05rem; color: #fbbf24;">0g</div></div>';
        html += '</div>';

        html += '<div style="font-size: 0.8rem; font-weight: 800; text-transform: uppercase; color: #94a3b8; margin-bottom: 8px;">Decomposed Food Items (' + items.length + ')</div>';
        html += '<div id="review-items-list" style="display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px;">';

        items.forEach(function (it, idx) {
            var badgeCls = 'recent';
            var badgeText = 'Recent Food';
            if (it.match_source === 'sparky_db') {
                badgeCls = 'db';
                badgeText = 'Sparky Database';
            } else if (it.match_source === 'sparky_openfoodfacts') {
                badgeCls = 'db';
                badgeText = 'Open Food Facts';
            } else if (it.match_source === 'sparky_ai_created' || it.match_source === 'sparky_ai') {
                badgeCls = 'ai';
                badgeText = '✨ Sparky AI';
            } else if (it.match_source === 'sparky_estimation') {
                badgeCls = 'ai';
                badgeText = 'Sparky AI Estimation';
            }

            html += '<div class="snap-review-item-row" id="review-item-' + idx + '" style="padding: 10px; background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px;">';
            html += '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">';
            html += '<div style="display: flex; align-items: center; gap: 8px;">';
            html += '<input type="checkbox" id="chk-item-' + idx + '" checked style="width: 18px; height: 18px; accent-color: #10b981; cursor: pointer;" />';
            html += '<div>';
            html += '<div style="font-weight: 800; font-size: 0.9rem; color: #fff;">' + it.name + '</div>';
            html += '<span class="snap-badge ' + badgeCls + '" style="font-size: 0.65rem;">' + badgeText + '</span>';
            html += '</div>';
            html += '</div>';
            html += '<div style="text-align: right;">';
            html += '<div id="val-pro-' + idx + '" style="font-weight: 900; color: #c084fc; font-size: 0.88rem;">' + Math.round(it.protein || 0) + 'g P</div>';
            html += '<div id="val-cal-' + idx + '" style="font-size: 0.75rem; color: #94a3b8;">' + Math.round(it.calories || 0) + ' kcal</div>';
            html += '</div>';
            html += '</div>';

            // Multiplier controls
            html += '<div style="display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-top: 4px;">';
            html += '<span style="font-size: 0.72rem; color: #94a3b8;">Portion:</span>';
            html += '<button type="button" class="btn-step-sub" data-idx="' + idx + '" style="width: 24px; height: 24px; border-radius: 6px; border: 1px solid rgba(255, 255, 255, 0.15); background: rgba(15, 23, 42, 0.8); color: #fff; cursor: pointer; font-weight: 800;">-</button>';
            html += '<span id="val-mult-' + idx + '" style="font-weight: 800; font-size: 0.82rem; min-width: 32px; text-align: center; color: #fff;">1.0x</span>';
            html += '<button type="button" class="btn-step-add" data-idx="' + idx + '" style="width: 24px; height: 24px; border-radius: 6px; border: 1px solid rgba(255, 255, 255, 0.15); background: rgba(15, 23, 42, 0.8); color: #fff; cursor: pointer; font-weight: 800;">+</button>';
            html += '</div>';

            html += '</div>';
        });

        html += '</div>';

        var activeDateVal = window._activeNutritionDate || new Date().toISOString().split('T')[0];

        html += '<div style="display: flex; align-items: center; justify-content: space-between; background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; padding: 8px 12px; margin-bottom: 12px;">';
        html += '<label style="font-size: 0.75rem; font-weight: 800; color: #cbd5e1; text-transform: uppercase;"><i class="fa-regular fa-calendar text-purple-400 mr-1.5"></i> Log Date</label>';
        html += '<input type="date" id="snap-commit-date" value="' + activeDateVal + '" style="background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 8px; color: #fff; padding: 6px 10px; font-weight: 700; font-size: 0.85rem;" />';
        html += '</div>';

        html += '<div style="display: flex; gap: 10px;">';
        html += '<button id="btn-snap-commit" style="flex: 1; padding: 14px; background: linear-gradient(135deg, #10b981 0%, #059669 100%); border: none; border-radius: 14px; color: #fff; font-weight: 800; font-size: 0.95rem; cursor: pointer; box-shadow: 0 4px 14px rgba(16, 185, 129, 0.4);"><i class="fa-solid fa-cloud-arrow-up"></i> Commit Meal to Sparky (+XP)</button>';
        html += '</div>';
        html += '</div>';

        if (modalDesc) modalDesc.innerHTML = html;
        if (window.openModal) window.openModal();

        function updateReviewTotals() {
            var totalCal = 0, totalPro = 0, totalCarb = 0, totalFat = 0;
            itemStates.forEach(function (state, idx) {
                var mult = state.multiplier;
                var cal = Math.round(state.baseCal * mult);
                var pro = Math.round(state.basePro * mult);

                var elCal = document.getElementById('val-cal-' + idx);
                var elPro = document.getElementById('val-pro-' + idx);
                var elMult = document.getElementById('val-mult-' + idx);
                if (elCal) elCal.textContent = cal + ' kcal';
                if (elPro) elPro.textContent = pro + 'g P';
                if (elMult) elMult.textContent = mult.toFixed(1) + 'x';

                if (state.selected) {
                    totalCal += state.baseCal * mult;
                    totalPro += state.basePro * mult;
                    totalCarb += state.baseCarb * mult;
                    totalFat += state.baseFat * mult;
                }
            });

            var sumCal = document.getElementById('sum-cal');
            var sumPro = document.getElementById('sum-pro');
            var sumCarb = document.getElementById('sum-carb');
            var sumFat = document.getElementById('sum-fat');
            if (sumCal) sumCal.textContent = Math.round(totalCal);
            if (sumPro) sumPro.textContent = Math.round(totalPro) + 'g';
            if (sumCarb) sumCarb.textContent = Math.round(totalCarb) + 'g';
            if (sumFat) sumFat.textContent = Math.round(totalFat) + 'g';
        }

        // Bind checkboxes
        items.forEach(function (it, idx) {
            var chk = document.getElementById('chk-item-' + idx);
            if (chk) {
                chk.onchange = function () {
                    itemStates[idx].selected = chk.checked;
                    var row = document.getElementById('review-item-' + idx);
                    if (row) {
                        row.style.opacity = chk.checked ? '1' : '0.4';
                    }
                    updateReviewTotals();
                };
            }
        });

        // Bind stepper buttons
        var subButtons = modalDesc.querySelectorAll('.btn-step-sub');
        subButtons.forEach(function (btn) {
            btn.onclick = function () {
                var idx = parseInt(btn.getAttribute('data-idx'), 10);
                if (itemStates[idx] && itemStates[idx].multiplier > 0.5) {
                    itemStates[idx].multiplier = Math.max(0.5, Math.round((itemStates[idx].multiplier - 0.5) * 10) / 10);
                    updateReviewTotals();
                }
            };
        });

        var addButtons = modalDesc.querySelectorAll('.btn-step-add');
        addButtons.forEach(function (btn) {
            btn.onclick = function () {
                var idx = parseInt(btn.getAttribute('data-idx'), 10);
                if (itemStates[idx] && itemStates[idx].multiplier < 5.0) {
                    itemStates[idx].multiplier = Math.round((itemStates[idx].multiplier + 0.5) * 10) / 10;
                    updateReviewTotals();
                }
            };
        });

        // Initialize totals
        updateReviewTotals();

        var btnCommit = document.getElementById('btn-snap-commit');
        if (btnCommit) {
            btnCommit.onclick = function () {
                var selectedItems = [];
                itemStates.forEach(function (state) {
                    if (state.selected) {
                        var copy = Object.assign({}, state.raw);
                        copy.quantity = state.multiplier;
                        copy.calories = Math.round(state.baseCal * state.multiplier);
                        copy.protein = Math.round(state.basePro * state.multiplier);
                        copy.carbs = Math.round(state.baseCarb * state.multiplier);
                        copy.fat = Math.round(state.baseFat * state.multiplier);
                        selectedItems.push(copy);
                    }
                });

                if (!selectedItems.length) {
                    alert('Please select at least one food item to log.');
                    return;
                }

                btnCommit.disabled = true;
                btnCommit.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Logging ' + selectedItems.length + ' item(s) to Sparky...';

                var dateInp = document.getElementById('snap-commit-date');
                var commitDate = (dateInp && dateInp.value) ? dateInp.value : activeDateVal;

                fetch('/api/v1/nutrition/snaps/' + draft.id + '/commit/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCookie('csrftoken') || ''
                    },
                    body: JSON.stringify({
                        items: selectedItems,
                        meal_type: draft.meal_type || 'Lunch',
                        entry_date: commitDate
                    })
                })
                .then(function (res) { return res.json(); })
                .then(function (resData) {
                    if (resData.success) {
                        if (window.closeModal) window.closeModal();
                        if (window.showToast) {
                            window.showToast('Logged ' + selectedItems.length + ' item(s) to SparkyFitness! (+' + (resData.xp_awarded || 0) + ' XP)');
                        }
                        var refreshDate = resData.entry_date || commitDate;
                        if (window.loadNutrition) window.loadNutrition(refreshDate);
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
            resultsList.innerHTML = '<div style="padding: 12px; text-align: center; color: #94a3b8;"><i class="fa-solid fa-spinner fa-spin"></i> Searching Sparky database & external catalogs...</div>';
            fetch('/api/v1/nutrition/search-foods/?q=' + encodeURIComponent(q) + '&expand=true')
                .then(function (res) { return res.json(); })
                .then(function (data) {
                    var items = data.results || [];
                    resultsList.innerHTML = '';

                    if (!items.length) {
                        resultsList.innerHTML = '<div style="padding: 12px; text-align: center; color: #64748b;">No matching foods found in database or external catalogs.</div>';
                    } else {
                        items.forEach(function (f) {
                            var badgeHtml = '';
                            if (f.source === 'sparky_openfoodfacts') {
                                badgeHtml = '<span style="background: rgba(14, 165, 233, 0.2); color: #38bdf8; font-size: 0.68rem; padding: 2px 6px; border-radius: 6px; font-weight: 700; margin-left: 6px;"><i class="fa-solid fa-earth-americas"></i> Open Food Facts</span>';
                            } else if (f.source === 'sparky_ai') {
                                badgeHtml = '<span style="background: rgba(168, 85, 247, 0.2); color: #c084fc; font-size: 0.68rem; padding: 2px 6px; border-radius: 6px; font-weight: 700; margin-left: 6px;"><i class="fa-solid fa-wand-magic-sparkles"></i> Sparky AI</span>';
                            } else if (f.is_custom) {
                                badgeHtml = '<span style="background: rgba(234, 179, 8, 0.2); color: #facc15; font-size: 0.68rem; padding: 2px 6px; border-radius: 6px; font-weight: 700; margin-left: 6px;">Custom</span>';
                            }

                            var card = document.createElement('div');
                            card.className = 'food-result-item';
                            card.innerHTML = '<div>' +
                                '<div style="font-weight: 800; font-size: 0.9rem; color: #fff; display: flex; align-items: center; flex-wrap: wrap;">' + f.name + badgeHtml + '</div>' +
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
                                window.openPortionLogModal(f);
                            };
                            resultsList.appendChild(card);
                        });
                    }

                    // Always provide option to create new food with Sparky AI
                    var aiBanner = document.createElement('div');
                    aiBanner.style.cssText = 'background: linear-gradient(135deg, rgba(168, 85, 247, 0.15) 0%, rgba(126, 34, 206, 0.15) 100%); border: 1px dashed rgba(168, 85, 247, 0.4); border-radius: 12px; padding: 12px; margin-top: 10px; display: flex; justify-content: space-between; align-items: center; gap: 10px;';
                    aiBanner.innerHTML = '<div>' +
                        '<div style="font-weight: 800; font-size: 0.88rem; color: #e9d5ff;"><i class="fa-solid fa-wand-magic-sparkles"></i> Make with Sparky AI</div>' +
                        '<div style="font-size: 0.75rem; color: #cbd5e1;">Generate macros and save as a new food.</div>' +
                        '</div>' +
                        '<button type="button" id="btn-make-ai-food" style="padding: 8px 14px; background: #a855f7; border: none; border-radius: 10px; color: #fff; font-weight: 800; font-size: 0.8rem; cursor: pointer; white-space: nowrap;"><i class="fa-solid fa-plus"></i> Make with AI</button>';
                    resultsList.appendChild(aiBanner);

                    var btnAi = aiBanner.querySelector('#btn-make-ai-food');
                    if (btnAi) {
                        btnAi.onclick = function (e) {
                            e.stopPropagation();
                            window.openCreateFoodAiModal(q);
                        };
                    }
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

    // Open Create Food with Sparky AI Modal
    window.openCreateFoodAiModal = function (initialName) {
        if (window.closeModal) window.closeModal();

        var modalTitle = document.getElementById('modal-title');
        var modalDesc = document.getElementById('modal-desc');
        var modalAction = document.getElementById('modal-action');
        var modalIcon = document.querySelector('.modal-icon i');

        if (modalTitle) modalTitle.textContent = 'Create Food with Sparky AI';
        if (modalIcon) modalIcon.className = 'fa-solid fa-wand-magic-sparkles';
        if (modalAction) modalAction.style.display = 'none';

        var queryName = initialName || '';
        var html = '<div style="text-align: left;">';
        html += '<p style="color: #94a3b8; font-size: 0.85rem; margin-bottom: 12px;">Ask Sparky AI to estimate macros and save as a new custom food in your SparkyFitness database.</p>';

        html += '<div style="margin-bottom: 10px;">';
        html += '<label style="display: block; font-size: 0.75rem; font-weight: 800; color: #cbd5e1; text-transform: uppercase; margin-bottom: 4px;">Food Name / Meal</label>';
        html += '<div style="display: flex; gap: 8px;">';
        html += '<input type="text" id="ai-food-name" value="' + queryName.replace(/"/g, '&quot;') + '" placeholder="e.g. Teriyaki Salmon with Quinoa" style="flex: 1; padding: 10px; background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 12px; color: #fff; font-size: 0.9rem;" />';
        html += '<button type="button" id="btn-trigger-ai" style="padding: 10px 14px; background: linear-gradient(135deg, #a855f7 0%, #7e22ce 100%); border: none; border-radius: 12px; color: #fff; font-weight: 800; font-size: 0.82rem; cursor: pointer; white-space: nowrap;"><i class="fa-solid fa-wand-sparkles"></i> Generate</button>';
        html += '</div>';
        html += '</div>';

        var activeDateVal = window._activeNutritionDate || new Date().toISOString().split('T')[0];

        html += '<div style="background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; padding: 10px; margin-bottom: 12px;">';
        html += '<div style="font-size: 0.72rem; font-weight: 800; color: #94a3b8; text-transform: uppercase; margin-bottom: 6px;"><i class="fa-solid fa-calculator"></i> Base Profile (Per 1 Serving)</div>';
        html += '<div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; margin-bottom: 8px;">';
        html += '<div>';
        html += '<label style="display: block; font-size: 0.7rem; font-weight: 700; color: #cbd5e1; margin-bottom: 2px;">Serving Desc</label>';
        html += '<input type="text" id="ai-food-serving" value="1 serving" placeholder="e.g. 1 bar, 100g" style="width: 100%; padding: 8px; background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 10px; color: #fff; font-size: 0.82rem;" />';
        html += '</div>';
        html += '<div>';
        html += '<label style="display: block; font-size: 0.7rem; font-weight: 700; color: #cbd5e1; margin-bottom: 2px;">Meal Slot</label>';
        html += '<select id="ai-food-meal-type" style="width: 100%; padding: 8px; background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 10px; color: #fff; font-weight: 700; font-size: 0.82rem;">';
        html += '<option value="Breakfast">Breakfast</option><option value="Lunch" selected>Lunch</option><option value="Dinner">Dinner</option><option value="Snack">Snack</option>';
        html += '</select>';
        html += '</div>';
        html += '<div>';
        html += '<label style="display: block; font-size: 0.7rem; font-weight: 700; color: #cbd5e1; margin-bottom: 2px;"><i class="fa-regular fa-calendar text-purple-400 mr-1"></i> Date</label>';
        html += '<input type="date" id="ai-food-date" value="' + activeDateVal + '" style="width: 100%; padding: 7px 8px; background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 10px; color: #fff; font-weight: 700; font-size: 0.8rem;" />';
        html += '</div>';
        html += '</div>';

        html += '<div style="display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 6px;">';
        html += '<div><label style="display: block; font-size: 0.68rem; font-weight: 800; color: #94a3b8; margin-bottom: 2px;">Calories</label><input type="number" id="ai-food-cal" value="0" style="width: 100%; padding: 8px; background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 10px; color: #fff; font-weight: 800; text-align: center;" /></div>';
        html += '<div><label style="display: block; font-size: 0.68rem; font-weight: 800; color: #c084fc; margin-bottom: 2px;">Protein (g)</label><input type="number" id="ai-food-pro" value="0" style="width: 100%; padding: 8px; background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 10px; color: #c084fc; font-weight: 800; text-align: center;" /></div>';
        html += '<div><label style="display: block; font-size: 0.68rem; font-weight: 800; color: #38bdf8; margin-bottom: 2px;">Carbs (g)</label><input type="number" id="ai-food-carb" value="0" style="width: 100%; padding: 8px; background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 10px; color: #38bdf8; font-weight: 800; text-align: center;" /></div>';
        html += '<div><label style="display: block; font-size: 0.68rem; font-weight: 800; color: #fbbf24; margin-bottom: 2px;">Fat (g)</label><input type="number" id="ai-food-fat" value="0" style="width: 100%; padding: 8px; background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 10px; color: #fbbf24; font-weight: 800; text-align: center;" /></div>';
        html += '</div>';
        html += '</div>';

        // Servings Consumed section
        html += '<div style="background: rgba(168, 85, 247, 0.12); border: 1px solid rgba(168, 85, 247, 0.35); border-radius: 12px; padding: 12px; margin-bottom: 14px;">';
        html += '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">';
        html += '<label style="font-size: 0.78rem; font-weight: 800; color: #e9d5ff; text-transform: uppercase;"><i class="fa-solid fa-utensils"></i> Servings Consumed</label>';
        html += '<span style="font-size: 0.7rem; color: #94a3b8;">(1 serving in DB = base macros)</span>';
        html += '</div>';
        html += '<div style="display: flex; align-items: center; justify-content: center; gap: 10px; margin-bottom: 8px;">';
        html += '<button type="button" id="ai-qty-minus" style="width: 40px; height: 40px; border-radius: 10px; background: rgba(30, 41, 59, 0.9); border: 1px solid rgba(255, 255, 255, 0.2); color: #fff; font-size: 1.2rem; font-weight: 900; cursor: pointer;">-</button>';
        html += '<input type="number" id="ai-food-qty" value="1.0" step="0.25" min="0.1" style="width: 85px; height: 40px; text-align: center; font-size: 1.2rem; font-weight: 900; color: #00F0FF; background: rgba(15, 23, 42, 0.9); border: 1px solid rgba(0, 240, 255, 0.4); border-radius: 10px;" />';
        html += '<button type="button" id="ai-qty-plus" style="width: 40px; height: 40px; border-radius: 10px; background: rgba(30, 41, 59, 0.9); border: 1px solid rgba(255, 255, 255, 0.2); color: #fff; font-size: 1.2rem; font-weight: 900; cursor: pointer;">+</button>';
        html += '</div>';
        html += '<div style="display: flex; gap: 6px; justify-content: center; margin-bottom: 10px;">';
        [0.5, 1.0, 1.5, 2.0, 3.0].forEach(function (preset) {
            html += '<button type="button" class="ai-qty-pill" data-val="' + preset + '" style="padding: 4px 10px; border-radius: 6px; border: 1px solid rgba(255, 255, 255, 0.15); background: rgba(30, 41, 59, 0.6); color: #cbd5e1; font-weight: 700; font-size: 0.75rem; cursor: pointer;">' + preset + 'x</button>';
        });
        html += '</div>';
        html += '<div id="ai-total-preview" style="text-align: center; font-size: 0.88rem; font-weight: 800; color: #fff; padding-top: 6px; border-top: 1px solid rgba(255, 255, 255, 0.1);">';
        html += 'Logging <span id="ai-tot-lbl" style="color: #00F0FF;">1.0</span> serving(s): <span id="ai-tot-cal" style="color: #4ade80;">0 cal</span> • <span id="ai-tot-pro" style="color: #c084fc;">0g Protein</span> • <span id="ai-tot-carb" style="color: #38bdf8;">0g Carbs</span> • <span id="ai-tot-fat" style="color: #fbbf24;">0g Fat</span>';
        html += '</div>';
        html += '</div>';

        html += '<div style="display: flex; gap: 8px;">';
        html += '<button type="button" id="btn-save-and-log" style="flex: 1; padding: 12px; background: linear-gradient(135deg, #10b981 0%, #059669 100%); border: none; border-radius: 12px; color: #fff; font-weight: 800; font-size: 0.88rem; cursor: pointer; box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);"><i class="fa-solid fa-cloud-arrow-up"></i> Save & Log (+XP)</button>';
        html += '<button type="button" id="btn-save-only" style="padding: 12px 14px; background: rgba(30, 41, 59, 0.9); border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 12px; color: #e2e8f0; font-weight: 700; font-size: 0.82rem; cursor: pointer;">Save to DB Only</button>';
        html += '</div>';

        html += '</div>';

        if (modalDesc) modalDesc.innerHTML = html;
        if (window.openModal) window.openModal();

        var qtyInput = document.getElementById('ai-food-qty');
        var btnMinus = document.getElementById('ai-qty-minus');
        var btnPlus = document.getElementById('ai-qty-plus');
        var btnSaveLog = document.getElementById('btn-save-and-log');
        var btnSaveOnly = document.getElementById('btn-save-only');

        function updateAiPreview() {
            var q = parseFloat(qtyInput ? qtyInput.value : 1.0) || 1.0;
            if (q < 0.1) q = 0.1;
            var cal = parseFloat(document.getElementById('ai-food-cal').value) || 0;
            var pro = parseFloat(document.getElementById('ai-food-pro').value) || 0;
            var carb = parseFloat(document.getElementById('ai-food-carb').value) || 0;
            var fat = parseFloat(document.getElementById('ai-food-fat').value) || 0;

            var totCal = Math.round(cal * q);
            var totPro = Math.round(pro * q * 10) / 10;
            var totCarb = Math.round(carb * q * 10) / 10;
            var totFat = Math.round(fat * q * 10) / 10;

            var lbl = document.getElementById('ai-tot-lbl');
            var cEl = document.getElementById('ai-tot-cal');
            var pEl = document.getElementById('ai-tot-pro');
            var cbEl = document.getElementById('ai-tot-carb');
            var fEl = document.getElementById('ai-tot-fat');

            if (lbl) lbl.textContent = q;
            if (cEl) cEl.textContent = totCal + ' cal';
            if (pEl) pEl.textContent = totPro + 'g Protein';
            if (cbEl) cbEl.textContent = totCarb + 'g Carbs';
            if (fEl) fEl.textContent = totFat + 'g Fat';

            if (btnSaveLog) {
                btnSaveLog.innerHTML = '<i class="fa-solid fa-cloud-arrow-up"></i> Save & Log ' + q + ' Serving' + (q === 1 ? '' : 's') + ' (' + totCal + ' cal / +XP)';
            }
        }

        if (btnMinus) {
            btnMinus.onclick = function () {
                var q = (parseFloat(qtyInput.value) || 1.0) - 0.5;
                if (q < 0.5) q = 0.25;
                qtyInput.value = q;
                updateAiPreview();
            };
        }
        if (btnPlus) {
            btnPlus.onclick = function () {
                var q = (parseFloat(qtyInput.value) || 1.0) + 0.5;
                qtyInput.value = q;
                updateAiPreview();
            };
        }
        if (qtyInput) {
            qtyInput.oninput = updateAiPreview;
        }

        ['ai-food-cal', 'ai-food-pro', 'ai-food-carb', 'ai-food-fat'].forEach(function (id) {
            var el = document.getElementById(id);
            if (el) el.oninput = updateAiPreview;
        });

        document.querySelectorAll('.ai-qty-pill').forEach(function (pill) {
            pill.onclick = function () {
                if (qtyInput) {
                    qtyInput.value = pill.getAttribute('data-val');
                    updateAiPreview();
                }
            };
        });

        function triggerAiGeneration() {
            var nameVal = document.getElementById('ai-food-name').value.trim();
            var servingVal = document.getElementById('ai-food-serving').value.trim();
            if (!nameVal) {
                alert('Please enter a food name to generate.');
                return;
            }
            var btnGen = document.getElementById('btn-trigger-ai');
            btnGen.disabled = true;
            btnGen.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Estimating...';

            fetch('/api/v1/nutrition/ai-generate-food/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken') || ''
                },
                body: JSON.stringify({ food_name: nameVal, unit: servingVal })
            })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                btnGen.disabled = false;
                btnGen.innerHTML = '<i class="fa-solid fa-wand-sparkles"></i> Generate';
                if (data.success && data.food) {
                    var f = data.food;
                    document.getElementById('ai-food-cal').value = Math.round(f.calories || 0);
                    document.getElementById('ai-food-pro').value = Math.round(f.protein || 0);
                    document.getElementById('ai-food-carb').value = Math.round(f.carbs || 0);
                    document.getElementById('ai-food-fat').value = Math.round(f.fat || 0);
                    if (f.serving) document.getElementById('ai-food-serving').value = f.serving;
                    updateAiPreview();
                    if (window.showToast) window.showToast('✨ Sparky AI estimated nutritional profile!');
                }
            })
            .catch(function () {
                btnGen.disabled = false;
                btnGen.innerHTML = '<i class="fa-solid fa-wand-sparkles"></i> Generate';
            });
        }

        var btnTrigger = document.getElementById('btn-trigger-ai');
        if (btnTrigger) btnTrigger.onclick = triggerAiGeneration;

        // Auto-trigger if queryName provided
        if (queryName) {
            triggerAiGeneration();
        }

        if (btnSaveLog) {
            btnSaveLog.onclick = function () {
                var nameVal = document.getElementById('ai-food-name').value.trim();
                var servingVal = document.getElementById('ai-food-serving').value.trim();
                var mealVal = document.getElementById('ai-food-meal-type').value;
                var calVal = parseFloat(document.getElementById('ai-food-cal').value) || 0;
                var proVal = parseFloat(document.getElementById('ai-food-pro').value) || 0;
                var carbVal = parseFloat(document.getElementById('ai-food-carb').value) || 0;
                var fatVal = parseFloat(document.getElementById('ai-food-fat').value) || 0;
                var qVal = parseFloat(qtyInput ? qtyInput.value : 1.0) || 1.0;

                if (!nameVal) {
                    alert('Food name is required.');
                    return;
                }

                var dateInp = document.getElementById('ai-food-date');
                var chosenDate = (dateInp && dateInp.value) ? dateInp.value : activeDateVal;

                btnSaveLog.disabled = true;
                btnSaveLog.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving & Logging...';

                window.quickLogFood({
                    name: nameVal,
                    food_name: nameVal,
                    base_calories: calVal,
                    base_protein: proVal,
                    base_carbs: carbVal,
                    base_fat: fatVal,
                    calories: Math.round(calVal * qVal * 10) / 10,
                    protein: Math.round(proVal * qVal * 10) / 10,
                    carbs: Math.round(carbVal * qVal * 10) / 10,
                    fat: Math.round(fatVal * qVal * 10) / 10,
                    serving: servingVal,
                    unit: servingVal,
                    brand: 'Sparky AI',
                    create_custom: true,
                    meal_type: mealVal,
                    entry_date: chosenDate
                }, qVal, chosenDate);

                if (window.closeModal) window.closeModal();
            };
        }

        if (btnSaveOnly) {
            btnSaveOnly.onclick = function () {
                var nameVal = document.getElementById('ai-food-name').value.trim();
                var servingVal = document.getElementById('ai-food-serving').value.trim();
                var calVal = parseFloat(document.getElementById('ai-food-cal').value) || 0;
                var proVal = parseFloat(document.getElementById('ai-food-pro').value) || 0;
                var carbVal = parseFloat(document.getElementById('ai-food-carb').value) || 0;
                var fatVal = parseFloat(document.getElementById('ai-food-fat').value) || 0;

                btnSaveOnly.disabled = true;
                btnSaveOnly.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving...';

                fetch('/api/v1/nutrition/create-food/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCookie('csrftoken') || ''
                    },
                    body: JSON.stringify({
                        food_name: nameVal,
                        calories: calVal,
                        protein: proVal,
                        carbs: carbVal,
                        fat: fatVal,
                        unit: servingVal,
                        brand: 'Sparky AI'
                    })
                })
                .then(function (res) { return res.json(); })
                .then(function (data) {
                    if (data.success) {
                        if (window.closeModal) window.closeModal();
                        if (window.showToast) window.showToast('✅ Saved ' + nameVal + ' to Sparky database!');
                    } else {
                        alert('Could not save food: ' + (data.error || 'Server error'));
                        btnSaveOnly.disabled = false;
                        btnSaveOnly.innerHTML = 'Save to DB Only';
                    }
                })
                .catch(function () {
                    alert('Error saving custom food.');
                    btnSaveOnly.disabled = false;
                    btnSaveOnly.innerHTML = 'Save to DB Only';
                });
            };
        }
    };

    // Open Barcode Scanner Modal
    window.openBarcodeScannerModal = function () {
        if (window.closeModal) window.closeModal();

        var modalTitle = document.getElementById('modal-title');
        var modalDesc = document.getElementById('modal-desc');
        var modalAction = document.getElementById('modal-action');
        var modalIcon = document.querySelector('.modal-icon i');

        if (modalTitle) modalTitle.textContent = 'Scan Food Barcode';
        if (modalIcon) modalIcon.className = 'fa-solid fa-barcode';
        if (modalAction) modalAction.style.display = 'none';

        var html = '<div style="text-align: left;">';
        html += '<p style="color: #94a3b8; font-size: 0.85rem; margin-bottom: 12px;">Aim your camera at the barcode on any packaged food or drink to look up verified macros.</p>';

        html += '<div id="barcode-viewport-wrap" style="position: relative; width: 100%; height: 220px; background: #0f172a; border-radius: 16px; overflow: hidden; border: 2px solid rgba(168, 85, 247, 0.4); margin-bottom: 10px; display: flex; align-items: center; justify-content: center;">';
        html += '<video id="barcode-video" playsinline autoplay muted style="width: 100%; height: 100%; object-fit: cover;"></video>';
        html += '<div style="position: absolute; width: 75%; height: 130px; border: 2px dashed #a855f7; border-radius: 12px; box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.45); pointer-events: none; display: flex; align-items: center; justify-content: center;">';
        html += '<div style="width: 90%; height: 2px; background: #00F0FF; box-shadow: 0 0 10px #00F0FF;"></div>';
        html += '</div>';
        html += '<div id="barcode-cam-status" style="position: absolute; bottom: 8px; font-size: 0.75rem; color: #e2e8f0; background: rgba(15, 23, 42, 0.85); padding: 4px 10px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.1); max-width: 90%; text-align: center;">Initializing camera...</div>';
        html += '</div>';

        html += '<div style="display: flex; gap: 8px; margin-bottom: 12px;">';
        html += '<button type="button" id="btn-snap-barcode-photo" style="flex: 1; padding: 10px; background: rgba(168, 85, 247, 0.18); border: 1px dashed rgba(168, 85, 247, 0.6); border-radius: 12px; color: #e9d5ff; font-weight: 800; font-size: 0.85rem; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 6px;"><i class="fa-solid fa-camera"></i> Snap Barcode Photo</button>';
        html += '<button type="button" id="btn-restart-cam" style="padding: 10px 14px; background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 12px; color: #cbd5e1; font-weight: 700; font-size: 0.85rem; cursor: pointer;" title="Restart Camera"><i class="fa-solid fa-arrows-rotate"></i></button>';
        html += '</div>';
        html += '<input type="file" id="barcode-file-input" accept="image/*" capture="environment" style="display: none;" />';

        html += '<div style="margin-bottom: 14px;">';
        html += '<div style="display: flex; gap: 8px;">';
        html += '<input type="text" id="manual-barcode-input" placeholder="Or enter barcode numbers (e.g. 012345678905)" style="flex: 1; padding: 10px; background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 12px; color: #fff; font-size: 0.85rem;" />';
        html += '<button type="button" id="btn-manual-barcode-lookup" style="padding: 10px 14px; background: linear-gradient(135deg, #a855f7 0%, #7e22ce 100%); border: none; border-radius: 12px; color: #fff; font-weight: 800; font-size: 0.85rem; cursor: pointer;">Lookup</button>';
        html += '</div>';
        html += '</div>';

        html += '<div id="barcode-result-card" style="display: none; background: rgba(30, 41, 59, 0.9); border: 1px solid rgba(168, 85, 247, 0.4); border-radius: 14px; padding: 12px; margin-bottom: 14px;"></div>';

        html += '</div>';

        if (modalDesc) modalDesc.innerHTML = html;
        if (window.openModal) window.openModal();

        var video = document.getElementById('barcode-video');
        var camStatus = document.getElementById('barcode-cam-status');
        var resultCard = document.getElementById('barcode-result-card');
        var activeStream = null;
        var scanning = true;

        function stopCamera() {
            scanning = false;
            if (activeStream) {
                activeStream.getTracks().forEach(function (track) { track.stop(); });
                activeStream = null;
            }
        }

        function handleBarcodeFound(code) {
            if (!code || !scanning) return;
            scanning = false;
            stopCamera();

            if (window.FlamingoNative && window.FlamingoNative.haptic) {
                window.FlamingoNative.haptic('medium');
            }

            if (camStatus) camStatus.textContent = 'Found barcode: ' + code;
            if (resultCard) {
                resultCard.style.display = 'block';
                resultCard.innerHTML = '<div style="text-align: center; color: #94a3b8; padding: 12px;"><i class="fa-solid fa-spinner fa-spin"></i> Looking up barcode in Sparky...</div>';
            }

            fetch('/api/v1/nutrition/barcode/?code=' + encodeURIComponent(code))
                .then(function (res) { return res.json(); })
                .then(function (data) {
                    if (data.success && data.food) {
                        var f = data.food;
                        var cardHtml = '<div style="margin-bottom: 8px;">';
                        cardHtml += '<div style="font-weight: 800; font-size: 1rem; color: #fff;">' + f.name + '</div>';
                        cardHtml += '<div style="font-size: 0.78rem; color: #94a3b8;">' + (f.brand ? f.brand + ' • ' : '') + f.serving + '</div>';
                        cardHtml += '</div>';

                        cardHtml += '<div style="display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 6px; background: rgba(15, 23, 42, 0.6); padding: 8px; border-radius: 10px; margin-bottom: 12px; text-align: center;">';
                        cardHtml += '<div><div style="font-size: 0.7rem; color: #94a3b8; font-weight: 700;">CAL</div><div style="font-weight: 800; color: #fff;">' + Math.round(f.calories || 0) + '</div></div>';
                        cardHtml += '<div><div style="font-size: 0.7rem; color: #c084fc; font-weight: 700;">PRO</div><div style="font-weight: 800; color: #c084fc;">' + Math.round(f.protein || 0) + 'g</div></div>';
                        cardHtml += '<div><div style="font-size: 0.7rem; color: #38bdf8; font-weight: 700;">CARB</div><div style="font-weight: 800; color: #38bdf8;">' + Math.round(f.carbs || 0) + 'g</div></div>';
                        cardHtml += '<div><div style="font-size: 0.7rem; color: #fbbf24; font-weight: 700;">FAT</div><div style="font-weight: 800; color: #fbbf24;">' + Math.round(f.fat || 0) + 'g</div></div>';
                        cardHtml += '</div>';

                        cardHtml += '<div style="display: flex; gap: 8px;">';
                        cardHtml += '<button type="button" id="btn-barcode-log" style="flex: 1; padding: 12px; background: linear-gradient(135deg, #10b981 0%, #059669 100%); border: none; border-radius: 12px; color: #fff; font-weight: 800; font-size: 0.9rem; cursor: pointer; box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);"><i class="fa-solid fa-plus"></i> Log to Sparky (+XP)</button>';
                        cardHtml += '<button type="button" id="btn-barcode-rescan" style="padding: 12px 14px; background: rgba(30, 41, 59, 0.9); border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 12px; color: #e2e8f0; font-weight: 700; font-size: 0.85rem; cursor: pointer;"><i class="fa-solid fa-arrows-rotate"></i> Rescan</button>';
                        cardHtml += '</div>';

                        resultCard.innerHTML = cardHtml;

                        var btnLog = document.getElementById('btn-barcode-log');
                        if (btnLog) {
                            btnLog.onclick = function () {
                                if (window.closeModal) window.closeModal();
                                window.openPortionLogModal(f);
                            };
                        }

                        var btnRescan = document.getElementById('btn-barcode-rescan');
                        if (btnRescan) {
                            btnRescan.onclick = function () {
                                resultCard.style.display = 'none';
                                scanning = true;
                                startCamera();
                            };
                        }
                    } else {
                        resultCard.innerHTML = '<div style="text-align: center; color: #f87171; padding: 10px;">Barcode not found. Try searching by name or generate with Sparky AI.</div><button type="button" id="btn-barcode-search-fallback" style="width: 100%; margin-top: 8px; padding: 10px; background: #a855f7; border: none; border-radius: 10px; color: #fff; font-weight: 800;">Search or Make with AI</button>';
                        var btnFall = document.getElementById('btn-barcode-search-fallback');
                        if (btnFall) {
                            btnFall.onclick = function () {
                                window.openSearchFoodsModal();
                            };
                        }
                    }
                })
                .catch(function () {
                    resultCard.innerHTML = '<div style="color: #ef4444; padding: 8px; text-align: center;">Error looking up barcode.</div>';
                });
        }

        function decodeImageElement(imgElement) {
            if (camStatus) camStatus.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Reading barcode from photo...';
            if ('BarcodeDetector' in window) {
                var detector = new window.BarcodeDetector({
                    formats: ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128', 'qr_code', 'code_39', 'itf']
                });
                detector.detect(imgElement)
                    .then(function (barcodes) {
                        if (barcodes && barcodes.length > 0) {
                            handleBarcodeFound(barcodes[0].rawValue);
                        } else {
                            if (camStatus) camStatus.textContent = 'No barcode detected in photo. Try another angle or manual entry below.';
                        }
                    })
                    .catch(function () {
                        if (camStatus) camStatus.textContent = 'Could not process photo barcode. Enter digits below.';
                    });
            } else {
                if (camStatus) camStatus.textContent = 'Barcode detector unavailable. Please enter digits below.';
            }
        }

        function setupDetector() {
            if ('BarcodeDetector' in window) {
                var detector = new window.BarcodeDetector({
                    formats: ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128', 'qr_code', 'code_39', 'itf']
                });

                function detectLoop() {
                    if (!scanning || !video) return;
                    detector.detect(video)
                        .then(function (barcodes) {
                            if (barcodes && barcodes.length > 0) {
                                handleBarcodeFound(barcodes[0].rawValue);
                            } else if (scanning) {
                                requestAnimationFrame(detectLoop);
                            }
                        })
                        .catch(function () {
                            if (scanning) requestAnimationFrame(detectLoop);
                        });
                }
                detectLoop();
            } else {
                if (camStatus) camStatus.textContent = 'Camera active (tap Snap Photo or enter code below)';
            }
        }

        function tryGetUserMedia(attempt) {
            attempt = attempt || 1;
            var constraints;
            if (attempt === 1) {
                constraints = { video: { facingMode: { ideal: 'environment' } } };
            } else if (attempt === 2) {
                constraints = { video: { facingMode: 'environment' } };
            } else {
                constraints = { video: true };
            }

            if (camStatus) camStatus.textContent = 'Requesting camera...';

            navigator.mediaDevices.getUserMedia(constraints)
                .then(function (stream) {
                    activeStream = stream;
                    if (video) {
                        video.srcObject = stream;
                        video.setAttribute('playsinline', 'true');
                        video.play().catch(function () {});
                    }
                    if (camStatus) camStatus.textContent = 'Point camera at barcode';
                    setupDetector();
                })
                .catch(function (err) {
                    if (attempt < 3) {
                        tryGetUserMedia(attempt + 1);
                    } else {
                        var errName = err && err.name ? err.name : 'Unavailable';
                        if (camStatus) camStatus.textContent = 'Camera ' + errName + '. Tap "Snap Barcode Photo" or enter below.';
                    }
                });
        }

        function startCamera() {
            scanning = true;

            // Prompt native permission if in Flutter shell
            if (window.FlamingoNative && window.FlamingoNative.requestCameraPermission) {
                window.FlamingoNative.requestCameraPermission();
            }

            window.onCameraPermissionResult = function (granted) {
                if (granted && !activeStream) {
                    tryGetUserMedia(1);
                }
            };

            if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
                tryGetUserMedia(1);
            } else {
                if (camStatus) camStatus.textContent = 'Live stream unsupported. Tap "Snap Barcode Photo" or enter code.';
            }
        }

        startCamera();

        var btnSnap = document.getElementById('btn-snap-barcode-photo');
        var fileInp = document.getElementById('barcode-file-input');
        if (btnSnap) {
            btnSnap.onclick = function () {
                if (window.FlamingoNative && window.FlamingoNative.snapFoodPhoto) {
                    window.onFoodPhotoCaptured = function (dataUrl) {
                        var img = new Image();
                        img.onload = function () { decodeImageElement(img); };
                        img.src = dataUrl;
                    };
                    window.FlamingoNative.snapFoodPhoto('camera');
                } else if (fileInp) {
                    fileInp.click();
                }
            };
        }

        if (fileInp) {
            fileInp.onchange = function (e) {
                var file = e.target.files && e.target.files[0];
                if (file) {
                    var reader = new FileReader();
                    reader.onload = function (evt) {
                        var img = new Image();
                        img.onload = function () { decodeImageElement(img); };
                        img.src = evt.target.result;
                    };
                    reader.readAsDataURL(file);
                }
            };
        }

        var btnRestart = document.getElementById('btn-restart-cam');
        if (btnRestart) {
            btnRestart.onclick = function () {
                stopCamera();
                startCamera();
            };
        }

        var btnManual = document.getElementById('btn-manual-barcode-lookup');
        var manualInput = document.getElementById('manual-barcode-input');
        if (btnManual && manualInput) {
            btnManual.onclick = function () {
                var val = manualInput.value.trim();
                if (val) {
                    handleBarcodeFound(val);
                }
            };
            manualInput.onkeydown = function (e) {
                if (e.key === 'Enter') {
                    btnManual.click();
                }
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

        var activeDateVal = window._activeNutritionDate || new Date().toISOString().split('T')[0];

        html += '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 16px;">';
        html += '<div>';
        html += '<label style="font-size: 0.78rem; font-weight: 800; color: #cbd5e1; text-transform: uppercase;">Meal Slot</label>';
        html += '<select id="custom-meal-slot" style="width: 100%; padding: 10px; background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; color: #fff; font-weight: 700; margin-top: 4px;"><option value="Breakfast">Breakfast</option><option value="Lunch" selected>Lunch</option><option value="Dinner">Dinner</option><option value="Snack">Snack</option></select>';
        html += '</div>';
        html += '<div>';
        html += '<label style="font-size: 0.78rem; font-weight: 800; color: #cbd5e1; text-transform: uppercase;"><i class="fa-regular fa-calendar text-purple-400 mr-1"></i> Date</label>';
        html += '<input type="date" id="custom-food-date" value="' + activeDateVal + '" style="width: 100%; padding: 9px 10px; background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; color: #fff; font-weight: 700; margin-top: 4px; font-size: 0.85rem;" />';
        html += '</div>';
        html += '</div>';

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
                var dateVal = (document.getElementById('custom-food-date') && document.getElementById('custom-food-date').value) || activeDateVal;

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
                    serving: '1 serving',
                    entry_date: dateVal
                }, 1.0, dateVal);
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

        var activeDateStr = data.selected_date || (data.today && data.today.date) || new Date().toISOString().split('T')[0];
        window._activeNutritionDate = activeDateStr;
        var todayStr = data.today_date || new Date().toISOString().split('T')[0];
        var isToday = Boolean(data.is_today !== undefined ? data.is_today : (activeDateStr === todayStr));

        function getRelativeDateLabel(dateStr, tStr) {
            if (dateStr === tStr) return 'Today';
            var d = new Date(dateStr + 'T12:00:00');
            var t = new Date(tStr + 'T12:00:00');
            var diffDays = Math.round((d - t) / (1000 * 60 * 60 * 24));
            if (diffDays === -1) return 'Yesterday';
            if (diffDays === 1) return 'Tomorrow';
            if (diffDays < 0) return Math.abs(diffDays) + ' days ago';
            return 'in ' + diffDays + ' days';
        }

        function formatDatePretty(dateStr) {
            try {
                var parts = dateStr.split('-');
                var d = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
                return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
            } catch (e) {
                return dateStr;
            }
        }

        function shiftDate(dateStr, days) {
            var parts = dateStr.split('-');
            var d = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
            d.setDate(d.getDate() + days);
            var y = d.getFullYear();
            var m = String(d.getMonth() + 1).padStart(2, '0');
            var day = String(d.getDate()).padStart(2, '0');
            return y + '-' + m + '-' + day;
        }

        // 1.5 Interactive Date Navigator Bar
        var dateNav = document.createElement('div');
        dateNav.className = 'nutrition-date-nav';
        dateNav.style.cssText = 'display: flex; align-items: center; justify-content: space-between; background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 14px; padding: 6px 10px; margin-bottom: 14px;';

        var prevBtn = document.createElement('button');
        prevBtn.type = 'button';
        prevBtn.id = 'btn-nut-prev-day';
        prevBtn.title = 'Previous Day';
        prevBtn.style.cssText = 'background: rgba(15, 23, 42, 0.85); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 10px; color: #cbd5e1; width: 36px; height: 36px; display: flex; align-items: center; justify-content: center; cursor: pointer; font-size: 0.9rem;';
        prevBtn.innerHTML = '<i class="fa-solid fa-chevron-left"></i>';
        prevBtn.onclick = function () {
            var pDate = shiftDate(activeDateStr, -1);
            if (window.loadNutrition) window.loadNutrition(pDate);
        };
        dateNav.appendChild(prevBtn);

        var centerWrap = document.createElement('div');
        centerWrap.style.cssText = 'display: flex; align-items: center; gap: 8px; cursor: pointer; position: relative; padding: 2px 10px;';
        centerWrap.title = 'Tap to pick any date';

        var calIcon = document.createElement('i');
        calIcon.className = 'fa-regular fa-calendar text-purple-400';
        calIcon.style.fontSize = '1.1rem';
        centerWrap.appendChild(calIcon);

        var textCol = document.createElement('div');
        textCol.style.textAlign = 'center';
        var mainDateText = document.createElement('div');
        mainDateText.style.cssText = 'font-weight: 800; font-size: 0.95rem; color: #fff; line-height: 1.2;';
        mainDateText.textContent = formatDatePretty(activeDateStr);
        textCol.appendChild(mainDateText);

        var subDateText = document.createElement('div');
        subDateText.style.cssText = 'font-size: 0.72rem; font-weight: 700; color: ' + (isToday ? '#4ade80' : '#c084fc') + ';';
        subDateText.textContent = getRelativeDateLabel(activeDateStr, todayStr);
        textCol.appendChild(subDateText);
        centerWrap.appendChild(textCol);

        var hiddenPicker = document.createElement('input');
        hiddenPicker.type = 'date';
        hiddenPicker.value = activeDateStr;
        hiddenPicker.style.cssText = 'position: absolute; opacity: 0; pointer-events: none; width: 0; height: 0;';
        hiddenPicker.onchange = function (e) {
            var chosen = e.target.value;
            if (chosen && window.loadNutrition) {
                window.loadNutrition(chosen);
            }
        };
        centerWrap.appendChild(hiddenPicker);

        centerWrap.onclick = function () {
            if (hiddenPicker.showPicker) {
                hiddenPicker.showPicker();
            } else {
                hiddenPicker.click();
            }
        };
        dateNav.appendChild(centerWrap);

        var rightSide = document.createElement('div');
        rightSide.style.cssText = 'display: flex; align-items: center; gap: 6px;';

        if (!isToday) {
            var todayBtn = document.createElement('button');
            todayBtn.type = 'button';
            todayBtn.style.cssText = 'background: rgba(168, 85, 247, 0.2); border: 1px solid rgba(168, 85, 247, 0.5); border-radius: 8px; color: #e9d5ff; font-weight: 800; font-size: 0.72rem; padding: 6px 10px; cursor: pointer;';
            todayBtn.textContent = 'Today';
            todayBtn.onclick = function () {
                if (window.loadNutrition) window.loadNutrition(todayStr);
            };
            rightSide.appendChild(todayBtn);
        }

        var nextBtn = document.createElement('button');
        nextBtn.type = 'button';
        nextBtn.id = 'btn-nut-next-day';
        nextBtn.title = 'Next Day';
        nextBtn.style.cssText = 'background: rgba(15, 23, 42, 0.85); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 10px; color: #cbd5e1; width: 36px; height: 36px; display: flex; align-items: center; justify-content: center; cursor: pointer; font-size: 0.9rem;';
        nextBtn.innerHTML = '<i class="fa-solid fa-chevron-right"></i>';
        nextBtn.onclick = function () {
            var nDate = shiftDate(activeDateStr, 1);
            if (window.loadNutrition) window.loadNutrition(nDate);
        };
        rightSide.appendChild(nextBtn);
        dateNav.appendChild(rightSide);

        hero.appendChild(dateNav);

        // 2. Header with Date & Status Badge
        var today = data.today || {};
        var head = document.createElement('div');
        head.style.display = 'flex';
        head.style.justifyContent = 'space-between';
        head.style.alignItems = 'center';
        head.style.marginBottom = '14px';

        var title = document.createElement('div');
        title.style.fontWeight = '900';
        title.style.fontSize = '1.05rem';
        title.style.color = '#fff';
        title.innerHTML = '<i class="fa-solid fa-utensils text-purple-400 mr-2"></i> ' + (isToday ? "Today's Macros" : (getRelativeDateLabel(activeDateStr, todayStr) + "'s Macros"));
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

        var scanBtn = document.createElement('button');
        scanBtn.className = 'nutrition-action-btn barcode-cta';
        scanBtn.innerHTML = '<i class="fa-solid fa-barcode"></i> Scan Code';
        scanBtn.onclick = function () {
            window.openBarcodeScannerModal();
        };
        actionsRow.appendChild(scanBtn);

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
                        window.openPortionLogModal(f);
                    };
                    grid.appendChild(card);
                });
            });

        // 7. Meals Timeline
        var timeline = document.createElement('div');
        timeline.className = 'today-intake-timeline';
        var tlHeader = document.createElement('div');
        tlHeader.className = 'today-intake-header';
        var dayTitle = isToday ? "Today's Logged Meals" : (formatDatePretty(activeDateStr) + "'s Meals");
        var entriesCount = (today.food_entries && today.food_entries.length) || 0;
        tlHeader.innerHTML = '<span><i class="fa-solid fa-list-check mr-1.5"></i> ' + dayTitle + '</span><span>' + entriesCount + ' items</span>';
        timeline.appendChild(tlHeader);

        if (today.food_entries && today.food_entries.length) {
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
        } else {
            var emptyItem = document.createElement('div');
            emptyItem.style.cssText = 'padding: 16px; text-align: center; color: #94a3b8; font-size: 0.85rem;';
            emptyItem.innerHTML = 'No meals logged for this day yet.<div style="font-size: 0.74rem; color: #64748b; margin-top: 4px;">Use Quick Log, Search DB, Barcode, or Snap to log food for ' + formatDatePretty(activeDateStr) + '.</div>';
            timeline.appendChild(emptyItem);
        }
        hero.appendChild(timeline);

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
                        if (window.loadNutrition) {
                            window.loadNutrition(day.date);
                        } else {
                            window.showDayDetailModal(day);
                        }
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
