package com.tempo.app.feature.saint

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

// backend/saint_commands.py::Action is the canonical schema. Params stay generic
// on the wire so adding a capability does not create a second executor in Android.
@Serializable data class SaintAction(
    val type: String,
    val params: JsonObject,
    val summary: String,
    @SerialName("requires_approval") val requiresApproval: Boolean,
    @SerialName("idempotency_key") val idempotencyKey: String,
    val user: String,
    @SerialName("expires_at") val expiresAt: String
)
@Serializable data class SaintProposal(val action: SaintAction, val signature: String)
@Serializable data class SaintCommand(val user: String, val text: String)
@Serializable data class SaintReply(
    val kind: String, val question: String? = null, val proposal: SaintProposal? = null,
    val planner: String = "deterministic_demo", val demo: Boolean = true
)
@Serializable data class SaintDecision(val proposal: SaintProposal, val approved: Boolean)
@Serializable data class SaintPreferences(
    @SerialName("home_area") val homeArea: String = "",
    @SerialName("preferred_time") val preferredTime: String = "09:00",
    val sport: String = "badminton", val level: String = "beginner"
)
@Serializable data class SaintPreferenceRecord(
    val user: String, val preferences: SaintPreferences,
    @SerialName("storage_mode") val storageMode: String = "unknown"
)
@Serializable data class SaintActionRecord(
    val user: String, val action: SaintAction, val approved: Boolean, val status: String,
    val result: JsonObject? = null, val demo: Boolean = true,
    @SerialName("storage_mode") val storageMode: String = "unknown"
)
