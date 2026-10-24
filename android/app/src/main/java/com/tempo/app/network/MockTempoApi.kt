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

    override suspend fun ingestSession(
        metadata: RequestBody,
        video: MultipartBody.Part?
    ): SessionIngestResponseDto {
        delay(400) // Simulate fast network turnaround
        return SessionIngestResponseDto(
            sessionId = UUID.randomUUID().toString(),
            status = "PENDING",
            estimatedAnalysisTimeSec = 8,
            message = "Offline mock session ingestion accepted."
        )
    }

    override suspend fun getSession(sessionId: String): SessionRecordDto {
        delay(300)
        val mockFeedback = buildJsonObject {
            put("overall_score", 85)
            put("matched_archetype", "Viktor Axelsen")
            put("primary_flaw", "Elbow dropped to 158.4° at contact")
            put("concise_audio_cue", "Accelerate forearm pronation at peak reach.")
            put("coach_voice_note_script", "Great session today! Your contact reach was explosive.")
        }

        val mockWidget1 = buildJsonObject {
            put("widget_type", "PathProgressWidget")
            put("current_streak", 5)
            put("active_node_id", "node_pronation_03")
        }

        val mockWidget2 = buildJsonObject {
            put("widget_type", "DrillCardWidget")
            put("id", "drill_pronation_wall_30s")
            put("title", "30s Rapid Pronation Drill")
            put("instruction", "Rapidly rotate forearm against wall target.")
            put("target_reps", 15)
            put("focus_cue", "Full elbow extension at contact.")
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
            activeWidgets = listOf(mockWidget1, mockWidget2),
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
