🦖 Liftosaur Integration Spec

AI Context: This document translates the Liftosaur Google Apps Script data ingestion logic into Django Python. Following our ELT pattern, we extract raw workout history from the Liftosaur API, load it into the RawActivityLog JSONB field, and then transform/parse the custom text blocks to calculate Strength XP based on volume.

1. API Client Service (services/liftosaur_client.py)

This service acts as a Python wrapper around the liftosaur.com/api/v1 endpoints. It requires Bearer token authentication.

# Pseudo-code for AI guidance
import requests
from urllib.parse import quote

class LiftosaurClient:
    BASE_URL = 'https://www.liftosaur.com/api/v1'

    def __init__(self, api_key):
        self.headers = {
            'Authorization': f'Bearer {api_key}',
            'Accept': 'application/json'
        }

    def fetch_history(self, start_date_iso: str) -> list:
        # Replaces: /history?limit=200&startDate=...
        # Handles pagination via 'cursor' and 'hasMore'
        records = []
        cursor = None
        has_more = True
        
        while has_more:
            url = f"{self.BASE_URL}/history?limit=200&startDate={quote(start_date_iso)}"
            if cursor:
                url += f"&cursor={quote(cursor)}"
                
            response = requests.get(url, headers=self.headers)
            if response.status_code in [200, 201]:
                data = response.json().get('data', {})
                records.extend(data.get('records', []))
                has_more = data.get('hasMore', False)
                cursor = data.get('nextCursor')
            else:
                has_more = False
                
        return records

    def fetch_current_program(self) -> dict:
        # Replaces: /programs/current
        url = f"{self.BASE_URL}/programs/current"
        response = requests.get(url, headers=self.headers)
        return response.json().get('data', {}) if response.status_code == 200 else {}


2. Celery Polling Task (tasks/liftosaur_tasks.py)

This task runs on a schedule, pulls the latest workout histories, and dumps them unparsed into our landing zone.

# Pseudo-code for AI guidance
from celery import shared_task
from django.utils import timezone
from core.models import UserIntegration, RawActivityLog
from services.liftosaur_client import LiftosaurClient

@shared_task
def sync_all_liftosaur_data():
    integrations = UserIntegration.objects.filter(provider='liftosaur')
    
    # Fetch last 3 days to catch any delayed syncs
    start_date = timezone.now() - timezone.timedelta(days=3)
    start_date_iso = start_date.isoformat()

    for integration in integrations:
        client = LiftosaurClient(api_key=integration.access_token)
        
        # 1. Fetch Workout History
        history_records = client.fetch_history(start_date_iso)
        
        for record in history_records:
            # Upsert into RawActivityLog using the Liftosaur record 'id' as the unique identifier
            # We dump the raw payload here, including the messy 'text' field.
            RawActivityLog.objects.update_or_create(
                user=integration.user,
                provider='liftosaur',
                activity_type='workout',
                timestamp=record.get('date'), # Extract proper date from payload
                defaults={'raw_payload': record, 'processed': False}
            )


3. Transformation / Gamification Layer (services/gamification.py)

Liftosaur returns workout data as a giant structured string in record['text']. The Gamification layer must parse this string using Regex (translating the JS parseHistoryRecordText and set-matching logic) to calculate Total Volume and award XP.

# Pseudo-code for AI guidance
import re

def process_liftosaur_strength_xp(raw_log_id):
    log = RawActivityLog.objects.get(id=raw_log_id)
    record_text = log.raw_payload.get('text', '')
    
    # 1. Extract Exercises Block
    exercises_match = re.search(r'exercises:\s*\{([\s\S]*?)\}', record_text)
    if not exercises_match:
        return # No exercises found
        
    exercises_text = exercises_match.group(1).strip()
    
    # 2. Parse Sets, Reps, and Weight to calculate Volume
    total_volume_lbs = 0
    
    # Split by line, then match the Liftosaur set pattern: 3 x 10 135lb
    lines = [line.strip() for line in exercises_text.split('\n') if line.strip()]
    for line in lines:
        parts = [p.strip() for p in line.split('/')]
        if len(parts) < 2:
            continue
            
        sets_string = parts[1]
        set_groups = [s.strip() for s in sets_string.split(',')]
        
        for group in set_groups:
            # Regex translates JS: /(\d+)\s*x\s*(\d+)\s*(\d+(?:\.\d+)?)/
            match = re.search(r'(\d+)\s*x\s*(\d+)\s*(\d+(?:\.\d+)?)', group)
            if match:
                sets = int(match.group(1))
                reps = int(match.group(2))
                weight = float(match.group(3))
                
                total_volume_lbs += (sets * reps * weight)
                
    # 3. Calculate XP based on rules in 03_gamification_math.md
    # 1 XP per 1,000 lbs volume + 20 XP completion bonus
    volume_xp = int(total_volume_lbs / 1000)
    total_xp = volume_xp + 20
    
    if total_xp > 0:
        award_xp(user=log.user, modality='strength', amount=total_xp, reason='Liftosaur Workout')
        
    log.processed = True
    log.save()
