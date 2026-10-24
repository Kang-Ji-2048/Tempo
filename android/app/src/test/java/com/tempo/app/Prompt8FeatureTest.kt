package com.tempo.app

import com.tempo.app.data.PlayerIdentity
import com.tempo.app.feature.biometrics.BiometricDataPoint
import com.tempo.app.feature.ingestion.model.BiometricPointDto
import com.tempo.app.feature.ingestion.model.SessionIngestMetadata
import com.tempo.app.feature.schedule.ScheduleViewModel
import com.tempo.app.feature.sdui.data.WidgetParser
import com.tempo.app.feature.sdui.data.toRequest
import com.tempo.app.feature.sdui.model.CheckInScheduleWidget
import com.tempo.app.feature.sdui.model.ScheduleSlot
import com.tempo.app.feature.sdui.model.WidgetAction
import com.tempo.app.network.MockTempoApi
import com.tempo.app.network.models.NetworkResult
import com.tempo.app.network.models.UserScheduleDto
import com.tempo.app.repository.SessionRepositoryImpl
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class Prompt8FeatureTest {

    private val json = Json {
        ignoreUnknownKeys = true
        isLenient = true
        encodeDefaults = true
    }

    @Test
    fun testMockTempoApiSchedulePersistence() = runBlocking {
        val mockApi = MockTempoApi()
        val userId = "athlete_prompt8"

        // Initial schedule
        val initial = mockApi.getSchedule(userId)
        assertEquals(userId, initial.userId)
        assertEquals(listOf("Monday", "Wednesday", "Friday"), initial.daysOfWeek)
        assertEquals("18:00", initial.targetTimeUtc)

        // Update schedule
        val updatedSchedule = initial.copy(
            daysOfWeek = listOf("Tuesday", "Thursday", "Saturday"),
            targetTimeUtc = "19:30",
            preferredChannel = "push"
        )
        val saveResponse = mockApi.updateSchedule(updatedSchedule)
        assertEquals("19:30", saveResponse.targetTimeUtc)

        // Reload from mock API and verify persistence
        val reloaded = mockApi.getSchedule(userId)
        assertEquals(listOf("Tuesday", "Thursday", "Saturday"), reloaded.daysOfWeek)
        assertEquals("19:30", reloaded.targetTimeUtc)
        assertEquals("push", reloaded.preferredChannel)
    }

    @Test
    fun testScheduleViewModelToggleAndSave() = runBlocking {
        val mockApi = MockTempoApi()
        val sessionRepo = SessionRepositoryImpl(mockApi)
        val identity = object : PlayerIdentity {
            override var playerId = "athlete_prompt8"
            override var accessToken = ""
        }

        val viewModel = ScheduleViewModel(sessionRepo, identity)

        // Toggle Sunday into days of week
        viewModel.toggleDay("Sunday")
        viewModel.setTime("09:00")
        viewModel.setDuration(90)
        viewModel.setChannel("push")

        viewModel.saveSchedule(this).join()

        val state = viewModel.uiState.value
        assertTrue(state.saveSuccess)
        assertTrue(state.daysOfWeek.contains("Sunday"))
        assertEquals("09:00", state.targetTimeUtc)
        assertEquals(90, state.durationMinutes)
        assertEquals("push", state.preferredChannel)
    }

    @Test
    fun testCheckInScheduleWidgetSerializationAndAction() {
        val parser = WidgetParser()

        // Test parser polymorphism with classDiscriminator "widget_type"
        val jsonString = """
            {
                "widget_type": "CheckInScheduleWidget",
                "id": "cadence_w1",
                "title": "Weekly Training Schedule",
                "subtitle": "Choose your days",
                "days_of_week": ["Monday", "Wednesday", "Friday"],
                "target_time_utc": "18:00",
                "duration_minutes": 45,
                "priming_lead_minutes": 30,
                "preferred_channel": "whatsapp"
            }
        """.trimIndent()

        val widgets = parser.parseFeed("[$jsonString]")
        val parsed = widgets.first()
        assertTrue(parsed is CheckInScheduleWidget)
        val scheduleWidget = parsed as CheckInScheduleWidget
        assertEquals("cadence_w1", scheduleWidget.id)
        assertEquals(3, scheduleWidget.daysOfWeek.size)

        // Test ScheduleChanged action serialization
        val action = WidgetAction.ScheduleChanged(
            widgetId = "cadence_w1",
            daysOfWeek = listOf("Monday", "Wednesday"),
            targetTimeUtc = "18:00",
            durationMinutes = 45,
            primingLeadMinutes = 30,
            preferredChannel = "whatsapp"
        )
        val requestDto = action.toRequest("session_123")
        assertEquals("ScheduleChanged", requestDto.actionType)
        assertEquals("cadence_w1", requestDto.widgetId)
        assertEquals("18:00", requestDto.payload["target_time_utc"]?.jsonPrimitive?.content)
    }

    @Test
    fun testTelemetryEmptyFallbackRule() {
        // Enforce rule: empty list [] strictly provided when no sensor data exists
        val emptyTelemetry = emptyList<BiometricPointDto>()
        val metadata = SessionIngestMetadata(
            sessionId = "sess_001",
            userId = "athlete_1",
            sport = "badminton",
            strokeType = "overhead_clear",
            targetArchetype = "Axelsen",
            userIntent = "Steep jump smash",
            telemetry = emptyTelemetry
        )

        val jsonStr = json.encodeToString(metadata)
        val parsedJson = json.parseToJsonElement(jsonStr).jsonObject
        val telemetryArray = parsedJson["telemetry"]?.jsonArray
        assertNotNull(telemetryArray)
        assertEquals(0, telemetryArray?.size)
    }

    @Test
    fun testBiometricDataPointStructure() {
        val point = BiometricDataPoint(
            timestampMs = 1718000000000L,
            heartRate = 152,
            cadence = null,
            activeEnergyBurned = 28.5
        )

        val encoded = json.encodeToString(point)
        val decoded = json.decodeFromString<BiometricDataPoint>(encoded)
        assertEquals(152, decoded.heartRate)
        assertEquals(1718000000000L, decoded.timestampMs)
        assertEquals(null, decoded.cadence)
        assertEquals(28.5, decoded.activeEnergyBurned!!, 0.001)
    }
}
