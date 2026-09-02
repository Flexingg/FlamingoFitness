/// Flamingo Fitness - Flutter Mobile Shell & Native Bridge (main.dart)
/// -------------------------------------------------------------------
/// Architecture Overview:
/// - Hybrid Flutter application hosting the Django-powered web SPA via `webview_flutter`.
/// - Native Bridge (`FlamingoNativeBridge`):
///   Exposes JavaScript channel `window.FlamingoNative` for two-way communication:
///   * `haptic:<type>` -> triggers device haptic engines (light, medium, heavy, selection).
///   * `notify:<json>` -> dispatches native system notifications via Android/iOS channels.
///   * `avatar:<url>` -> updates current user avatar cache.
///   * `syncHealth:` -> prompts immediate biometric data harvest and sync to server.
///   * `openSettings:` -> launches OS notification/health permission settings.
/// - Background Health Sync:
///   Aggregates HealthKit (iOS) and Health Connect (Android) metrics (steps, workouts,
///   calories, hydration, sleep) and posts payloads to the backend API (`/api/v1/health/sync`).
library;

import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_flutter_android/webview_flutter_android.dart';
import 'services/api_service.dart';
import 'services/health_service.dart';
import 'ui/health_control_sheet.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setSystemUIOverlayStyle(
    const SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: Brightness.light,
      systemNavigationBarColor: Color(0xFF0F0F1E),
      systemNavigationBarIconBrightness: Brightness.light,
    ),
  );

  final apiService = ApiService();
  await apiService.init();

  final healthService = HealthService();
  await healthService.configure();

  runApp(const FlamingoApp());
}

/// Root widget configuring dark theme, brand typography, and route entry.
class FlamingoApp extends StatelessWidget {
  const FlamingoApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Flamingo Fitness',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF0F0F1E),
        primaryColor: const Color(0xFFFF2E93),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFFFF2E93),
          secondary: Color(0xFF00F0FF),
          surface: Color(0xFF1E1E38),
        ),
        useMaterial3: true,
      ),
      home: const FlamingoHomeScreen(),
    );
  }
}

class FlamingoHomeScreen extends StatefulWidget {
  const FlamingoHomeScreen({super.key});

  @override
  State<FlamingoHomeScreen> createState() => _FlamingoHomeScreenState();
}

class _FlamingoHomeScreenState extends State<FlamingoHomeScreen> {
  final ApiService _apiService = ApiService();
  final HealthService _healthService = HealthService();

  static const MethodChannel _notificationChannel = MethodChannel('com.flamingo.fitness/notifications');

  late final WebViewController _webViewController;
  bool _isLoading = true;
  double _loadProgress = 0.0;
  bool _hasError = false;
  String? _errorMessage;
  bool _isAutoSyncing = false;

  @override
  void initState() {
    super.initState();
    _initWebView();
    _checkHealthPermissions();
    _initNotifications();
  }

  Future<void> _initNotifications() async {
    try {
      await _notificationChannel.invokeMethod('requestNotificationPermission');
    } catch (e) {
      debugPrint('Error requesting notification permission: $e');
    }
  }

  void _initWebView() {
    final serverUrl = _apiService.baseUrl;

    _webViewController = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(const Color(0xFF0F0F1E))
      ..setUserAgent('FlamingoFitnessAndroid/1.0')
      ..setNavigationDelegate(
        NavigationDelegate(
          onProgress: (int progress) {
            setState(() {
              _loadProgress = progress / 100.0;
            });
          },
          onPageStarted: (String url) {
            setState(() {
              _isLoading = true;
              _hasError = false;
              _errorMessage = null;
            });
          },
          onPageFinished: (String url) {
            setState(() {
              _isLoading = false;
            });
            _injectJavaScriptBridge();
          },
          onWebResourceError: (WebResourceError error) {
            // Only show error for main frame navigation failures
            if (error.isForMainFrame ?? true) {
              setState(() {
                _isLoading = false;
                _hasError = true;
                _errorMessage = error.description;
              });
            }
          },
        ),
      )
      ..addJavaScriptChannel(
        'FlamingoNativeBridge',
        onMessageReceived: _handleBridgeMessage,
      )
      ..loadRequest(Uri.parse(serverUrl));

    final platform = _webViewController.platform;
    if (platform is AndroidWebViewController) {
      platform.setOnShowFileSelector((FileSelectorParams params) async {
        try {
          final picker = ImagePicker();
          final isCapture = params.isCaptureEnabled;
          final XFile? photo = await picker.pickImage(
            source: isCapture ? ImageSource.camera : ImageSource.gallery,
            maxWidth: 1280,
            maxHeight: 1280,
            imageQuality: 85,
          );
          if (photo != null) {
            return [Uri.file(photo.path).toString()];
          }
        } catch (e) {
          debugPrint('Error in setOnShowFileSelector: $e');
        }
        return [];
      });
    }
  }

