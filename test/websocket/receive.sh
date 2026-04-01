#!/bin/bash

# Configuration
WS_BASE_URL="ws://localhost:8000/ws/receive"

# 1. Validate Argument
if [ -z "$1" ]; then
  echo "Usage: ./local_listen.sh <session_id>"
  exit 1
fi

SESSION_ID=$(echo "$1" | tr -d '\r\n[:space:]')
FULL_WS_URL="${WS_BASE_URL}/${SESSION_ID}"

echo -e "\033[1;34m┏━━━━━━━━━━━━━━━ Local Listener Active ━━━━━━━━━━━━━━━┓\033[0m"
echo -e "\033[1;34m┃\033[0m \033[1;32mTarget:\033[0m $FULL_WS_URL"
echo -e "\033[1;34m┃\033[0m \033[1;33mAction:\033[0m Press \033[1;31mCtrl+C\033[0m to disconnect"
echo -e "\033[1;34m┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\033[0m"

# 2. Main Reconnection Loop
while true; do
  websocat -v "$FULL_WS_URL" | while read -r line; do

    [[ -z "$line" ]] && continue

    # 3. Extract Session ID and Content using jq
    # We parse the line and pull both fields at once
    PARSED=$(echo "$line" | jq -r 'select(.session_id != null) | "\(.session_id) @@@ \(.data.content)"' 2>/dev/null)

    # 4. UI Rendering Logic
    if [[ -n "$PARSED" ]]; then
      # Split the parsed string back into variables
      S_ID=$(echo "$PARSED" | awk -F " @@@ " '{print $1}')
      CONTENT=$(echo "$PARSED" | awk -F " @@@ " '{print $2}')

      printf "\r\033[K"
      echo -e "\033[34m┃\033[0m \033[1;90mSession:\033[0m \033[36m$S_ID\033[0m"
      echo -e "\033[34m┃\033[0m \033[1;32mMessage:\033[0m $CONTENT"
      printf "> "
    else
      # Fallback for non-JSON or unexpected formats
      if [[ ! "$line" =~ ^\{ ]]; then
        printf "\r\033[K[RAW]: %s\n> " "$line"
      fi
    fi

  done

  echo -e "\n[!] Connection lost. Retrying in 2 seconds..."
  sleep 2
done
