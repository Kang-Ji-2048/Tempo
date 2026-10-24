package com.tempo.app

import com.tempo.app.network.MockTempoApi
import com.tempo.app.network.models.NetworkResult
import com.tempo.app.network.models.UserScheduleDto
import com.tempo.app.repository.SessionRepositoryImpl
import kotlinx.coroutines.runBlocking
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SessionRepositoryTest {

    @Test
    fun mockUploadPreservesTheAndroidSessionId() = runBlocking {
        val metadata = """{"session_id":"stable-android-id","user_id":"alice"}"""
            .toRequestBody("application/json".toMediaType())
        val response = MockTempoApi().ingestSession(metadata, null)
        assertEquals("stable-android-id", response.sessionId)
    }

    @Test
    fun httpErrorRetainsStatusForPollingPolicy() = runBlocking {
        val api = object : com.tempo.app.network.TempoApi by MockTempoApi() {
            override suspend fun getSession(sessionId: String): com.tempo.app.network.models.SessionRecordDto {
                throw retrofit2.HttpException(retrofit2.Response.error<Any>(403,
                    "Denied".toResponseBody("text/plain".toMediaType())))
            }
        }
        val result = SessionRepositoryImpl(api).getSession("private-session")
        assertTrue(result is NetworkResult.Error)
        assertEquals(403, (result as NetworkResult.Error).code)
    }

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

        val scheduleResult = repository.getSchedule("user_1")
        assertTrue(scheduleResult is NetworkResult.Success)

        val schedule = (scheduleResult as NetworkResult.Success).data
        assertEquals("user_1", schedule.userId)
        assertEquals("18:00", schedule.targetTimeUtc)

        val updated = schedule.copy(targetTimeUtc = "19:00")
        val updateResult = repository.updateSchedule(updated)
        assertTrue(updateResult is NetworkResult.Success)
        assertEquals("19:00", (updateResult as NetworkResult.Success).data.targetTimeUtc)
    }
}
