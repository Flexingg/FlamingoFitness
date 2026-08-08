⚡ SparkyFitness Integration Spec

AI Context: This document outlines how to translate the SparkyFitness data ingestion logic into Django Python. The backend uses an ELT (Extract, Load, Transform) pattern. We do not immediately parse the data into columns; instead, we dump the raw JSON responses into RawActivityLog, then use a post-save signal or secondary task to calculate XP.

1. API Client Service (services/sparky_client.py)

This service acts as a Python wrapper around the fit.randalls.cc/api endpoints, replacing the UrlFetchApp calls from the original script.

# Pseudo-code for AI guidance
import requests
from datetime import timedelta, date

class SparkyFitnessClient:
    BASE_URL = 'https://fit.randalls.cc/api'

    def __init__(self, api_key):
        self.headers = {
            'x-api-key': api_key,
            'Accept': 'application/json'
        }

    def fetch_sleep_data(self, start_date: str, end_date: str) -> list:
        # Replaces: /sleep/analytics?startDate=...
        url = f"{self.BASE_URL}/sleep/analytics"
        params = {'startDate': start_date, 'endDate': end_date}
        response = requests.get(url, headers=self.headers, params=params)
        return response.json() if response.status_code == 200 else []

    def fetch_food_entries(self, start_date: str, end_date: str) -> list:
        # Replaces: /food-entries/range/...
        url = f"{self.BASE_URL}/food-entries/range/{start_date}/{end_date}"
        response = requests.get(url, headers=self.headers)
        return response.json() if response.status_code == 200 else []

    def fetch_daily_goals(self, target_date: str) -> dict:
        # Replaces: /goals/by-date/...
        url = f"{self.BASE_URL}/goals/by-date/{target_date}"
        response = requests.get(url, headers=self.headers)
        return response.json() if response.status_code == 200 else {}
        
    def fetch_checkins(self, start_date: str, end_date: str) -> list:
        # Replaces: /measurements/check-in-measurements-range/...
        url = f"{self.BASE_URL}/measurements/check-in-measurements-range/{start_date}/{end_date}"
        response = requests.get(url, headers=self.headers)
        return response.json() if response.status_code == 200 else []


2. Celery Polling Task (tasks/sparky_tasks.py)

This task runs on a schedule (e.g., via Celery Beat every 4 hours), iterates over users who have connected their SparkyFitness account, and dumps the data into our JSONB landing zone.

# Pseudo-code for AI guidance
from celery import shared_task
from django.utils import timezone
from core.models import UserIntegration, RawActivityLog
from services.sparky_client import SparkyFitnessClient

@shared_task
def sync_all_sparky_fitness_data():
    integrations = UserIntegration.objects.filter(provider='sparkyfitness')
    
    # Normally fetch just the last 1-2 days to keep sync fast
    end_date = timezone.now().date()
    start_date = end_date - timezone.timedelta(days=1)
    
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')

    for integration in integrations:
        client = SparkyFitnessClient(api_key=integration.access_token)
        
        # 1. Fetch Sleep
        sleep_data = client.fetch_sleep_data(start_str, end_str)
        for entry in sleep_data:
            # Upsert into RawActivityLog using date as unique identifier for the day
            RawActivityLog.objects.update_or_create(
                user=integration.user,
                provider='sparkyfitness',
                activity_type='sleep',
                timestamp=entry.get('date'), # e.g., '2026-08-07'
                defaults={'raw_payload': entry, 'processed': False}
            )

        # 2. Fetch Food/Nutrition (Grouped or Raw)
        food_data = client.fetch_food_entries(start_str, end_str)
        # Note: We dump the whole array of the day's food into a single JSONB row for that day
        # so the gamification engine can calculate total macros vs goals later.
        
        # ... fetch goals, checkins, etc., following the same pattern ...


3. The Transformation / Gamification Layer (services/gamification.py)

Once the data is sitting in RawActivityLog, a secondary process pulls it out to award Flamingo Fitness XP.

# Pseudo-code for AI guidance
def process_sparky_nutrition_xp(raw_log_id):
    log = RawActivityLog.objects.get(id=raw_log_id)
    food_entries = log.raw_payload  # Array of food entries
    
    total_pro = sum(item.get('protein', 0) for item in food_entries)
    total_cals = sum(item.get('calories', 0) for item in food_entries)
    
    # Fetch the corresponding goals log for this user/date
    goals_log = RawActivityLog.objects.get(...) 
    pro_goal = goals_log.raw_payload.get('protein', 0)
    
    if total_pro >= pro_goal and total_cals <= goals_log.raw_payload.get('calories', 9999):
        # Award "Perfect Macro" XP to XPLedger and grant Base Materials
        award_xp(user=log.user, modality='nutrition', amount=50, reason='Perfect Macros')
        
    log.processed = True
    log.save()
