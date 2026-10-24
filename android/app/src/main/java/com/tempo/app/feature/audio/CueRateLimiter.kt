package com.tempo.app.feature.audio

sealed interface CueRateLimitResult {
    data class Allowed(val timestampMs: Long) : CueRateLimitResult
    data class Suppressed(
        val elapsedMs: Long,
        val remainingCooldownMs: Long
    ) : CueRateLimitResult
}

/**
 * Enforces a strict minimum gap (default 15 seconds) between coaching audio cues
 * to avoid cognitive overload during live sports practice.
 */
class CueRateLimiter(
    val minIntervalMs: Long = 15_000L
) {
    var lastCuePlayedTimestampMs: Long = 0L
        private set

    /**
     * Attempts to trigger a cue at [currentTimeMs].
     * Returns [CueRateLimitResult.Allowed] if at least [minIntervalMs] has elapsed since the last cue.
     * Returns [CueRateLimitResult.Suppressed] if called too soon.
     */
    fun attemptPlay(currentTimeMs: Long = System.currentTimeMillis()): CueRateLimitResult {
        if (lastCuePlayedTimestampMs > 0L) {
            val elapsed = currentTimeMs - lastCuePlayedTimestampMs
            if (elapsed < minIntervalMs) {
                val remaining = minIntervalMs - elapsed
                return CueRateLimitResult.Suppressed(
                    elapsedMs = elapsed,
                    remainingCooldownMs = remaining
                )
            }
        }

        lastCuePlayedTimestampMs = currentTimeMs
        return CueRateLimitResult.Allowed(timestampMs = currentTimeMs)
    }

    /** Returns true if a cue can be played immediately without being suppressed. */
    fun canPlay(currentTimeMs: Long = System.currentTimeMillis()): Boolean {
        if (lastCuePlayedTimestampMs == 0L) return true
        return (currentTimeMs - lastCuePlayedTimestampMs) >= minIntervalMs
    }

    /** Returns remaining cooldown time in milliseconds, or 0 if ready. */
    fun getCooldownRemainingMs(currentTimeMs: Long = System.currentTimeMillis()): Long {
        if (lastCuePlayedTimestampMs == 0L) return 0L
        val elapsed = currentTimeMs - lastCuePlayedTimestampMs
        return maxOf(0L, minIntervalMs - elapsed)
    }

    /** Resets the debounce window so the next cue plays immediately. */
    fun reset() {
        lastCuePlayedTimestampMs = 0L
    }
}
