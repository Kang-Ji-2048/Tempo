package com.tempo.app.feature.audio

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class CueRateLimiterTest {

    private lateinit var rateLimiter: CueRateLimiter

    @Before
    fun setUp() {
        rateLimiter = CueRateLimiter(minIntervalMs = 15_000L)
    }

    @Test
    fun `initial cue is allowed immediately`() {
        assertTrue(rateLimiter.canPlay(currentTimeMs = 100_000L))
        assertEquals(0L, rateLimiter.getCooldownRemainingMs(currentTimeMs = 100_000L))

        val result = rateLimiter.attemptPlay(currentTimeMs = 100_000L)
        assertTrue(result is CueRateLimitResult.Allowed)
        assertEquals(100_000L, (result as CueRateLimitResult.Allowed).timestampMs)
    }

    @Test
    fun `second cue within 15 seconds is suppressed with accurate remaining cooldown`() {
        // First cue at t = 1,000,000
        val firstResult = rateLimiter.attemptPlay(currentTimeMs = 1_000_000L)
        assertTrue(firstResult is CueRateLimitResult.Allowed)

        // Second cue attempted 4 seconds later (t = 1,004,000)
        assertFalse(rateLimiter.canPlay(currentTimeMs = 1_004_000L))
        assertEquals(11_000L, rateLimiter.getCooldownRemainingMs(currentTimeMs = 1_004_000L))

        val secondResult = rateLimiter.attemptPlay(currentTimeMs = 1_004_000L)
        assertTrue(secondResult is CueRateLimitResult.Suppressed)
        val suppressed = secondResult as CueRateLimitResult.Suppressed
        assertEquals(4_000L, suppressed.elapsedMs)
        assertEquals(11_000L, suppressed.remainingCooldownMs)
    }

    @Test
    fun `cue attempted just before 15s boundary is suppressed`() {
        rateLimiter.attemptPlay(currentTimeMs = 10_000L)

        // Attempt at 14,999ms later (t = 24,999L)
        val result = rateLimiter.attemptPlay(currentTimeMs = 24_999L)
        assertTrue(result is CueRateLimitResult.Suppressed)
        assertEquals(1L, (result as CueRateLimitResult.Suppressed).remainingCooldownMs)
    }

    @Test
    fun `cue attempted exactly at or after 15s interval is allowed`() {
        // Cue 1 at t = 50_000
        rateLimiter.attemptPlay(currentTimeMs = 50_000L)

        // Cue 2 at t = 65_000 (exactly 15s later)
        assertTrue(rateLimiter.canPlay(currentTimeMs = 65_000L))
        assertEquals(0L, rateLimiter.getCooldownRemainingMs(currentTimeMs = 65_000L))

        val result = rateLimiter.attemptPlay(currentTimeMs = 65_000L)
        assertTrue(result is CueRateLimitResult.Allowed)
        assertEquals(65_000L, (result as CueRateLimitResult.Allowed).timestampMs)
    }

    @Test
    fun `reset clears debounce window and allows immediate playback`() {
        rateLimiter.attemptPlay(currentTimeMs = 100_000L)
        assertFalse(rateLimiter.canPlay(currentTimeMs = 102_000L))

        rateLimiter.reset()

        assertTrue(rateLimiter.canPlay(currentTimeMs = 102_000L))
        val result = rateLimiter.attemptPlay(currentTimeMs = 102_000L)
        assertTrue(result is CueRateLimitResult.Allowed)
    }
}
