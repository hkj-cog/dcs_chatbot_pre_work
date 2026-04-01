#!/bin/bash

# Configuration
POST_URL="http://localhost:8000/conversation/chat"
USER_ID="your_user_id_here"
SESSION_ID="" # Initially empty

echo "────────────────────────────────────────────────────────────────"
echo -e "\033[1;32m  CHAT SESSION ACTIVE\033[0m"
echo -e "  \033[90mCommand:\033[0m  ./receive.sh {session_id}"
echo -e "  \033[90mNote:\033[0m     Run above command in a separate terminal window to monitor."
echo "────────────────────────────────────────────────────────────────"

while true; do
  # 1. Get User Input
  read -e -p "You: " USER_INPUT
  [[ -z "$USER_INPUT" ]] && continue

  TMP_RESPONSE=$(mktemp)

  # 2. Build Header Array
  # This makes the curl command cleaner than inline shell expansion
  HEADERS=(-H "Content-Type: application/json" -H "X-User-ID: $USER_ID")

  if [ -n "$SESSION_ID" ]; then
    HEADERS+=(-H "X-Session-ID: $SESSION_ID")
  fi

  # 3. Send the POST request
  curl -s -i -X POST "$POST_URL" \
    "${HEADERS[@]}" \
    -d "{\"user_input\": \"$USER_INPUT\"}" >"$TMP_RESPONSE"

  # 4. Extract and Update Session ID
  # This looks for the header and assigns it if found
  EXTRACTED_ID=$(grep -i "x-session-id:" "$TMP_RESPONSE" | awk '{print $2}' | tr -d '\r\n[:space:]')

  if [ -n "$EXTRACTED_ID" ]; then
    SESSION_ID="$EXTRACTED_ID"
  fi

  # 5. UI Feedback
  echo "-----------------------------------"
  echo "Session_ID: ${SESSION_ID:-None (Initial Request)}"

  echo -n "Server: "
  # sed deletes everything from the first line up to the first blank line (the headers)
  sed '1,/^\r\{0,1\}$/d' "$TMP_RESPONSE"
  echo -e "\n-----------------------------------"

  rm -f "$TMP_RESPONSE"
done
