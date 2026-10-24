package com.tempo.app

import com.tempo.app.feature.sdui.data.WidgetParser
import com.tempo.app.feature.sdui.model.CapturePromptWidget
import com.tempo.app.feature.sdui.model.ChoiceWidget
import com.tempo.app.network.MockTempoApi
import com.tempo.app.network.models.NetworkResult
import com.tempo.app.network.models.OnboardingStepRequestDto
import com.tempo.app.repository.OnboardingRepositoryImpl
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class OnboardingRepositoryTest {

    @Test
    fun testCompleteOnboardingScriptedFlow() = runBlocking {
        val mockApi = MockTempoApi()
        val repository = OnboardingRepositoryImpl(mockApi)
        val parser = WidgetParser()

        // 1. Initial request -> Sport ChoiceWidget
        val step0 = repository.getNextStep(OnboardingStepRequestDto(stepId = "", answer = ""))
        assertTrue(step0 is NetworkResult.Success)
        val data0 = (step0 as NetworkResult.Success).data
        assertEquals("sport", data0.stepId)
        val widget0 = data0.widget?.let { parser.parseOne(it) }
        assertTrue("Widget should be ChoiceWidget", widget0 is ChoiceWidget)
        val choice0 = widget0 as ChoiceWidget
        assertEquals("sport", choice0.id)
        assertTrue(choice0.options.any { it.id == "badminton" })

        // 2. Sport answered -> Level ChoiceWidget
        val step1 = repository.getNextStep(
            OnboardingStepRequestDto(
                stepId = "sport",
                answer = "badminton",
                answers = mapOf("sport" to "badminton")
            )
        )
        assertTrue(step1 is NetworkResult.Success)
        val data1 = (step1 as NetworkResult.Success).data
        assertEquals("level", data1.stepId)
        val widget1 = data1.widget?.let { parser.parseOne(it) } as ChoiceWidget
        assertEquals("level", widget1.id)

        // 3. Level answered -> Goal ChoiceWidget
        val step2 = repository.getNextStep(
            OnboardingStepRequestDto(
                stepId = "level",
                answer = "intermediate",
                answers = mapOf("sport" to "badminton", "level" to "intermediate")
            )
        )
        assertTrue(step2 is NetworkResult.Success)
        val data2 = (step2 as NetworkResult.Success).data
        assertEquals("goal", data2.stepId)

        // 4. Goal answered -> Playstyle ChoiceWidget
        val step3 = repository.getNextStep(
            OnboardingStepRequestDto(
                stepId = "goal",
                answer = "overhead_power",
                answers = mapOf("sport" to "badminton", "level" to "intermediate", "goal" to "overhead_power")
            )
        )
        assertTrue(step3 is NetworkResult.Success)
        val data3 = (step3 as NetworkResult.Success).data
        assertEquals("playstyle", data3.stepId)

        // 5. Playstyle answered -> Injuries ChoiceWidget
        val step4 = repository.getNextStep(
            OnboardingStepRequestDto(
                stepId = "playstyle",
                answer = "aggressive",
                answers = mapOf(
                    "sport" to "badminton",
                    "level" to "intermediate",
                    "goal" to "overhead_power",
                    "playstyle" to "aggressive"
                )
            )
        )
        assertTrue(step4 is NetworkResult.Success)
        val data4 = (step4 as NetworkResult.Success).data
        assertEquals("injuries", data4.stepId)

        // 6. Injuries answered -> Archetype ChoiceWidget ("who do you want to move like?")
        val step5 = repository.getNextStep(
            OnboardingStepRequestDto(
                stepId = "injuries",
                answer = "none",
                answers = mapOf(
                    "sport" to "badminton",
                    "level" to "intermediate",
                    "goal" to "overhead_power",
                    "playstyle" to "aggressive",
                    "injuries" to "none"
                )
            )
        )
        assertTrue(step5 is NetworkResult.Success)
        val data5 = (step5 as NetworkResult.Success).data
        assertEquals("archetype", data5.stepId)
        val widget5 = data5.widget?.let { parser.parseOne(it) } as ChoiceWidget
        assertTrue(widget5.options.any { it.id == "Viktor Axelsen" })

        // 7. Archetype answered -> 5s CapturePromptWidget
        val step6 = repository.getNextStep(
            OnboardingStepRequestDto(
                stepId = "archetype",
                answer = "Viktor Axelsen",
                answers = mapOf(
                    "sport" to "badminton",
                    "level" to "intermediate",
                    "goal" to "overhead_power",
                    "playstyle" to "aggressive",
                    "injuries" to "none",
                    "archetype" to "Viktor Axelsen"
                )
            )
        )
        assertTrue(step6 is NetworkResult.Success)
        val data6 = (step6 as NetworkResult.Success).data
        assertEquals("capture_prompt", data6.stepId)
        val widget6 = data6.widget?.let { parser.parseOne(it) }
        assertTrue("Widget should be CapturePromptWidget", widget6 is CapturePromptWidget)
        val captureWidget = widget6 as CapturePromptWidget
        assertEquals(5, captureWidget.durationS)

        // 8. Capture completed -> Summary & Permissions
        val step7 = repository.getNextStep(
            OnboardingStepRequestDto(
                stepId = "capture_prompt",
                answer = "captured",
                answers = mapOf(
                    "sport" to "badminton",
                    "level" to "intermediate",
                    "goal" to "overhead_power",
                    "playstyle" to "aggressive",
                    "injuries" to "none",
                    "archetype" to "Viktor Axelsen"
                )
            )
        )
        assertTrue(step7 is NetworkResult.Success)
        val data7 = (step7 as NetworkResult.Success).data
        assertEquals("summary_permissions", data7.stepId)
        assertTrue(data7.isCompleted)
        assertNotNull(data7.userProfile)
        assertEquals("badminton", data7.userProfile?.sport)
        assertEquals("Viktor Axelsen", data7.userProfile?.targetArchetype)
        assertEquals("aggressive", data7.userProfile?.playstyle)
    }
}
