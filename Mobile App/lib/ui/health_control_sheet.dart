import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';
import '../models/health_metrics.dart';
import '../services/api_service.dart';
import '../services/health_service.dart';

class HealthControlSheet extends StatefulWidget {
  final VoidCallback onRefreshWebView;
  final ValueChanged<String>? onExecuteJavaScript;

  const HealthControlSheet({
    super.key,
    required this.onRefreshWebView,
    this.onExecuteJavaScript,
  });

  @override
  State<HealthControlSheet> createState() => _HealthControlSheetState();
}

class _HealthControlSheetState extends State<HealthControlSheet> {
  final HealthService _healthService = HealthService();
  final ApiService _apiService = ApiService();

  bool _isChecking = true;
  bool _isAuthorized = false;
  bool _isSyncing = false;
  HealthMetrics? _latestMetrics;
  String? _syncMessage;
  bool? _syncSuccess;

  late TextEditingController _urlController;
  late TextEditingController _userController;
  final TextEditingController _waterController = TextEditingController(text: '8');

  @override
  void initState() {
    super.initState();
    _urlController = TextEditingController(text: _apiService.baseUrl);
    _userController = TextEditingController(text: _apiService.username ?? '');
    _loadState();
  }

  @override
  void dispose() {
    _urlController.dispose();
    _userController.dispose();
    _waterController.dispose();
    super.dispose();
  }

  Future<void> _loadState() async {
    setState(() => _isChecking = true);
    final authorized = await _healthService.checkPermissions();
    HealthMetrics? metrics;
    if (authorized) {
      metrics = await _healthService.fetchTodayMetrics();
    }
    if (mounted) {
      setState(() {
        _isAuthorized = authorized;
        _latestMetrics = metrics;
        _isChecking = false;
      });
    }
  }

  Future<void> _requestPermissions() async {
    HapticFeedback.mediumImpact();
    final ok = await _healthService.requestPermissions();
    if (mounted) {
      setState(() => _isAuthorized = ok);
      if (ok) {
        final metrics = await _healthService.fetchTodayMetrics();
        setState(() => _latestMetrics = metrics);
      } else {
        await _healthService.openHealthConnectSettings();
        setState(() {
          _syncMessage = 'Opening Health Connect Settings... Please grant permissions for Flamingo Fitness.';
        });
      }
    }
  }

  Future<void> _syncNow() async {
    HapticFeedback.selectionClick();
    setState(() {
      _isSyncing = true;
      _syncMessage = null;
      _syncSuccess = null;
    });

    final metrics = await _healthService.fetchTodayMetrics();
    final result = await _apiService.syncHealthData(metrics);

    HapticFeedback.heavyImpact();
    if (mounted) {
      setState(() {
        _isSyncing = false;
        _latestMetrics = metrics;
        _syncSuccess = result.success;
        if (result.success) {
          _syncMessage = '✨ Synced! +${result.totalXpAwarded} XP awarded (${result.syncedLogsCount} logs)';
          if (result.newlyAwardedBadges.isNotEmpty) {
            _syncMessage = '$_syncMessage | 🏅 ${result.newlyAwardedBadges.length} new badges!';
          }
        } else {
          _syncMessage = result.message ?? 'Sync failed. Check server connection.';
        }
      });
      if (result.success) {
        widget.onRefreshWebView();
      }
    }
  }

  Future<void> _logWater(double oz) async {
    HapticFeedback.mediumImpact();
    setState(() {
      _isSyncing = true;
      _syncMessage = null;
      _syncSuccess = null;
    });

    bool wrote = false;
    try {
      wrote = await _healthService.writeWater(oz);
    } catch (e) {
      debugPrint('Health write error: $e');
    }

    HealthMetrics? metrics;
    try {
      metrics = await _healthService.fetchTodayMetrics();
    } catch (e) {
      debugPrint('Error fetching metrics after water write: $e');
    }

    // If Health Connect write was skipped or unavailable, optimistically increment local water
    if (!wrote) {
      final currentWaterMl = _latestMetrics?.waterMl ?? 0.0;
      final addedMl = oz * 29.5735;
      metrics = (_latestMetrics ?? HealthMetrics.empty()).copyWith(
        waterMl: currentWaterMl + addedMl,
      );
    }

    final result = await _apiService.syncHealthData(metrics ?? _latestMetrics ?? HealthMetrics.empty());

    if (mounted) {
      setState(() {
        _isSyncing = false;
        _latestMetrics = metrics ?? _latestMetrics;
        _syncSuccess = true;
        if (wrote) {
          _syncMessage = '💧 Logged ${oz.toStringAsFixed(0)} oz → Health Connect & Flamingo (+${result.totalXpAwarded} XP)';
        } else {
          _syncMessage = '💧 Logged ${oz.toStringAsFixed(0)} oz to Flamingo (+${result.totalXpAwarded} XP). Grant Health Connect access to sync on device.';
        }
      });
      if (result.success) widget.onRefreshWebView();
    }
  }

