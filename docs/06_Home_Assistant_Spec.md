🏠 Home Assistant Integration Spec

AI Context: This defines the bridge between the Django Backend and Home Assistant (HA).

Inbound to Django (HA -> App)

Method: HA Automations send JSON payloads to Django Webhooks.

Use Cases: * Smart scale logs weight/body fat.

Sleep pad sensors detect sleep start/end times if Garmin isn't worn.

NFC tags in the gym tapped to register "Workout Started" to grant temporary XP multipliers.

Outbound to Home Assistant (App -> HA)

Method: Django uses the ha-api Python wrapper or standard REST to update HA entities.

Use Cases (The House "Plays"):

Streak Danger: If it's 8 PM and the user hasn't met their streak requirement, Django calls HA to change living room lights to --primary-red.

Boss Defeated: When a PR is logged, Django triggers an HA automation to play a victory sound on Sonos/Alexa.

Recovery Mode: If Garmin data dictates a "Rest Day", Django sets a helper boolean in HA (input_boolean.rest_day = true), which HA uses to adjust the morning thermostat and open blinds later.