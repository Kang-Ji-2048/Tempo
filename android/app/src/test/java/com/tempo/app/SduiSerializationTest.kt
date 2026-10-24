package com.tempo.app

import com.tempo.app.feature.sdui.data.MockSduiApi
import com.tempo.app.feature.sdui.data.MockWidgetFeed
import com.tempo.app.feature.sdui.data.SduiRepositoryImpl
import com.tempo.app.feature.sdui.data.WidgetParser
import com.tempo.app.feature.sdui.model.CapturePromptWidget
import com.tempo.app.feature.sdui.model.CheckInScheduleWidget
import com.tempo.app.feature.sdui.model.ChoiceWidget
import com.tempo.app.feature.sdui.model.ConceptQuizWidget
import com.tempo.app.feature.sdui.model.DrillCardWidget
import com.tempo.app.feature.sdui.model.PathProgressWidget
import com.tempo.app.feature.sdui.model.QuestionWidget
import com.tempo.app.feature.sdui.model.UnknownWidget
import com.tempo.app.feature.sdui.model.WidgetAction
import com.tempo.app.network.models.NetworkResult
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class SduiSerializationTest {

    private lateinit var parser: WidgetParser
    private lateinit var mockApi: MockSduiApi
    private lateinit var repository: SduiRepositoryImpl

    @Before
    fun setUp() {
        parser = WidgetParser()
        mockApi = MockSduiApi()
        repository = SduiRepositoryImpl(mockApi, parser)
    }

    @Test
    fun parseFeed_parsesAllKnownWidgetsInMockFeed() {
        val widgets = parser.parseFeed(MockWidgetFeed.JSON)
        assertTrue("Parsed widgets should not be empty", widgets.isNotEmpty())

        val pathWidget = widgets.filterIsInstance<PathProgressWidget>().firstOrNull()
        assertNotNull("PathProgressWidget should be parsed", pathWidget)
        assertEquals(5, pathWidget?.currentStreak)
        assertEquals("node_pronation_03", pathWidget?.activeNodeId)
        assertEquals(6, pathWidget?.nodes?.size)

        val captureWidget = widgets.filterIsInstance<CapturePromptWidget>().firstOrNull()
        assertNotNull("CapturePromptWidget should be parsed", captureWidget)
        assertEquals(45, captureWidget?.durationS)

        val drillWidget = widgets.filterIsInstance<DrillCardWidget>().firstOrNull()
        assertNotNull("DrillCardWidget should be parsed", drillWidget)
        assertEquals(15, drillWidget?.targetReps)

        val quizWidget = widgets.filterIsInstance<ConceptQuizWidget>().firstOrNull()
        assertNotNull("ConceptQuizWidget should be parsed", quizWidget)
        assertEquals(0, quizWidget?.correctIndex)
        assertEquals(4, quizWidget?.options?.size)

        val scheduleWidget = widgets.filterIsInstance<CheckInScheduleWidget>().firstOrNull()
        assertNotNull("CheckInScheduleWidget should be parsed", scheduleWidget)
        assertEquals(4, scheduleWidget?.slots?.size)

        val questionWidget = widgets.filterIsInstance<QuestionWidget>().firstOrNull()
        assertNotNull("QuestionWidget should be parsed", questionWidget)
        assertEquals(3, questionWidget?.quickReplies?.size)

        val choiceWidget = widgets.filterIsInstance<ChoiceWidget>().firstOrNull()
        assertNotNull("ChoiceWidget should be parsed", choiceWidget)
        assertTrue(choiceWidget?.multiSelect == true)
        assertEquals(3, choiceWidget?.options?.size)
    }

    @Test
    fun parseFeed_unknownWidgetTypeDoesNotCrashAndMapsToUnknown() {
        // Specifically tests the user requirement: adding {"widget_type":"Foo"} to the JSON does not crash
        val jsonWithFoo = """
            [
              {"widget_type": "Foo", "bar": 123},
              {"widget_type": "Bar", "nested": {"a": "b"}},
              {"missing_discriminator": "test"}
            ]
        """.trimIndent()

        val widgets = parser.parseFeed(jsonWithFoo)
        assertEquals(3, widgets.size)

        val first = widgets[0]
        assertTrue(first is UnknownWidget)
        assertEquals("Foo", (first as UnknownWidget).widgetType)

        val second = widgets[1]
        assertTrue(second is UnknownWidget)
        assertEquals("Bar", (second as UnknownWidget).widgetType)

        val third = widgets[2]
        assertTrue(third is UnknownWidget)
        assertEquals("missing", (third as UnknownWidget).widgetType)
    }

    @Test
    fun parseFeed_handlesMalformedKnownWidgetGracefully() {
        // Missing required fields on DrillCardWidget should degrade to UnknownWidget without throwing
        val malformedJson = """
            [
              {"widget_type": "DrillCardWidget", "id": "broken_drill"}
            ]
        """.trimIndent()

        val widgets = parser.parseFeed(malformedJson)
        assertEquals(1, widgets.size)
        assertTrue("Malformed drill should degrade to UnknownWidget", widgets[0] is UnknownWidget)
        assertEquals("DrillCardWidget", (widgets[0] as UnknownWidget).widgetType)
    }

    @Test
    fun repository_getFeedAndPostActionUpdatesList() = runBlocking {
        val initialResult = repository.getFeed("session_test_01")
        assertTrue(initialResult is NetworkResult.Success)
        val initialWidgets = (initialResult as NetworkResult.Success).data
        assertTrue(initialWidgets.isNotEmpty())

        // 1. Post QuizAnswered action
        val quizAction = WidgetAction.QuizAnswered(
            widgetId = "quiz_hip_rotation",
            selectedIndex = 0,
            isCorrect = true
        )
        val quizResult = repository.postAction("session_test_01", quizAction)
        assertTrue(quizResult is NetworkResult.Success)
        val afterQuizWidgets = (quizResult as NetworkResult.Success).data
        val updatedQuiz = afterQuizWidgets.filterIsInstance<ConceptQuizWidget>().firstOrNull { it.id == "quiz_hip_rotation" }
        assertEquals(0, updatedQuiz?.answeredIndex)

        // 2. Post DrillCompleted action (should remove drill and advance path progress)
        val drillAction = WidgetAction.DrillCompleted(
            widgetId = "drill_pronation_wall_30s",
            repsCompleted = 15
        )
        val drillResult = repository.postAction("session_test_01", drillAction)
        assertTrue(drillResult is NetworkResult.Success)
        val afterDrillWidgets = (drillResult as NetworkResult.Success).data
        val remainingDrill = afterDrillWidgets.filterIsInstance<DrillCardWidget>().firstOrNull { it.id == "drill_pronation_wall_30s" }
        assertEquals("Completed drill should be removed from active feed", null, remainingDrill)

        val pathWidget = afterDrillWidgets.filterIsInstance<PathProgressWidget>().firstOrNull()
        assertNotNull(pathWidget)
        assertEquals(6, pathWidget?.currentStreak) // was 5, now 6
        assertEquals("node_reach_04", pathWidget?.activeNodeId) // advanced from pronation to reach
    }
}
