import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../models/health_metrics.dart';
import '../services/api_service.dart';
import '../services/health_service.dart';

class HealthControlSheet extends StatefulWidget {
  final VoidCallback onRefreshWebView;

  const HealthControlSheet({
    super.key,
    required this.onRefreshWebView,
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
    setState(() => _isAuthorized = ok);
    if (ok) {
      final metrics = await _healthService.fetchTodayMetrics();
      setState(() => _latestMetrics = metrics);
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
