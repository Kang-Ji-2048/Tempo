package com.tempo.app.feature.ingestion.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class BiometricPointDto(
    @SerialName("timestamp_ms") val timestampMs: Long,
    @SerialName("heart_rate") val heartRate: Int,
    val cadence: Int? = null,
    @SerialName("active_energy_burned") val activeEnergyBurned: Double? = null
)

@Serializable
data class SessionIngestMetadata(
    @SerialName("session_id") val sessionId: String? = null,
    @SerialName("user_id") val userId: String,
    val sport: String,
    @SerialName("stroke_type") val strokeType: String,
    @SerialName("target_archetype") val targetArchetype: String? = null,
    @SerialName("user_intent") val userIntent: String? = null,
    val telemetry: List<BiometricPointDto> = emptyList()
)
