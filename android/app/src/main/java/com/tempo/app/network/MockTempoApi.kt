package com.tempo.app.network

import com.tempo.app.network.models.SessionIngestResponseDto
import com.tempo.app.network.models.SessionRecordDto
import com.tempo.app.network.models.UserScheduleDto
import kotlinx.coroutines.delay
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import okhttp3.MultipartBody
import okhttp3.RequestBody
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton

/**
 * High-fidelity Mock implementation of TempoApi for offline development and testing.
 * Conforms to project rule: "provide a MockApi so every screen works offline".
 */
@Singleton
class MockTempoApi @Inject constructor() : TempoApi {

    private val pollCounts = java.util.concurrent.ConcurrentHashMap<String, Int>()

    override suspend fun ingestSession(
        metadata: RequestBody,
        video: MultipartBody.Part?
    ): SessionIngestResponseDto {
        delay(400) // Simulate fast network turnaround
        return SessionIngestResponseDto(
            sessionId = okio.Buffer().also { metadata.writeTo(it) }.readUtf8().let {
                kotlinx.serialization.json.Json.parseToJsonElement(it)
                    .let { element -> (element as? kotlinx.serialization.json.JsonObject)?.get("session_id") }
                    ?.let { element -> (element as? kotlinx.serialization.json.JsonPrimitive)?.content }
            } ?: UUID.randomUUID().toString(),
            status = "PENDING",
            estimatedAnalysisTimeSec = 8,
            message = "Offline mock session ingestion accepted."
        )
    }

    fun resetSessionPollCount(sessionId: String) {
        pollCounts.remove(sessionId)
    }

    override suspend fun getSession(sessionId: String): SessionRecordDto {
        delay(300)
        val count = pollCounts.compute(sessionId) { _, current -> (current ?: 0) + 1 } ?: 1

        val currentStatus = when {
            sessionId.contains("fail", ignoreCase = true) -> "FAILED"
            count <= 1 -> "PENDING"
            count == 2 -> "ANALYZING"
            else -> "COMPLETED"
        }

        if (currentStatus == "FAILED") {
            return SessionRecordDto(
                sessionId = sessionId,
                userId = "usr_sumanth_001",
                sport = "badminton",
                strokeType = "overhead_clear",
                targetArchetype = "Viktor Axelsen",
                status = "FAILED",
                errorMessage = "Biomechanical analysis failed: athlete body lost from frame at impact point."
            )
        }

        if (currentStatus == "PENDING" || currentStatus == "ANALYZING") {
            return SessionRecordDto(
                sessionId = sessionId,
                userId = "usr_sumanth_001",
                sport = "badminton",
                strokeType = "overhead_clear",
                targetArchetype = "Viktor Axelsen",
                status = currentStatus,
                telemetryCount = 3
            )
        }

        // COMPLETED state with rich SDUI widgets
        val mockFeedback = buildJsonObject {
            put("overall_score", 85)
            put("matched_archetype", "Viktor Axelsen")
            put("primary_flaw", "Elbow dropped to 158.4° at contact")
            put("concise_audio_cue", "Accelerate forearm pronation at peak reach.")
            put("coach_voice_note_script", "Great session today! Your contact reach was explosive.")
            put("kinetic_phases", kotlinx.serialization.json.buildJsonArray {
                add(buildJsonObject {
                    put("phase_name", "Preparation")
                    put("timestamp_ms", 300)
                    put("form_accuracy_score", 92)
                    put("observation", "Stable base with strong non-racket arm elevation for tracking shuttle height.")
                })
                add(buildJsonObject {
                    put("phase_name", "Loading")
                    put("timestamp_ms", 850)
                    put("form_accuracy_score", 80)
                    put("observation", "Slightly restricted thoracic arch during loading phase under fatigue.")
                })
                add(buildJsonObject {
                    put("phase_name", "Impact")
                    put("timestamp_ms", 1320)
                    put("form_accuracy_score", 74)
                    put("observation", "Elbow flexion at contact (158.4°) lacked full extension compared to Axelsen profile (175°).")
                })
                add(buildJsonObject {
                    put("phase_name", "Follow-Through")
                    put("timestamp_ms", 1750)
                    put("form_accuracy_score", 88)
                    put("observation", "Smooth kinetic dissipation across the torso with quick split-step recovery.")
                })
            })
        }

        val mockWidget1 = buildJsonObject {
            put("widget_type", "PathProgressWidget")
            put("title", "Forearm Mechanics Path")
            put("current_streak", 5)
            put("active_node_id", "node_pronation_03")
            put("nodes", kotlinx.serialization.json.buildJsonArray {
                add(buildJsonObject {
                    put("node_id", "node_pronation_01")
                    put("title", "High Elbow Setup")
                    put("status", "DONE")
                    put("xp_reward", 50)
                })
                add(buildJsonObject {
                    put("node_id", "node_pronation_02")
                    put("title", "Shoulder Rotation")
                    put("status", "DONE")
                    put("xp_reward", 50)
                })
                add(buildJsonObject {
                    put("node_id", "node_pronation_03")
                    put("title", "Peak Pronation Speed")
                    put("status", "ACTIVE")
                    put("xp_reward", 75)
                })
                add(buildJsonObject {
                    put("node_id", "node_pronation_04")
                    put("title", "Wrist Snap Recovery")
                    put("status", "LOCKED")
                    put("xp_reward", 100)
                })
            })
        }

        val mockWidget2 = buildJsonObject {
            put("widget_type", "DrillCardWidget")
            put("id", "drill_pronation_wall_30s")
            put("title", "30s Rapid Pronation Drill")
            put("instruction", "Rapidly rotate forearm against wall target maintaining high elbow position.")
            put("target_reps", 15)
            put("focus_cue", "Full elbow extension at contact.")
        }

        val mockWidget3 = buildJsonObject {
            put("widget_type", "ConceptQuizWidget")
            put("id", "quiz_impact_angle")
            put("question", "What is the primary power generation mechanism in an overhead clear?")
            put("options", kotlinx.serialization.json.buildJsonArray {
                add(kotlinx.serialization.json.JsonPrimitive("Bicep flexion"))
                add(kotlinx.serialization.json.JsonPrimitive("Forearm pronation & kinetic chain"))
                add(kotlinx.serialization.json.JsonPrimitive("Wrist flick only"))
            })
            put("correct_index", 1)
            put("explanation", "Forearm pronation combined with kinetic chain sequencing transfers maximum energy into the shuttlecock.")
        }

        return SessionRecordDto(
            sessionId = sessionId,
            userId = "usr_sumanth_001",
            sport = "badminton",
            strokeType = "overhead_clear",
            targetArchetype = "Viktor Axelsen",
            status = "COMPLETED",
            telemetryCount = 3,
            geminiFeedback = mockFeedback,
            activeWidgets = listOf(mockWidget1, mockWidget2, mockWidget3),
            kinematicVector = listOf(0.97f, 0.93f, 0.95f, 0.91f, 0.80f, 0.94f)
        )
    }

    override suspend fun getSchedule(userId: String): UserScheduleDto {
        delay(200)
        return UserScheduleDto(
            userId = userId,
            sport = "badminton",
            strokeType = "overhead_clear",
            daysOfWeek = listOf("Monday", "Wednesday", "Friday"),
            targetTimeUtc = "18:00",
            primingLeadMinutes = 30,
            preferredChannel = "whatsapp",
            isActive = true
        )
    }

    override suspend fun updateSchedule(schedule: UserScheduleDto): UserScheduleDto {
        delay(200)
        return schedule
    }
}
