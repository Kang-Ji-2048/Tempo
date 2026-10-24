package com.tempo.app.repository

import com.tempo.app.network.TempoApi
import com.tempo.app.network.models.NetworkResult
import com.tempo.app.network.models.SessionRecordDto
import com.tempo.app.network.models.UserScheduleDto
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class SessionRepositoryImpl @Inject constructor(
    private val api: TempoApi
) : SessionRepository {

    override suspend fun getSession(sessionId: String): NetworkResult<SessionRecordDto> {
        return try {
            val response = api.getSession(sessionId)
            NetworkResult.Success(response)
        } catch (e: Exception) {
            NetworkResult.Error(exception = e, message = e.message)
        }
    }

    override suspend fun getSchedule(userId: String): NetworkResult<UserScheduleDto> {
        return try {
            val response = api.getSchedule(userId)
            NetworkResult.Success(response)
        } catch (e: Exception) {
            NetworkResult.Error(exception = e, message = e.message)
        }
    }

    override suspend fun updateSchedule(schedule: UserScheduleDto): NetworkResult<UserScheduleDto> {
        return try {
            val response = api.updateSchedule(schedule)
            NetworkResult.Success(response)
        } catch (e: Exception) {
            NetworkResult.Error(exception = e, message = e.message)
        }
    }
}
