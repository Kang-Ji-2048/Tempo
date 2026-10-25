package com.tempo.app

import com.tempo.app.di.NetworkModule
import com.tempo.app.feature.sdui.data.WidgetParser
import com.tempo.app.feature.sdui.model.CheckInScheduleWidget
import com.tempo.app.feature.sdui.model.ChoiceWidget
import com.tempo.app.feature.sdui.model.ConceptQuizWidget
import com.tempo.app.feature.sdui.model.PathProgressWidget
import com.tempo.app.feature.sdui.model.UnknownWidget
import com.tempo.app.network.models.AuthResponseDto
import com.tempo.app.network.models.CoachConverseResponseDto
import com.tempo.app.network.models.CoachMemoryResponseDto
import com.tempo.app.network.models.OnboardingStepResponseDto
import com.tempo.app.network.models.ProfileUpdateResponseDto
import com.tempo.app.network.models.SportDto
import com.tempo.app.network.models.UserProfileDto
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Decodes real backend responses (captured by backend/scripts/capture_api_contract.py) with the app's
 * own Json config, so a backend shape change fails here instead of as a mislabeled error on a 200.
 */
class ApiContractTest {

    private val json = NetworkModule.provideJson()
    private val parser = WidgetParser()

    private fun fixture(name: String): String =
        requireNotNull(javaClass.classLoader?.getResource("contract/$name.json")) { "missing fixture $name" }.readText()

    private fun assertKnownWidgets(widgets: List<JsonObject>) {
        val unknown = widgets.map(parser::parseOne).filterIsInstance<UnknownWidget>()
        assertTrue("widgets failed to decode: ${unknown.map { it.widgetType }}", unknown.isEmpty())
    }

    @Test
    fun `sign-up, sports and profile responses decode`() {
        val auth = json.decodeFromString<AuthResponseDto>(fixture("auth_register"))
        assertTrue(auth.userId.isNotBlank())

        val sports = json.decodeFromString<List<SportDto>>(fixture("sports"))
        assertEquals(listOf("badminton", "tennis"), sports.filter { it.analysisReady }.map { it.id })

        // POST /api/v1/profile echoes injuries as [] and reference_player as null; this used to throw.
        val saved = json.decodeFromString<ProfileUpdateResponseDto>(fixture("profile_update"))
        assertEquals("profile_updated", saved.status)
        assertEquals("one_hand_backhand", saved.skill)
        assertEquals("none", saved.injuries)
    }

    @Test
    fun `auth me tells login whether a sport was picked`() {
        val fresh = json.decodeFromString<UserProfileDto>(fixture("auth_me_fresh"))
        assertTrue("a fresh account must not look like it has a sport", fresh.sport.isBlank())

        val afterProfile = json.decodeFromString<UserProfileDto>(fixture("auth_me_after_profile"))
        assertEquals("tennis", afterProfile.sport)
        assertEquals("one_hand_backhand", afterProfile.skill)
    }

    @Test
    fun `onboarding walks quiz, quiz, motivation, frequency, schedule, plan`() {
        fun step(name: String) = json.decodeFromString<OnboardingStepResponseDto>(fixture("onboarding_after_$name"))

        val q1 = step("sport")
        assertEquals("level_q1", q1.stepId)
        assertTrue(parser.parseOne(q1.widget!!) is ConceptQuizWidget)

        val q2 = step("level_q1")
        assertEquals("level_q2", q2.stepId)
        assertTrue(parser.parseOne(q2.widget!!) is ConceptQuizWidget)

        val goal = step("level_q2")
        assertEquals("goal", goal.stepId)
        val goalWidget = parser.parseOne(goal.widget!!) as ChoiceWidget
        assertEquals(listOf("fitness", "social_match_play", "tournament_mastery", "technique_refinement"),
            goalWidget.options.map { it.id })

        val intensity = step("goal")
        assertEquals("intensity", intensity.stepId)
        val frequency = parser.parseOne(intensity.widget!!) as ChoiceWidget
        assertEquals(listOf("2x / week", "3x / week", "5x / week"), frequency.options.map { it.label })

        val schedule = step("intensity")
        assertEquals("schedule", schedule.stepId)
        assertTrue(parser.parseOne(schedule.widget!!) is CheckInScheduleWidget)

        val done = step("schedule")
        assertTrue(done.isCompleted)
        val path = parser.parseOne(done.widget!!) as PathProgressWidget
        assertEquals(5, path.nodes.size)
        assertEquals("tennis", done.userProfile!!.sport)
    }

    @Test
    fun `home renders the five-node path from coach memory`() {
        val memory = json.decodeFromString<CoachMemoryResponseDto>(fixture("coach_memory"))
        assertTrue(memory.onboardingComplete)
        assertEquals("Tennis", memory.header.sportDisplay)
        assertEquals(5, memory.header.totalNodes)
        assertKnownWidgets(memory.widgets)
        val path = parser.parseOne(memory.widgets.first()) as PathProgressWidget
        assertEquals(5, path.nodes.size)
        assertEquals(path.nodes.first().nodeId, path.activeNodeId)
    }

    @Test
    fun `thea converse reply decodes with speak text and memory`() {
        val reply = json.decodeFromString<CoachConverseResponseDto>(fixture("coach_converse"))
        assertTrue(reply.replyText.isNotBlank())
        assertFalse(reply.speakText.isNullOrBlank())
        assertTrue(reply.athleteMemory != null)
        assertKnownWidgets(reply.dynamicWidgets)
    }
}
