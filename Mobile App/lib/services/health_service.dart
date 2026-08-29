/// Health Data Ingestion Service (health_service.dart)
/// --------------------------------------------------
/// Architecture & Hardware Integration:
/// - Singleton wrapping the Flutter `health` package for cross-platform biometric reads.
/// - Android: Interfaces with Google Health Connect (`androidx.health.connect.client`).
/// - iOS: Interfaces with Apple HealthKit (`HKHealthStore`).
/// - Collects daily steps, active/total calorie burn, distance, sleep stages,
///   water intake, bodyweight, workouts, and heart rate.
/// - Produces serialized `HealthMetricsPayload` models ready for backend sync.
library;

import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:health/health.dart';
import '../models/health_metrics.dart';

class HealthService {
  static final HealthService _instance = HealthService._internal();
  factory HealthService() => _instance;
  HealthService._internal();

  final Health _health = Health();

  static const List<HealthDataType> _healthDataTypesAndroid = [
    HealthDataType.STEPS,
    HealthDataType.ACTIVE_ENERGY_BURNED,
    HealthDataType.TOTAL_CALORIES_BURNED,
    HealthDataType.DISTANCE_DELTA,
    HealthDataType.SLEEP_SESSION,
    HealthDataType.WATER,
    HealthDataType.WEIGHT,
    HealthDataType.WORKOUT,
    HealthDataType.HEART_RATE,
  ];

  static const List<HealthDataType> _healthDataTypesIOS = [
    HealthDataType.STEPS,
    HealthDataType.ACTIVE_ENERGY_BURNED,
    HealthDataType.DISTANCE_WALKING_RUNNING,
    HealthDataType.SLEEP_ASLEEP,
    HealthDataType.WATER,
    HealthDataType.WEIGHT,
    HealthDataType.WORKOUT,
    HealthDataType.HEART_RATE,
  ];

  List<HealthDataType> get supportedTypes =>
      Platform.isAndroid ? _healthDataTypesAndroid : _healthDataTypesIOS;

  bool _isAuthorized = false;
  bool get isAuthorized => _isAuthorized;

  Future<void> configure() async {
    try {
      await _health.configure();
    } catch (e) {
      debugPrint('Health configure error: $e');
    }
  }

  Future<bool> checkPermissions() async {
    try {
      await configure();
      final hasPerm = await _health.hasPermissions(supportedTypes);
      _isAuthorized = hasPerm ?? false;
      return _isAuthorized;
    } catch (e) {
      debugPrint('Error checking health permissions: $e');
      return false;
    }
  }

  Future<bool> requestPermissions() async {
    try {
      await configure();
      // Request READ for most types, but READ_WRITE for water so we can
      // log water natively into Health Connect / HealthKit.
      final permissions = supportedTypes
          .map((type) => type == HealthDataType.WATER
              ? HealthDataAccess.READ_WRITE
              : HealthDataAccess.READ)
          .toList();

      final authorized = await _health.requestAuthorization(
        supportedTypes,
        permissions: permissions,
      );

      _isAuthorized = authorized;
      return _isAuthorized;
    } catch (e) {
      debugPrint('Error requesting health permissions: $e');
      return false;
    }
  }

  /// Write a water intake sample to Health Connect / HealthKit natively.
  /// [oz] is in US fluid ounces; the health package stores water in liters.
  /// Returns true on success.
  Future<bool> writeWater(double oz, {DateTime? time}) async {
    try {
      final now = time ?? DateTime.now();
      final liters = oz / 33.814; // 1 US fl oz = 0.0295735 L
      return await _health.writeHealthData(
        value: liters,
        type: HealthDataType.WATER,
        startTime: now,
        endTime: now,
        recordingMethod: RecordingMethod.manual,
      );
    } catch (e) {
      debugPrint('Error writing water: $e');
      return false;
    }
  }

  Future<HealthMetrics> fetchTodayMetrics() async {
    final now = DateTime.now();
    final startOfDay = DateTime(now.year, now.month, now.day, 0, 0, 0);
    // For sleep, check from 6 PM yesterday to capture full overnight sleep
    final sleepStartTime = startOfDay.subtract(const Duration(hours: 6));

    int steps = 0;
    double activeCalories = 0.0;
    double distanceMeters = 0.0;
    double sleepHours = 0.0;
    double deepSleepHours = 0.0;
    double waterMl = 0.0;
    double weightKg = 0.0;
    List<WorkoutEntry> workouts = [];

    try {
      // 1. Steps count
      final stepsCount = await _health.getTotalStepsInInterval(startOfDay, now);
      steps = stepsCount ?? 0;
    } catch (e) {
      debugPrint('Error fetching steps: $e');
    }

    try {
      // 2. Fetch health data points for today
      final dataPoints = await _health.getHealthDataFromTypes(
        types: supportedTypes,
        startTime: sleepStartTime,
        endTime: now,
      );

      for (var point in dataPoints) {
        final val = point.value;
        final dateFrom = point.dateFrom;

        switch (point.type) {
          case HealthDataType.ACTIVE_ENERGY_BURNED:
            if (dateFrom.isAfter(startOfDay)) {
              if (val is NumericHealthValue) {
                activeCalories += val.numericValue.toDouble();
              }
            }
            break;

          case HealthDataType.DISTANCE_DELTA:
          case HealthDataType.DISTANCE_WALKING_RUNNING:
            if (dateFrom.isAfter(startOfDay)) {
              if (val is NumericHealthValue) {
                distanceMeters += val.numericValue.toDouble();
              }
            }
            break;

          case HealthDataType.SLEEP_SESSION:
          case HealthDataType.SLEEP_ASLEEP:
            // Calculate sleep duration in hours
            final durationMins = point.dateTo.difference(point.dateFrom).inMinutes;
            if (durationMins > 15) {
              sleepHours += durationMins / 60.0;
            }
            break;

          case HealthDataType.SLEEP_DEEP:
            final deepMins = point.dateTo.difference(point.dateFrom).inMinutes;
            deepSleepHours += deepMins / 60.0;
            break;

          case HealthDataType.WATER:
            if (dateFrom.isAfter(startOfDay)) {
              if (val is NumericHealthValue) {
                // Usually in Liters or Milliliters
                final numVal = val.numericValue.toDouble();
                waterMl += numVal < 10 ? numVal * 1000 : numVal;
              }
            }
            break;

          case HealthDataType.WEIGHT:
            if (val is NumericHealthValue) {
              weightKg = val.numericValue.toDouble();
            }
            break;

          case HealthDataType.WORKOUT:
            if (dateFrom.isAfter(startOfDay)) {
              if (val is WorkoutHealthValue) {
                final duration = point.dateTo.difference(point.dateFrom).inMinutes;
                workouts.add(
                  WorkoutEntry(
                    type: val.workoutActivityType.name,
                    title: val.workoutActivityType.name.replaceAll('_', ' ').toUpperCase(),
                    durationMinutes: duration > 0 ? duration : 30,
                    calories: val.totalEnergyBurned?.toDouble() ?? 0.0,
                    avgHeartRate: null,
                  ),
                );
              }
            }
            break;

          default:
            break;
        }
      }
    } catch (e) {
      debugPrint('Error fetching health points: $e');
    }

    return HealthMetrics(
      steps: steps,
      activeCalories: activeCalories,
      distanceMeters: distanceMeters,
      sleepHours: sleepHours,
      deepSleepHours: deepSleepHours,
      waterMl: waterMl,
      weightKg: weightKg,
      workouts: workouts,
      capturedAt: now,
    );
  }
}
