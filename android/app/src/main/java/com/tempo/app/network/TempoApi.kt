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

    @POST("api/v1/auth/register")
    suspend fun register(@Body request: com.tempo.app.network.models.RegisterRequestDto): com.tempo.app.network.models.AuthResponseDto

    @POST("api/v1/auth/login")
    suspend fun login(@Body request: com.tempo.app.network.models.LoginRequestDto): com.tempo.app.network.models.AuthResponseDto

    @GET("api/v1/auth/me")
    suspend fun getMe(): com.tempo.app.network.models.UserProfileDto

    @POST("api/v1/auth/logout")
    suspend fun logout(): Map<String, String>

    @GET("api/v1/sports")
    suspend fun getSports(): List<com.tempo.app.network.models.SportDto>

    @POST("api/v1/profile")
    suspend fun updateProfile(@Body profile: com.tempo.app.network.models.ProfilePayloadDto): Map<String, String>

    @GET("api/v1/profile")
    suspend fun getProfile(): com.tempo.app.network.models.UserProfileDto

    @GET("api/v1/ai/status")
    suspend fun getAiStatus(): com.tempo.app.network.models.AiStatusDto

    @GET("health")
    suspend fun getHealth(): Map<String, String>
}