  Future<void> _injectJavaScriptBridge() async {
    const js = '''
      window.FlamingoNative = {
        syncHealth: function() {
          if (window.FlamingoNativeBridge) {
            window.FlamingoNativeBridge.postMessage('syncHealth');
          }
        },
        requestPermissions: function() {
          if (window.FlamingoNativeBridge) {
            window.FlamingoNativeBridge.postMessage('requestPermissions');
          }
        },
        openHealthConnectSettings: function() {
          if (window.FlamingoNativeBridge) {
            window.FlamingoNativeBridge.postMessage('openHealthConnectSettings');
          }
        },
        snapFoodPhoto: function(source) {
          if (window.FlamingoNativeBridge) {
            window.FlamingoNativeBridge.postMessage('snapFoodPhoto:' + (source || 'camera'));
          }
        },
        showNotification: function(title, body) {
          if (window.FlamingoNativeBridge) {
            window.FlamingoNativeBridge.postMessage('notify:' + JSON.stringify({title: title, body: body}));
          }
        },
        requestNotificationPermission: function() {
          if (window.FlamingoNativeBridge) {
            window.FlamingoNativeBridge.postMessage('requestNotificationPermission');
          }
        },
        openNotificationSettings: function() {
          if (window.FlamingoNativeBridge) {
            window.FlamingoNativeBridge.postMessage('openNotificationSettings');
          }
        },
        setAvatar: function(url) {
          if (window.FlamingoNativeBridge) {
            window.FlamingoNativeBridge.postMessage('avatar:' + url);
          }
        },
        logWater: function(oz) {
          if (window.FlamingoNativeBridge) {
            window.FlamingoNativeBridge.postMessage('logWater:' + oz);
          }
        },
        writeWater: function(oz) {
          if (window.FlamingoNativeBridge) {
            window.FlamingoNativeBridge.postMessage('logWater:' + oz);
          }
        },
        haptic: function(type) {
          if (window.FlamingoNativeBridge) {
            window.FlamingoNativeBridge.postMessage('haptic:' + (type || 'light'));
          }
        }
      };
      (function() {
        try {
          var av = document.getElementById('avatar-img') || document.querySelector('.avatar-edit-img');
          if (av && av.src && window.FlamingoNative && window.FlamingoNative.setAvatar) {
            window.FlamingoNative.setAvatar(av.src);
          }
        } catch(e) {}
      })();
      console.log('🦩 Flamingo Native Bridge initialized');
    ''';
    await _webViewController.runJavaScript(js);
  }

  Future<void> _pickFoodPhotoNative(ImageSource source) async {
    try {
      final picker = ImagePicker();
      final XFile? photo = await picker.pickImage(
        source: source,
        maxWidth: 1280,
        maxHeight: 1280,
        imageQuality: 85,
      );
      if (photo != null) {
        final bytes = await photo.readAsBytes();
        final b64 = base64Encode(bytes);
        final js = "if (window.onFoodPhotoCaptured) window.onFoodPhotoCaptured('data:image/jpeg;base64,$b64');";
        await _webViewController.runJavaScript(js);
      }
    } catch (e) {
      debugPrint('Error in _pickFoodPhotoNative: $e');
    }
  }

  void _handleBridgeMessage(JavaScriptMessage message) async {
    final msg = message.message;
    debugPrint('Bridge message received: $msg');

    if (msg == 'syncHealth') {
      _performBackgroundSync();
    } else if (msg == 'requestPermissions') {
      _showHealthControlSheet();
    } else if (msg == 'openHealthConnectSettings') {
      try {
        await _healthService.openHealthConnectSettings();
      } catch (e) {
        debugPrint('Error invoking openHealthConnectSettings: $e');
      }
    } else if (msg.startsWith('snapFoodPhoto:')) {
      final sourceStr = msg.split(':')[1];
      _pickFoodPhotoNative(sourceStr == 'gallery' ? ImageSource.gallery : ImageSource.camera);
    } else if (msg.startsWith('logWater:') || msg.startsWith('writeWater:')) {
      final parts = msg.split(':');
      final oz = double.tryParse(parts.length > 1 ? parts[1] : '') ?? 0.0;
      if (oz > 0) {
        _logWaterNative(oz);
      }
    } else if (msg == 'requestNotificationPermission') {
      try {
        await _notificationChannel.invokeMethod('requestNotificationPermission');
      } catch (e) {
        debugPrint('Error invoking requestNotificationPermission: $e');
      }
    } else if (msg == 'openNotificationSettings') {
      try {
        await _notificationChannel.invokeMethod('openNotificationSettings');
      } catch (e) {
        debugPrint('Error invoking openNotificationSettings: $e');
      }
    } else if (msg.startsWith('avatar:')) {
      final url = msg.substring(7);
      if (url.isNotEmpty) {
        debugPrint('Avatar updated via bridge: $url');
      }
    } else if (msg.startsWith('notify:')) {
      try {
        final jsonStr = msg.substring(7);
        final map = jsonDecode(jsonStr) as Map<String, dynamic>;
        await _notificationChannel.invokeMethod('showNotification', {
          'title': map['title'] ?? '🦩 Flamingo Fitness',
          'body': map['body'] ?? 'Time to log your habits and level up!',
        });
      } catch (e) {
        debugPrint('Error invoking showNotification: $e');
      }
    } else if (msg.startsWith('haptic:')) {
      final type = msg.split(':')[1];
      if (type == 'heavy') {
        HapticFeedback.heavyImpact();
      } else if (type == 'medium') {
        HapticFeedback.mediumImpact();
      } else if (type == 'selection') {
        HapticFeedback.selectionClick();
      } else {
        HapticFeedback.lightImpact();
      }
    }
  }

