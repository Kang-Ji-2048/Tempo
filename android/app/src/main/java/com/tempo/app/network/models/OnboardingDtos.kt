package com.tempo.app.network.models

import kotlinx.serialization.KSerializer
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonDecoder
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/**
 * Decodes a field the backend sends as a string, a list of strings, or null (e.g. `injuries`: `/auth/me`
 * stores `[]`, onboarding sends `"none"`) into one display string, instead of failing the whole response.
 */
object LenientStringSerializer : KSerializer<String> {
    override val descriptor: SerialDescriptor = PrimitiveSerialDescriptor("LenientString", PrimitiveKind.STRING)

    override fun deserialize(decoder: Decoder): String {
        val element = (decoder as? JsonDecoder)?.decodeJsonElement() ?: return decoder.decodeString()
        return when (element) {
            is JsonArray -> element.mapNotNull { (it as? JsonPrimitive)?.contentOrNull }.joinToString(", ").ifBlank { "none" }
            is JsonPrimitive -> element.contentOrNull ?: "none"
            else -> "none"
        }
    }

    override fun serialize(encoder: Encoder, value: String) = encoder.encodeString(value)
}

@Serializable
data class OnboardingStepRequestDto(
    @SerialName("step_id") val stepId: String = "",
    val answer: String = "",
    val answers: Map<String, String> = emptyMap()
)

/** `/auth/me`, `/profile` and onboarding's `user_profile`. Every field has a default: a fresh account has none. */
@Serializable
data class UserProfileDto(
    @SerialName("user_id") val userId: String = "",
    /** Blank until the athlete picks a sport (login uses this to decide whether to show sport selection). */
    val sport: String = "",
    val skill: String? = null,
    val level: String = "intermediate",
    val goal: String = "technique_refinement",
    val playstyle: String = "regular",
    @Serializable(with = LenientStringSerializer::class) val injuries: String = "none",
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

@Serializable
data class WhatsAppLinkRequestDto(@SerialName("phone_number") val phoneNumber: String)

/** `POST /api/v1/coach/whatsapp/link`: the phone saved on athlete_memory so Thea's WhatsApp knows you. */
@Serializable
data class WhatsAppLinkResponseDto(
    @SerialName("phone_number") val phoneNumber: String,
    @SerialName("prefill_text") val prefillText: String = "Hi Thea!",
    @SerialName("wa_link") val waLink: String? = null
)

/** `POST /api/v1/profile` echo. All optional: a 200 must never fail to decode. */
@Serializable
data class ProfileUpdateResponseDto(
    val status: String? = null,
    @SerialName("user_id") val userId: String? = null,
    val sport: String? = null,
    val skill: String? = null,
    val level: String? = null,
    val goal: String? = null,
    val playstyle: String? = null,
    @Serializable(with = LenientStringSerializer::class) val injuries: String = "none",
    @SerialName("reference_player") val referencePlayer: String? = null,
    @SerialName("updated_at") val updatedAt: String? = null
)

/** `GET /api/v1/coach/brief/me`: compact Tempo context for the WhatsApp hand-off to Thea. */
@Serializable
data class CoachBriefDto(
    @SerialName("brief_text") val briefText: String = "",
    @SerialName("whatsapp_link") val whatsappLink: String? = null,
    @SerialName("thea_number") val theaNumber: String? = null
)

/** `GET /api/v1/coach/memory/version`: poll this; refetch memory only when it changes. */
@Serializable
data class MemoryVersionDto(
    @SerialName("updated_at") val updatedAt: String? = null,
    @SerialName("chat_turns") val chatTurns: Int = 0
)

@Serializable
data class CourtDto(
    @SerialName("facility_id") val facilityId: String = "",
    val name: String = "",
    val postcode: String? = null,
    val sports: List<String> = emptyList(),
    val indoor: Boolean? = null,
    val outdoor: Boolean? = null,
    @SerialName("distance_km") val distanceKm: Double = 0.0
)

@Serializable
data class PlayCallDto(val decision: String = "", val venue: String? = null, val reason: String = "")

/** `GET /api/v1/coach/courts`: $nearSphere courts plus a play / move indoors / postpone call. */
@Serializable
data class CourtsResponseDto(
    val courts: List<CourtDto> = emptyList(),
    @SerialName("play_call") val playCall: PlayCallDto? = null,
    @SerialName("booking_note") val bookingNote: String? = null,
    @SerialName("search_method") val searchMethod: String? = null
)
