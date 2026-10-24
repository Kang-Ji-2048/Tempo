package com.tempo.app.network

import com.tempo.app.network.models.SessionIngestResponseDto
import com.tempo.app.network.models.SessionRecordDto
import com.tempo.app.network.models.UserScheduleDto
import okhttp3.MultipartBody
import okhttp3.RequestBody
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Path

interface TempoApi {

    @Multipart
    @POST("api/v1/sessions/ingest")
    suspend fun ingestSession(
        @Part("metadata") metadata: RequestBody,
        @Part video: MultipartBody.Part?
    ): SessionIngestResponseDto

    @GET("api/v1/sessions/{sessionId}")
    suspend fun getSession(
        @Path("sessionId") sessionId: String
    ): SessionRecordDto

    @GET("api/v1/cadence/schedule/{userId}")
    suspend fun getSchedule(
        @Path("userId") userId: String
    ): UserScheduleDto

    @POST("api/v1/cadence/schedule")
    suspend fun updateSchedule(
        @Body schedule: UserScheduleDto
    ): UserScheduleDto

    @POST("api/v1/onboarding/next")
    suspend fun nextOnboardingStep(
        @Body request: com.tempo.app.network.models.OnboardingStepRequestDto
    ): com.tempo.app.network.models.OnboardingStepResponseDto

    @GET("health")
    suspend fun getHealth(): Map<String, String>
}
