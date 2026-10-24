package com.tempo.app.network.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject

@Serializable
data class SessionIngestResponseDto(
    @SerialName("session_id") val sessionId: String,
    val status: String,
    @SerialName("estimated_analysis_time_sec") val estimatedAnalysisTimeSec: Int = 8,
    val message: String
)

@Serializable
data class SessionRecordDto(
    @SerialName("session_id") val sessionId: String,
    @SerialName("user_id") val userId: String,
    val sport: String,
    @SerialName("stroke_type") val strokeType: String,
    @SerialName("target_archetype") val targetArchetype: String? = null,
    val status: String,
    @SerialName("video_storage_path") val videoStoragePath: String? = null,
    @SerialName("video_url") val videoUrl: String? = null,
    @SerialName("telemetry_count") val telemetryCount: Int = 0,
    @SerialName("gemini_feedback") val geminiFeedback: JsonObject? = null,
    @SerialName("active_widgets") val activeWidgets: List<JsonObject>? = null,
    @SerialName("kinematic_vector") val kinematicVector: List<Float>? = null,
    @SerialName("error_message") val errorMessage: String? = null,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("updated_at") val updatedAt: String? = null
)

@Serializable
data class UserScheduleDto(
    @SerialName("user_id") val userId: String,
    val sport: String = "badminton",
    @SerialName("stroke_type") val strokeType: String = "overhead_clear",
    @SerialName("days_of_week") val daysOfWeek: List<String> = listOf("Monday", "Wednesday", "Friday"),
    @SerialName("target_time_utc") val targetTimeUtc: String = "18:00",
    @SerialName("priming_lead_minutes") val primingLeadMinutes: Int = 30,
    @SerialName("preferred_channel") val preferredChannel: String = "whatsapp",
    @SerialName("is_active") val isActive: Boolean = true
)

// Sealed Result pattern enforced by architecture rules
sealed interface NetworkResult<out T> {
    data class Success<out T>(val data: T) : NetworkResult<T>
    data class Error(val exception: Throwable, val code: Int? = null, val message: String? = null) : NetworkResult<Nothing>
    data object Loading : NetworkResult<Nothing>
}
