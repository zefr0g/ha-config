#!/bin/sh
# Query HA entity history and write a concise summary to input_text.historique_resultat.
# Usage: ha_history_service.sh <entity_id> [hours]
# Deploy to: /config/scripts/ha_history_service.sh

TOKEN=$(cat /config/.ha_token)
ENTITY_ID="$1"
HOURS="${2:-24}"
HA_URL="http://localhost:8123"

# Compute ISO start time (busybox-compatible)
START_EPOCH=$(( $(date +%s) - HOURS * 3600 ))
START=$(date -u -d "@${START_EPOCH}" +"%Y-%m-%dT%H:%M:%S+00:00")

# Fetch history
HISTORY=$(curl -sf \
  -H "Authorization: Bearer ${TOKEN}" \
  "${HA_URL}/api/history/period/${START}?filter_entity_id=${ENTITY_ID}&minimal_response=true&significant_changes_only=true")

# Fetch friendly name
FNAME=$(curl -sf \
  -H "Authorization: Bearer ${TOKEN}" \
  "${HA_URL}/api/states/${ENTITY_ID}" \
  | jq -r '.attributes.friendly_name // .entity_id')

# Build summary with jq
SUMMARY=$(printf '%s' "$HISTORY" | jq -r \
  --arg name "$FNAME" \
  --arg hours "$HOURS" \
  --arg entity "$ENTITY_ID" '
  def active_state: . == "on" or . == "open" or . == "true";

  if (. == null or length == 0 or (.[0] | length) == 0) then
    "\($name): aucun événement dans les dernières \($hours)h."
  else
    .[0] as $events |
    ($events | map(select(.state | active_state)) | length) as $count |
    ($events | last | .state) as $current |
    ($events | map(select(.state | active_state)) | last | .last_changed) as $last_on |
    (if $last_on != null then
      ($last_on | split("T") | "\(.[0][5:]) à \(.[1][:5])")
    else null end) as $last_str |
    (if $count > 0 and $last_str != null then
      "\($name): \($count) activation(s) en \($hours)h. Dernière: \($last_str). État: \($current)."
    elif $count > 0 then
      "\($name): \($count) activation(s) en \($hours)h. État: \($current)."
    else
      "\($name): aucune activation en \($hours)h. État: \($current)."
    end)
  end
')

# Truncate to 255 chars (HA state limit)
SUMMARY=$(printf '%s' "$SUMMARY" | cut -c1-255)

# Write result to HA
curl -sf -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"state\": $(printf '%s' "$SUMMARY" | jq -Rs .)}" \
  "${HA_URL}/api/states/input_text.historique_resultat" > /dev/null

printf '%s\n' "$SUMMARY"
