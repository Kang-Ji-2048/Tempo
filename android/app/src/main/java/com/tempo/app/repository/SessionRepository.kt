package com.tempo.app.repository

import com.tempo.app.network.models.NetworkResult
import com.tempo.app.network.models.SessionRecordDto
import com.tempo.app.network.models.UserScheduleDto

interface SessionRepository {
    suspend fun getSession(sessionId: String): NetworkResult<SessionRecordDto>
    suspend fun getSchedule(userId: String): NetworkResult<UserScheduleDto>
    suspend fun updateSchedule(schedule: UserScheduleDto): NetworkResult<UserScheduleDto>
}
