import 'dart:convert';

class WorkoutEntry {
  final String type;
  final String title;
  final int durationMinutes;
  final double calories;
  final double? avgHeartRate;
  final double? totalVolumeLbs;

  WorkoutEntry({
    required this.type,
    required this.title,
    required this.durationMinutes,
    required this.calories,
    this.avgHeartRate,
    this.totalVolumeLbs,
  });

  Map<String, dynamic> toJson() => {
        'type': type,
        'title': title,
        'duration_minutes': durationMinutes,
        'calories': calories,
        if (avgHeartRate != null) 'avg_heart_rate': avgHeartRate,
        if (totalVolumeLbs != null) 'total_volume_lbs': totalVolumeLbs,
      };
}

class HealthMetrics {
  final int steps;
  final double activeCalories;
  final double distanceMeters;
  final double sleepHours;
  final double deepSleepHours;
  final double waterMl;
  final double weightKg;
  final List<WorkoutEntry> workouts;
  final DateTime capturedAt;

  HealthMetrics({
    this.steps = 0,
    this.activeCalories = 0.0,
    this.distanceMeters = 0.0,
    this.sleepHours = 0.0,
    this.deepSleepHours = 0.0,
    this.waterMl = 0.0,
    this.weightKg = 0.0,
    this.workouts = const [],
    DateTime? capturedAt,
  }) : capturedAt = capturedAt ?? DateTime.now();

  Map<String, dynamic> toJson() => {
        'steps': steps,
        'active_calories': activeCalories,
        'distance_meters': distanceMeters,
        'sleep_hours': sleepHours,
        'deep_sleep_hours': deepSleepHours,
        'water_ml': waterMl,
        'weight_kg': weightKg,
        'workouts': workouts.map((w) => w.toJson()).toList(),
        'captured_at': capturedAt.toIso8601String(),
      };

  String toJsonString() => jsonEncode(toJson());
}
