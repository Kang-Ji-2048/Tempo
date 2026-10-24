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
    @SerialName("overall_score") val overallScore: Int? = null,
    @SerialName("primary_flaw") val primaryFlaw: String? = null,
    @SerialName("llm_source") val llmSource: String? = null,
    @SerialName("llm_model") val llmModel: String? = null,
    @SerialName("llm_error") val llmError: String? = null,
    @SerialName("video_used") val videoUsed: Boolean? = null,
    @SerialName("latency_ms") val latencyMs: Int? = null,
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
    @SerialName("is_active") val isActive: Boolean = true,
    @SerialName("recent_brief") val recentBrief: String? = null
)

@Serializable
data class RegisterRequestDto(
    val email: String,
    val password: String,
    @SerialName("display_name") val displayName: String
)

@Serializable
data class LoginRequestDto(
    val email: String,
    val password: String
)

@Serializable
data class AuthResponseDto(
    @SerialName("user_id") val userId: String,
    @SerialName("access_token") val accessToken: String,
    @SerialName("display_name") val displayName: String,
    val email: String? = null
) {
    val user_id: String get() = userId
    val access_token: String get() = accessToken
    val display_name: String get() = displayName
}

@Serializable
data class SportSkillDto(
    val id: String,
    val name: String,
    @SerialName("analysis_ready") val analysisReady: Boolean = true
) {
    val analysis_ready: Boolean get() = analysisReady
}

@Serializable
data class SportDto(
    val id: String,
    @SerialName("display_name") val displayName: String,
    @SerialName("icon_key") val iconKey: String = "sport",
    @SerialName("analysis_ready") val analysisReady: Boolean = true,
    val skills: List<SportSkillDto> = emptyList()
) {
    val name: String get() = displayName
    val analysis_ready: Boolean get() = analysisReady
}

@Serializable
data class ProfilePayloadDto(
    val sport: String,
    val skill: String? = null,
    val level: String = "intermediate",
    val goal: String? = null,
    val playstyle: String? = null,
    val injuries: List<String> = emptyList(),
    @SerialName("reference_player") val referencePlayer: String? = null
)

@Serializable
data class AiStatusDto(
    val configured: Boolean = false,
    val model: String = "gemini-4-argon",
    @SerialName("key_masked") val keyMasked: String = "****",
    @SerialName("last_call_ok") val lastCallOk: Boolean? = null,
    @SerialName("last_error") val lastError: String? = null,
    @SerialName("last_latency_ms") val lastLatencyMs: Int? = null,
    @SerialName("last_checked_at") val lastCheckedAt: String? = null
) {
    val key_masked: String get() = keyMasked
    val last_call_ok: Boolean? get() = lastCallOk
    val last_error: String? get() = lastError
    val last_latency_ms: Int? get() = lastLatencyMs
}

// Sealed Result pattern enforced by architecture rules
sealed interface NetworkResult<out T> {
    data class Success<out T>(val data: T) : NetworkResult<T>
    data class Error(
        val exception: Throwable,
        val code: Int? = null,
        val message: String? = null,
        val url: String? = null
    ) : NetworkResult<Nothing> {
        val fullDetail: String
            get() = buildString {
                url?.let { append("URL: $it\n") }
                append("Exception: ${exception.javaClass.name}")
                exception.message?.let { append("\nMessage: $it") }
                code?.let { append("\nHTTP Code: $it") }
            }
    }
    data object Loading : NetworkResult<Nothing>
}

@Serializable
data class CoachConverseRequestDto(
    @SerialName("user_id") val userId: String? = null,
    val message: String,
    @SerialName("session_id") val sessionId: String? = null
)

@Serializable
data class CoachConverseResponseDto(
    @SerialName("reply_text") val replyText: String,
    @SerialName("audio_cue_url") val audioCueUrl: String? = null,
    @SerialName("audio_cue_text") val audioCueText: String? = null,
    @SerialName("dynamic_widgets") val dynamicWidgets: List<JsonObject> = emptyList(),
    @SerialName("latency_ms") val latencyMs: Int? = null
)
