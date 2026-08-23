import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'models/health_metrics.dart';
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
  bool _isHealthAuthorized = false;
  bool _isAutoSyncing = false;
  String? _avatarUrl;

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

  void _handleBridgeMessage(JavaScriptMessage message) async {
    final msg = message.message;
    debugPrint('Bridge message received: $msg');

    if (msg == 'syncHealth') {
      _performBackgroundSync();
    } else if (msg == 'requestPermissions') {
      _showHealthControlSheet();
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
      if (url.isNotEmpty && mounted) {
        setState(() => _avatarUrl = url);
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

  Future<void> _checkHealthPermissions() async {
    final ok = await _healthService.checkPermissions();
    if (mounted) {
      setState(() => _isHealthAuthorized = ok);
      if (ok) {
        // Automatically sync on launch if authorized
        _performBackgroundSync();
      }
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
