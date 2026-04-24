"""
Session-level threat tracking via a Redis sliding window.
Detects multi-turn jailbreak patterns where individual messages pass but cumulative
behaviour is suspicious. Fail-open on Redis errors — per-message guardrails still enforce safety.
"""

import json
import time

from libs.logger import log_escalation_event, logger


class SessionThreatTracker:
    """Counts guardrail blocks per session in a Redis sliding window; escalates at threshold."""

    def __init__(
        self,
        threshold: int = 5,
        window_seconds: int = 3600,
        pii_threshold: int = 10,
    ) -> None:
        self._threshold = threshold
        self._window = window_seconds
        self._pii_threshold = pii_threshold  # higher threshold — citizens often share PII legitimately

    async def record_trigger(
        self,
        session_id: str,
        guardrail_name: str,
        reason: str = "",
    ) -> bool:
        """Increments the session block counter and returns True when the threshold is first hit."""
        if not session_id:
            return False

        from libs.redis_manager import redis_manager

        key = f"threat:{session_id}"
        now = time.time()
        redis = redis_manager.get_client()
        try:
            # Sorted-set sliding window: trim stale events then count the current window.
            async with redis.pipeline() as pipe:
                pipe.zremrangebyscore(key, 0, now - self._window)
                pipe.zadd(key, {str(now): now})
                pipe.zcard(key)
                pipe.expire(key, self._window)
                results = await pipe.execute()
            count = results[2]

            # Escalate exactly once (count == threshold, not >=) to avoid SIEM alert fatigue.
            if count == self._threshold:
                log_escalation_event(
                    session_id=session_id,
                    trigger_count=count,
                    last_guardrail=guardrail_name,
                    reason=(
                        reason or
                        f"Session triggered {count} guardrail blocks within "
                        f"{self._window}s window. Human review recommended."
                    ),
                )
                return True

        except Exception as exc:
            logger.warning(
                f"[SessionThreatTracker] Redis error (fail-open) for "
                f"session={session_id!r}: {exc}"
            )

        return False

    async def record_pii_event(
        self,
        session_id: str,
        pii_types: list,
    ) -> bool:
        """Tracks PII detections in a separate counter. Returns True when the PII threshold is first hit."""
        if not session_id:
            return False

        from libs.redis_manager import redis_manager

        key = f"pii_threat:{session_id}"
        now = time.time()
        redis = redis_manager.get_client()
        try:
            async with redis.pipeline() as pipe:
                pipe.zremrangebyscore(key, 0, now - self._window)
                pipe.zadd(key, {str(now): now})
                pipe.zcard(key)
                pipe.expire(key, self._window)
                results = await pipe.execute()
            count = results[2]

            if count == self._pii_threshold:
                logger.warning(json.dumps({
                    "pii_escalation_event": {
                        "session_id": session_id,
                        "pii_event_count": count,
                        "pii_types": pii_types,
                        "reason": (
                            f"Session submitted PII {count} times within "
                            f"{self._window}s window. May indicate data harvesting "
                            "or a misconfigured upstream system. Advisory review recommended."
                        ),
                    }
                }))
                return True

        except Exception as exc:
            logger.warning(
                f"[SessionThreatTracker] PII counter Redis error (fail-open) for "
                f"session={session_id!r}: {exc}"
            )

        return False
