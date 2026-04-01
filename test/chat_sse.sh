#!/bin/bash

# --- Configuration ---
POST_URL="http://localhost:8000/conversation/chat"
SSE_BASE_URL="http://localhost:8000/ws/stream"
USER_ID="shell-user-$(hostname)"
SESSION_ID=""

# Use a temporary file as a "lock"
LOCK_FILE="/tmp/chat_lock_$(date +%s)"
touch "$LOCK_FILE"

cleanup() {
  # Kill the specific listener PID
  if [ -n "$LISTENER_PID" ]; then
    kill "$LISTENER_PID" 2>/dev/null
  fi
  # Safety net: Kill any background jobs started by this script
  kill $(jobs -p) 2>/dev/null
  rm -f "$LOCK_FILE"
  echo -e "\nDisconnected."
  exit
}

# Trap more signals for reliability
trap cleanup EXIT SIGINT SIGTERM

start_listener() {
  (
    exec curl -sN -H "Accept: text/event-stream" "$SSE_BASE_URL/$1" | while read -r line; do
      # 1. Skip empty lines (SSE keep-alives)
      [[ -z "$line" ]] && continue

      # 2. Check for the [DONE] signal
      # This handles both raw [DONE] and JSON {"msg": "[DONE]"}
      if [[ "$line" == *"[DONE]"* ]]; then
        # Release the lock so the "You: " prompt appears
        truncate -s 0 "$LOCK_FILE"
        continue
      fi

      # 3. Process actual content
      # We extract .msg, turn that string into JSON, and grab the content
      CLEAN_TEXT=$(echo "$line" | jq -r '.msg | fromjson | .data.content // empty' 2>/dev/null)

      if [[ -n "$CLEAN_TEXT" && "$CLEAN_TEXT" != "null" ]]; then
        printf "\r\033[KAssistant: %s\n" "$CLEAN_TEXT"
        # Optional: You can also truncate here if you want the prompt
        # to appear as soon as the first bit of text arrives.
      fi
    done
  ) &
  LISTENER_PID=$!
}

# --- THE INPUT LOOP ---
echo "Welcome! Type your message to begin."

while true; do
  # 1. Wait until Assistant is done
  while [ -s "$LOCK_FILE" ]; do
    sleep 0.1
  done

  # Use 'read -e' for line editing (backspace/arrow keys support)
  read -e -p "You: " USER_INPUT
  [ -z "$USER_INPUT" ] && continue

  # 2. Set the lock
  echo "busy" >"$LOCK_FILE"

  if [ -z "$SESSION_ID" ]; then
    # First request: Get headers to extract Session ID
    RESPONSE_HEADERS=$(curl -s -i -X POST "$POST_URL" \
      -H "Content-Type: application/json" \
      -H "X-User-ID: $USER_ID" \
      -d "{\"user_input\": \"$USER_INPUT\"}")

    SESSION_ID=$(echo "$RESPONSE_HEADERS" | grep -i "x-session-id:" | awk '{print $2}' | tr -d '\r')

    if [ -z "$SESSION_ID" ]; then
      echo "Error: Could not find x-session-id."
      truncate -s 0 "$LOCK_FILE"
      continue
    fi
    start_listener "$SESSION_ID"
  else
    # Subsequent requests: Session ID is already known
    curl -s -o /dev/null -X POST "$POST_URL" \
      -H "Content-Type: application/json" \
      -H "X-User-ID: $USER_ID" \
      -H "x-session-id: $SESSION_ID" \
      -d "{\"user_input\": \"$USER_INPUT\"}"
  fi
done
