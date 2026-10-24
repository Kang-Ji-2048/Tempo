package com.tempo.app

import com.tempo.app.network.MockTempoApi
import com.tempo.app.network.models.NetworkResult
import com.tempo.app.network.models.UserScheduleDto
import com.tempo.app.repository.SessionRepositoryImpl
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SessionRepositoryTest {

    @Test
    fun testMockApiSessionRetrieval() = runBlocking {
        val mockApi = MockTempoApi()
        val repository = SessionRepositoryImpl(mockApi)

        // Poll 1 -> PENDING
        val poll1 = repository.getSession("test_session_123")
        assertTrue("Expected Success", poll1 is NetworkResult.Success)
        assertEquals("PENDING", (poll1 as NetworkResult.Success).data.status)

        // Poll 2 -> ANALYZING
        val poll2 = repository.getSession("test_session_123")
        assertTrue("Expected Success", poll2 is NetworkResult.Success)
        assertEquals("ANALYZING", (poll2 as NetworkResult.Success).data.status)

        // Poll 3 -> COMPLETED
        val poll3 = repository.getSession("test_session_123")
        assertTrue("Expected Success", poll3 is NetworkResult.Success)
        val data = (poll3 as NetworkResult.Success).data
        assertEquals("test_session_123", data.sessionId)
        assertEquals("COMPLETED", data.status)
        assertEquals("Viktor Axelsen", data.targetArchetype)
        assertEquals(3, data.telemetryCount)
    }

    @Test
    fun testMockApiScheduleRetrievalAndUpdate() = runBlocking {
        val mockApi = MockTempoApi()
        val repository = SessionRepositoryImpl(mockApi)

        val scheduleResult = repository.getSchedule("usr_sumanth_001")
        assertTrue(scheduleResult is NetworkResult.Success)

        val schedule = (scheduleResult as NetworkResult.Success).data
        assertEquals("usr_sumanth_001", schedule.userId)
        assertEquals("18:00", schedule.targetTimeUtc)

        val updated = schedule.copy(targetTimeUtc = "19:00")
        val updateResult = repository.updateSchedule(updated)
        assertTrue(updateResult is NetworkResult.Success)
        assertEquals("19:00", (updateResult as NetworkResult.Success).data.targetTimeUtc)
    }
}
