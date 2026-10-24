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

        val result = repository.getSession("test_session_123")
        assertTrue("Expected NetworkResult.Success", result is NetworkResult.Success)

        val data = (result as NetworkResult.Success).data
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
