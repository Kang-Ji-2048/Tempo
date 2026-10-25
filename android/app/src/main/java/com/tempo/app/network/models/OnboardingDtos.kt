package com.tempo.app.network.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

@Serializable
data class OnboardingStepRequestDto(
    @SerialName("step_id") val stepId: String = "",
    val answer: String = "",
    val answers: Map<String, String> = emptyMap()
)

@Serializable
data class UserProfileDto(
    @SerialName("user_id") val userId: String = "user_1",
    val sport: String = "badminton",
    val level: String = "intermediate",
    val goal: String = "overhead_power",
    val playstyle: String = "aggressive",
    val injuries: String = "none",
    @SerialName("target_archetype") val targetArchetype: String = "Viktor Axelsen",
    @SerialName("calibration_completed") val calibrationCompleted: Boolean = true
)

@Serializable
data class OnboardingStepResponseDto(
    @SerialName("step_id") val stepId: String,
    val progress: Float = 0.0f,
    @SerialName("coach_message") val coachMessage: String = "",
    val widget: JsonObject? = null,
    @SerialName("is_completed") val isCompleted: Boolean = false,
    @SerialName("user_profile") val userProfile: UserProfileDto? = null
)

@Serializable
data class CoachMemoryHeaderDto(
    val sport: String? = null,
    @SerialName("sport_display") val sportDisplay: String? = null,
    val level: String? = null,
    val intensity: String? = null,
    @SerialName("sessions_per_week") val sessionsPerWeek: Int = 0,
    @SerialName("cadence_label") val cadenceLabel: String? = null,
    @SerialName("completed_nodes") val completedNodes: Int = 0,
    @SerialName("total_nodes") val totalNodes: Int = 0
)

/** `GET /api/v1/coach/memory`: the shared athlete_memory rendered as home-screen SDUI widgets. */
@Serializable
data class CoachMemoryResponseDto(
    @SerialName("athlete_memory") val athleteMemory: JsonObject? = null,
    val header: CoachMemoryHeaderDto = CoachMemoryHeaderDto(),
    val widgets: List<JsonObject> = emptyList(),
    @SerialName("onboarding_complete") val onboardingComplete: Boolean = false
)
