import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../models/health_metrics.dart';

class SyncResult {
  final bool success;
  final String? message;
  final int syncedLogsCount;
  final int totalXpAwarded;
  final List<dynamic> newlyAwardedBadges;

  SyncResult({
    required this.success,
    this.message,
    this.syncedLogsCount = 0,
    this.totalXpAwarded = 0,
    this.newlyAwardedBadges = const [],
  });
}

class ApiService {
  static final ApiService _instance = ApiService._internal();
  factory ApiService() => _instance;
  ApiService._internal();

  static const String _prefServerUrlKey = 'flamingo_server_url';
  static const String _prefUsernameKey = 'flamingo_username';

  static const String defaultServerUrl = 'https://devflamingo.randalls.cc';

  String _baseUrl = defaultServerUrl;
  String get baseUrl => _baseUrl;

  String? _username;
  String? get username => _username;

  Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    _baseUrl = prefs.getString(_prefServerUrlKey) ?? defaultServerUrl;
    _username = prefs.getString(_prefUsernameKey);
  }

  Future<void> setBaseUrl(String url) async {
    var formatted = url.trim();
    if (!formatted.startsWith('http://') && !formatted.startsWith('https://')) {
      formatted = 'https://$formatted';
    }
    if (formatted.endsWith('/')) {
      formatted = formatted.substring(0, formatted.length - 1);
    }
    _baseUrl = formatted;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_prefServerUrlKey, _baseUrl);
  }

  Future<void> setUsername(String? user) async {
    _username = user?.trim().isEmpty == true ? null : user?.trim();
    final prefs = await SharedPreferences.getInstance();
    if (_username != null) {
      await prefs.setString(_prefUsernameKey, _username!);
    } else {
      await prefs.remove(_prefUsernameKey);
    }
  }

  Future<bool> checkHealth() async {
    try {
      final uri = Uri.parse('$_baseUrl/api/v1/badges/');
      final response = await http.get(uri).timeout(const Duration(seconds: 5));
      return response.statusCode == 200 || response.statusCode == 302 || response.statusCode == 403;
    } catch (e) {
      debugPrint('Connection check failed: $e');
      return false;
    }
  }

  Future<SyncResult> syncHealthData(HealthMetrics metrics) async {
    try {
      final uri = Uri.parse('$_baseUrl/api/v1/sync/health');
      final payload = {
        'provider': 'health_connect',
        'device': 'Android Health Connect',
        if (_username != null) 'username': _username,
        'metrics': metrics.toJson(),
      };

      final response = await http
          .post(
            uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(payload),
          )
          .timeout(const Duration(seconds: 10));

      if (response.statusCode == 200 || response.statusCode == 201) {
        final data = jsonDecode(response.body);
        return SyncResult(
          success: true,
          syncedLogsCount: data['synced_logs_count'] ?? 0,
          totalXpAwarded: data['total_xp_awarded'] ?? 0,
          newlyAwardedBadges: data['newly_awarded_badges'] ?? [],
        );
      } else {
        return SyncResult(
          success: false,
          message: 'Server returned ${response.statusCode}: ${response.body}',
        );
      }
    } catch (e) {
      debugPrint('Sync failed: $e');
      return SyncResult(
        success: false,
        message: 'Sync error: $e',
      );
    }
  }
}