  Future<void> _logWaterNative(double oz) async {
    try {
      HapticFeedback.mediumImpact();
      final wrote = await _healthService.writeWater(oz);
      debugPrint('Natively logged $oz oz to Health Connect: $wrote');
      if (wrote) {
        final metrics = await _healthService.fetchTodayMetrics();
        await _apiService.syncHealthData(metrics);
      }
    } catch (e) {
      debugPrint('Error writing water natively from bridge: $e');
    }
  }

  Future<void> _checkHealthPermissions() async {
    final ok = await _healthService.checkPermissions();
    if (mounted && ok) {
      // Automatically sync on launch if authorized
      _performBackgroundSync();
    }
  }

  Future<void> _performBackgroundSync() async {
    if (_isAutoSyncing) return;
    setState(() => _isAutoSyncing = true);

    try {
      final metrics = await _healthService.fetchTodayMetrics();
      final result = await _apiService.syncHealthData(metrics);
      if (result.success && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('🦩 Health Synced: +${result.totalXpAwarded} XP awarded!'),
            backgroundColor: const Color(0xFFFF2E93),
            duration: const Duration(seconds: 2),
          ),
        );
      }
    } catch (e) {
      debugPrint('Background sync error: $e');
    } finally {
      if (mounted) {
        setState(() => _isAutoSyncing = false);
      }
    }
  }

  void _showHealthControlSheet() {
    HapticFeedback.mediumImpact();
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => HealthControlSheet(
        onRefreshWebView: () {
          _checkHealthPermissions();
          _webViewController.loadRequest(Uri.parse(_apiService.baseUrl));
        },
        onExecuteJavaScript: (js) {
          _webViewController.runJavaScript(js);
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    const primaryColor = Color(0xFFFF2E93);
    const cyanColor = Color(0xFF00F0FF);

    return Scaffold(
      backgroundColor: const Color(0xFF0F0F1E),
      body: SafeArea(
        top: true,
        bottom: true,
        child: Stack(
          children: [
            if (!_hasError)
              RefreshIndicator(
                color: primaryColor,
                backgroundColor: const Color(0xFF1E1E38),
                onRefresh: () async {
                  HapticFeedback.lightImpact();
                  await _performBackgroundSync();
                  await _webViewController.reload();
                },
                child: WebViewWidget(controller: _webViewController),
              ),

            // Loading Progress Bar
            if (_isLoading)
              LinearProgressIndicator(
                value: _loadProgress > 0 ? _loadProgress : null,
                color: primaryColor,
                minHeight: 3,
              ),

            // Error View with Retry Button
            if (_hasError)
              Center(
                child: Padding(
                  padding: const EdgeInsets.all(28.0),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Text('🦩', style: TextStyle(fontSize: 48)),
                      const SizedBox(height: 16),
                      const Text(
                        'Unable to reach Flamingo Server',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                          color: Colors.white,
                        ),
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 8),
                      Text(
                        _errorMessage ?? 'Please check your internet connection or server URL.',
                        style: const TextStyle(color: Colors.white60, fontSize: 13),
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 20),
                      Text(
                        'Current URL: ${_apiService.baseUrl}',
                        style: const TextStyle(color: cyanColor, fontSize: 12),
                      ),
                      const SizedBox(height: 24),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          ElevatedButton.icon(
                            onPressed: () {
                              _webViewController.loadRequest(Uri.parse(_apiService.baseUrl));
                            },
                            icon: const Icon(Icons.refresh),
                            label: const Text('Retry Connection'),
                            style: ElevatedButton.styleFrom(
                              backgroundColor: primaryColor,
                              foregroundColor: Colors.white,
                              padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
                            ),
                          ),
                          const SizedBox(width: 12),
                          OutlinedButton.icon(
                            onPressed: _showHealthControlSheet,
                            icon: const Icon(Icons.settings),
                            label: const Text('Change URL'),
                            style: OutlinedButton.styleFrom(
                              foregroundColor: cyanColor,
                              side: const BorderSide(color: cyanColor),
                              padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