  Future<void> _snapMealCamera() async {
    try {
      HapticFeedback.mediumImpact();
      final picker = ImagePicker();
      final photo = await picker.pickImage(
        source: ImageSource.camera,
        maxWidth: 1280,
        maxHeight: 1280,
        imageQuality: 85,
      );
      if (photo != null && mounted) {
        Navigator.of(context).pop();
        final bytes = await photo.readAsBytes();
        final b64 = base64Encode(bytes);
        if (widget.onExecuteJavaScript != null) {
          widget.onExecuteJavaScript!('''
            if (window.openSnapMealModal) {
              window.openSnapMealModal();
              setTimeout(function() {
                if (window.onFoodPhotoCaptured) {
                  window.onFoodPhotoCaptured('data:image/jpeg;base64,$b64');
                }
              }, 400);
            }
          ''');
        }
      }
    } catch (e) {
      debugPrint('Error in _snapMealCamera: $e');
    }
  }

  void _openFoodSearch() {
    HapticFeedback.selectionClick();
    Navigator.of(context).pop();
    if (widget.onExecuteJavaScript != null) {
      widget.onExecuteJavaScript!('if (window.openSearchFoodsModal) window.openSearchFoodsModal();');
    }
  }

  Future<void> _saveSettings() async {
    HapticFeedback.lightImpact();
    await _apiService.setBaseUrl(_urlController.text);
    await _apiService.setUsername(_userController.text.isEmpty ? null : _userController.text);
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('✅ Settings saved! Reloading dashboard...'),
          backgroundColor: Color(0xFF00E676),
          duration: Duration(seconds: 2),
        ),
      );
      widget.onRefreshWebView();
    }
  }

  @override
  Widget build(BuildContext context) {
    const primaryColor = Color(0xFFFF2E93);
    const cyanColor = Color(0xFF00F0FF);
    const cardBg = Color(0xFF1E1E38);

    return Container(
      decoration: const BoxDecoration(
        color: Color(0xFF121226),
        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
      ),
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        top: 16,
        bottom: MediaQuery.of(context).viewInsets.bottom + 24,
      ),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Handle bar
            Center(
              child: Container(
                width: 44,
                height: 5,
                decoration: BoxDecoration(
                  color: Colors.white24,
                  borderRadius: BorderRadius.circular(10),
                ),
              ),
            ),
            const SizedBox(height: 16),

            // Header
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: primaryColor.withValues(alpha: 0.2),
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(Icons.favorite, color: primaryColor, size: 24),
                ),
                const SizedBox(width: 12),
                const Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Device Health Connect',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      Text(
                        'Automatic health tracking for Flamingo XP & Badges',
                        style: TextStyle(color: Colors.white60, fontSize: 12),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  onPressed: () => Navigator.pop(context),
                  icon: const Icon(Icons.close, color: Colors.white70),
                ),
              ],
            ),
            const SizedBox(height: 16),

            // Health Connect Status Card
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: cardBg,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                  color: _isAuthorized ? const Color(0xFF00E676).withValues(alpha: 0.5) : Colors.amber.withValues(alpha: 0.5),
                  width: 1.5,
                ),
              ),
              child: Row(
                children: [
                  Icon(
                    _isAuthorized ? Icons.check_circle : Icons.warning_amber_rounded,
                    color: _isAuthorized ? const Color(0xFF00E676) : Colors.amber,
                    size: 28,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          _isAuthorized ? 'Health Connect Connected' : 'Health Connect Needs Access',
                          style: const TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.bold,
                            fontSize: 14,
                          ),
                        ),
                        Text(
                          _isAuthorized
                              ? 'Steps, Workouts, Sleep, Hydration & Weight active'
                              : 'Grant permissions to sync your real health data',
                          style: const TextStyle(color: Colors.white60, fontSize: 12),
                        ),
                      ],
                    ),
                  ),
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (!_isAuthorized)
                        ElevatedButton(
                          onPressed: _isChecking ? null : _requestPermissions,
                          style: ElevatedButton.styleFrom(
                            backgroundColor: primaryColor,
                            foregroundColor: Colors.white,
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(12),
                            ),
                            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                          ),
                          child: const Text('Connect', style: TextStyle(fontWeight: FontWeight.bold)),
                        ),
                      const SizedBox(width: 4),
                      IconButton(
                        tooltip: 'Open Health Connect Settings',
                        onPressed: () => _healthService.openHealthConnectSettings(),
                        icon: const Icon(Icons.settings, color: Colors.white70, size: 22),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),

            // Live Metrics Grid
            if (_latestMetrics != null) ...[
              const Text(
                "Today's Captured Health Data",
                style: TextStyle(color: Colors.white70, fontSize: 13, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 10),
              Wrap(
                spacing: 10,
                runSpacing: 10,
                children: [
                  _metricTile(
                    icon: Icons.directions_walk,
                    title: 'Steps',
                    value: '${_latestMetrics!.steps}',
                    color: cyanColor,
                  ),
                  _metricTile(
                    icon: Icons.local_fire_department,
                    title: 'Calories',
                    value: '${_latestMetrics!.activeCalories.toInt()} kcal',
                    color: Colors.orangeAccent,
                  ),
                  _metricTile(
                    icon: Icons.bedtime,
                    title: 'Sleep',
                    value: '${_latestMetrics!.sleepHours.toStringAsFixed(1)} hrs',
                    color: const Color(0xFFB388FF),
                  ),
                  _metricTile(
                    icon: Icons.water_drop,
                    title: 'Hydration',
                    value: '${(_latestMetrics!.waterMl / 29.5735).toStringAsFixed(0)} oz',
                    color: Colors.blueAccent,
                  ),
                  if (_latestMetrics!.workouts.isNotEmpty)
                    _metricTile(
                      icon: Icons.fitness_center,
                      title: 'Workouts',
                      value: '${_latestMetrics!.workouts.length} sessions',
                      color: primaryColor,
                    ),
                  if (_latestMetrics!.weightKg > 0)
                    _metricTile(
                      icon: Icons.monitor_weight_outlined,
                      title: 'Weight',
                      value: '${(_latestMetrics!.weightKg * 2.20462).toStringAsFixed(1)} lbs',
                      color: const Color(0xFF69F0AE),
                    ),
                ],
              ),
              const SizedBox(height: 16),
            ],

            // Sync Banner Message
            if (_syncMessage != null) ...[
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                decoration: BoxDecoration(
                  color: (_syncSuccess == true ? const Color(0xFF00E676) : Colors.redAccent).withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: _syncSuccess == true ? const Color(0xFF00E676) : Colors.redAccent,
                  ),
                ),
                child: Text(
                  _syncMessage!,
                  style: TextStyle(
                    color: _syncSuccess == true ? const Color(0xFF00E676) : Colors.redAccent,
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              const SizedBox(height: 16),
            ],

            // Sync Now Button
            ElevatedButton.icon(
              onPressed: _isSyncing ? null : _syncNow,
              icon: _isSyncing
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2.5),
                    )
                  : const Icon(Icons.sync, color: Colors.white),
              label: Text(
                _isSyncing ? 'Syncing with Flamingo Fitness...' : 'Sync Health Data Now',
                style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: Colors.white),
              ),
              style: ElevatedButton.styleFrom(
                backgroundColor: primaryColor,
                padding: const EdgeInsets.symmetric(vertical: 14),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                elevation: 4,
              ),
            ),
            const SizedBox(height: 20),

            // Quick Log Water (native Health Connect / HealthKit write)
            Container(
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(
                color: cardBg,
                borderRadius: BorderRadius.circular(18),
                border: Border.all(color: Colors.blueAccent.withValues(alpha: 0.4)),
                boxShadow: [
                  BoxShadow(
                    color: Colors.blueAccent.withValues(alpha: 0.08),
                    blurRadius: 12,
                    offset: const Offset(0, 4),
                  ),
                ],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Row(
                        children: [
                          Icon(Icons.water_drop, color: Colors.blueAccent, size: 22),
                          SizedBox(width: 8),
                          Text(
                            'Quick Log Water',
                            style: TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.bold,
                              fontSize: 16,
                            ),
                          ),
                        ],
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        decoration: BoxDecoration(
                          color: Colors.blueAccent.withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: Colors.blueAccent.withValues(alpha: 0.3)),
                        ),
                        child: const Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(Icons.bolt, color: Colors.blueAccent, size: 13),
                            SizedBox(width: 4),
                            Text(
                              'Health Connect',
                              style: TextStyle(color: Colors.blueAccent, fontSize: 11, fontWeight: FontWeight.bold),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 14),
                  // Preset Water Cards Grid
                  Row(
                    children: [
                      _waterPresetCard(8.0, 'Glass', '🥛', Colors.lightBlueAccent),
                      const SizedBox(width: 8),
                      _waterPresetCard(16.0, 'Bottle', '🥤', Colors.blueAccent),
                      const SizedBox(width: 8),
                      _waterPresetCard(24.0, 'Shaker', '🍶', const Color(0xFF00F0FF)),
                      const SizedBox(width: 8),
                      _waterPresetCard(32.0, 'Flask', '🧊', const Color(0xFF80D8FF)),
                    ],
                  ),
                  const SizedBox(height: 14),
                  // Quick Stepper & Custom Input Row
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: _waterController,
                          keyboardType: TextInputType.number,
                          style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                          decoration: InputDecoration(
                            labelText: 'Custom Amount',
                            suffixText: 'oz',
                            suffixStyle: const TextStyle(color: Colors.blueAccent, fontWeight: FontWeight.bold),
                            labelStyle: const TextStyle(color: Colors.white60),
                            filled: true,
                            fillColor: const Color(0xFF121226),
                            contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: BorderSide(color: Colors.white.withValues(alpha: 0.1)),
                            ),
                            enabledBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: BorderSide(color: Colors.white.withValues(alpha: 0.1)),
                            ),
                            focusedBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: const BorderSide(color: Colors.blueAccent),
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      _waterStepperBtn(-4, '-4'),
                      const SizedBox(width: 4),
                      _waterStepperBtn(4, '+4'),
                      const SizedBox(width: 8),
                      ElevatedButton.icon(
                        onPressed: _isSyncing
                            ? null
                            : () {
                                final v = double.tryParse(_waterController.text) ?? 0;
                                if (v > 0) _logWater(v);
                              },
                        icon: const Icon(Icons.add, size: 18),
                        label: const Text('Add', style: TextStyle(fontWeight: FontWeight.bold)),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.blueAccent,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),

            // Quick Meal & Snap Section
            Container(
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(
                color: cardBg,
                borderRadius: BorderRadius.circular(18),
                border: Border.all(color: Colors.purpleAccent.withValues(alpha: 0.4)),
                boxShadow: [
                  BoxShadow(
                    color: Colors.purpleAccent.withValues(alpha: 0.08),
                    blurRadius: 12,
                    offset: const Offset(0, 4),
                  ),
                ],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: Colors.purpleAccent.withValues(alpha: 0.2),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: const Icon(Icons.restaurant, color: Colors.purpleAccent, size: 20),
                      ),
                      const SizedBox(width: 10),
                      const Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Quick Nutrition & Snaps',
                              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.white),
                            ),
                            Text(
                              'Sparky Fitness database & recent foods',
                              style: TextStyle(fontSize: 11, color: Colors.white60),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 14),
                  Row(
                    children: [
                      Expanded(
                        child: ElevatedButton.icon(
                          onPressed: _snapMealCamera,
                          icon: const Icon(Icons.camera_alt, size: 18),
                          label: const Text('Snap Meal', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: const Color(0xFFA855F7),
                            foregroundColor: Colors.white,
                            padding: const EdgeInsets.symmetric(vertical: 12),
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: _openFoodSearch,
                          icon: const Icon(Icons.search, size: 18),
                          label: const Text('Search DB', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
                          style: OutlinedButton.styleFrom(
                            foregroundColor: Colors.white,
                            side: const BorderSide(color: Colors.purpleAccent),
                            padding: const EdgeInsets.symmetric(vertical: 12),
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),

            // Server Settings Section
            ExpansionTile(
              title: const Text(
                '⚙️ Server & Sync Configuration',
                style: TextStyle(color: Colors.white70, fontSize: 14, fontWeight: FontWeight.w600),
              ),
              collapsedIconColor: Colors.white60,
              iconColor: cyanColor,
              children: [
                const SizedBox(height: 8),
                // Server presets
                Wrap(
                  spacing: 8,
                  children: [
                    ActionChip(
                      label: const Text('Live Dev (devflamingo.randalls.cc)'),
                      backgroundColor: cardBg,
                      labelStyle: const TextStyle(color: cyanColor, fontSize: 11),
                      onPressed: () {
                        setState(() => _urlController.text = 'https://devflamingo.randalls.cc');
                      },
                    ),
                    ActionChip(
                      label: const Text('Local (192.168.1.118:7777)'),
                      backgroundColor: cardBg,
                      labelStyle: const TextStyle(color: cyanColor, fontSize: 11),
                      onPressed: () {
                        setState(() => _urlController.text = 'http://192.168.1.118:7777');
                      },
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                TextField(
                  controller: _urlController,
                  style: const TextStyle(color: Colors.white, fontSize: 14),
                  decoration: InputDecoration(
                    labelText: 'Flamingo Backend Server URL',
                    labelStyle: const TextStyle(color: Colors.white60),
                    filled: true,
                    fillColor: cardBg,
                    border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                ),
                const SizedBox(height: 10),
                TextField(
                  controller: _userController,
                  style: const TextStyle(color: Colors.white, fontSize: 14),
                  decoration: InputDecoration(
                    labelText: 'Optional Demo / Target Username',
                    labelStyle: const TextStyle(color: Colors.white60),
                    filled: true,
                    fillColor: cardBg,
                    border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                ),
                const SizedBox(height: 12),
                ElevatedButton(
                  onPressed: _saveSettings,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF2A2A50),
                    foregroundColor: cyanColor,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                  child: const Text('Save & Apply Settings'),
                ),
                const SizedBox(height: 10),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _waterPresetCard(double oz, String label, String emoji, Color accentColor) {
    return Expanded(
      child: Material(
        color: const Color(0xFF16162E),
        borderRadius: BorderRadius.circular(14),
        child: InkWell(
          onTap: _isSyncing ? null : () => _logWater(oz),
          borderRadius: BorderRadius.circular(14),
          child: Container(
            padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 4),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: accentColor.withValues(alpha: 0.25)),
            ),
            child: Column(
              children: [
                Text(emoji, style: const TextStyle(fontSize: 20)),
                const SizedBox(height: 4),
                Text(
                  '+${oz.toStringAsFixed(0)} oz',
                  style: TextStyle(
                    color: accentColor,
                    fontWeight: FontWeight.bold,
                    fontSize: 13,
                  ),
                ),
                Text(
                  label,
                  style: const TextStyle(
                    color: Colors.white54,
                    fontSize: 10,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _waterStepperBtn(double delta, String label) {
    return InkWell(
      onTap: () {
        HapticFeedback.selectionClick();
        final current = double.tryParse(_waterController.text) ?? 8;
        final next = (current + delta).clamp(1.0, 128.0);
        _waterController.text = next.toStringAsFixed(0);
      },
      borderRadius: BorderRadius.circular(10),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 12),
        decoration: BoxDecoration(
          color: const Color(0xFF2A2A50),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: Colors.white.withValues(alpha: 0.1)),
        ),
        child: Text(
          label,
          style: const TextStyle(
            color: Colors.white,
            fontWeight: FontWeight.bold,
            fontSize: 12,
          ),
        ),
      ),
    );
  }

  Widget _metricTile({
    required IconData icon,
    required String title,
    required String value,
    required Color color,
  }) {
    return Container(
      width: (MediaQuery.of(context).size.width - 60) / 2,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: const Color(0xFF1E1E38),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Row(
        children: [
          Icon(icon, color: color, size: 22),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: const TextStyle(color: Colors.white60, fontSize: 11)),
                Text(
                  value,
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                    fontSize: 14,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
