package com.tempo.app.feature.onboarding

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.tempo.app.data.local.UserProfileEntity
import com.tempo.app.feature.sdui.data.WidgetParser
import com.tempo.app.feature.sdui.model.Widget
import com.tempo.app.feature.sdui.model.WidgetAction
import com.tempo.app.network.models.NetworkResult
import com.tempo.app.network.models.OnboardingStepRequestDto
import com.tempo.app.network.models.UserProfileDto
import com.tempo.app.repository.OnboardingRepository
import com.tempo.app.repository.UserProfileRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import javax.inject.Inject

private const val QUIZ_EXPLANATION_MS = 1200L

data class OnboardingUiState(
    val stepId: String = "init",
    val progress: Float = 0.08f,
    val coachMessage: String = "Welcome to Tempo! Connecting with your AI coach...",
    val currentWidget: Widget? = null,
    val isCompleted: Boolean = false,
    val userProfile: UserProfileDto? = null,
    val answers: Map<String, String> = emptyMap(),
    val isLoading: Boolean = false,
    val errorMessage: String? = null,
    /** Schedule edits held until the athlete taps Continue (the card emits on every tweak). */
    val pendingSchedule: PendingSchedule = PendingSchedule()
)

data class PendingSchedule(
    val daysOfWeek: List<String>? = null,
    val targetTimeUtc: String? = null,
    val preferredChannel: String? = null
) {
    /** JSON understood by `/onboarding/next`, or "next" to accept the suggested schedule. */
    fun toAnswer(): String {
        if (daysOfWeek == null && targetTimeUtc == null && preferredChannel == null) return "next"
        return buildJsonObject {
            daysOfWeek?.let { days -> put("days_of_week", JsonArray(days.map { JsonPrimitive(it) })) }
            targetTimeUtc?.let { put("target_time_utc", it) }
            preferredChannel?.let { put("preferred_channel", it) }
        }.toString()
    }
}

sealed interface OnboardingNavigationEvent {
    data object NavigateToHome : OnboardingNavigationEvent
}

@HiltViewModel
class OnboardingViewModel @Inject constructor(
    private val onboardingRepository: OnboardingRepository,
    private val userProfileRepository: UserProfileRepository,
    private val widgetParser: WidgetParser,
    private val identity: com.tempo.app.data.PlayerIdentity
) : ViewModel() {

    private val _uiState = MutableStateFlow(OnboardingUiState())
    val uiState: StateFlow<OnboardingUiState> = _uiState.asStateFlow()

    private val _navigationEvents = MutableSharedFlow<OnboardingNavigationEvent>()
    val navigationEvents: SharedFlow<OnboardingNavigationEvent> = _navigationEvents.asSharedFlow()

    init {
        loadInitialStep()
    }

    fun loadInitialStep() {
        // The sport picked on SportSelectionScreen is the first answer written to athlete_memory.
        val sport = identity.sport
        if (!sport.isNullOrBlank()) {
            fetchNextStep(stepId = "sport", answer = sport)
        } else {
            fetchNextStep(stepId = "", answer = "")
        }
    }

    fun submitSchedule() {
        fetchNextStep(stepId = _uiState.value.stepId, answer = _uiState.value.pendingSchedule.toAnswer())
    }

    fun onWidgetAction(action: WidgetAction) {
        val currentStep = _uiState.value.stepId
        when (action) {
            is WidgetAction.ChoiceSelected -> {
                val answer = action.optionIds.firstOrNull() ?: action.freeText ?: ""
                fetchNextStep(stepId = currentStep, answer = answer)
            }
            is WidgetAction.CaptureRequested -> {
                fetchNextStep(stepId = currentStep, answer = "captured")
            }
            is WidgetAction.QuizAnswered -> {
                viewModelScope.launch {
                    delay(QUIZ_EXPLANATION_MS) // let the athlete read the explanation
                    fetchNextStep(stepId = currentStep, answer = action.selectedIndex.toString())
                }
            }
            is WidgetAction.ScheduleChanged -> {
                _uiState.update {
                    it.copy(pendingSchedule = PendingSchedule(action.daysOfWeek, action.targetTimeUtc, action.preferredChannel))
                }
            }
            is WidgetAction.SlotPicked -> {
                _uiState.update { it.copy(pendingSchedule = it.pendingSchedule.copy(targetTimeUtc = action.slotId)) }
            }
            else -> {
                fetchNextStep(stepId = currentStep, answer = "next")
            }
        }
    }

    private fun fetchNextStep(stepId: String, answer: String) {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, errorMessage = null) }

            val updatedAnswers = _uiState.value.answers.toMutableMap()
            if (stepId.isNotBlank() && answer.isNotBlank()) {
                updatedAnswers[stepId] = answer
            }

            val request = OnboardingStepRequestDto(
                stepId = stepId,
                answer = answer,
                answers = updatedAnswers
            )

            when (val result = onboardingRepository.getNextStep(request)) {
                is NetworkResult.Success -> {
                    val response = result.data
                    val parsedWidget = response.widget?.let { widgetParser.parseOne(it) }

                    _uiState.update {
                        it.copy(
                            stepId = response.stepId,
                            progress = response.progress,
                            coachMessage = response.coachMessage,
                            currentWidget = parsedWidget,
                            isCompleted = response.isCompleted,
                            userProfile = response.userProfile,
                            answers = updatedAnswers,
                            isLoading = false,
                            pendingSchedule = PendingSchedule()
                        )
                    }
                }
                is NetworkResult.Error -> {
                    _uiState.update {
                        it.copy(
                            isLoading = false,
                            errorMessage = result.message ?: "Failed to connect to coaching server. Tap to retry."
                        )
                    }
                }
                is NetworkResult.Loading -> {
                    // Handled above
                }
            }
        }
    }

    fun completeOnboardingAndSave(allPermissionsGranted: Boolean) {
        viewModelScope.launch {
            val profile = _uiState.value.userProfile ?: UserProfileDto(
                userId = identity.userId,
                sport = _uiState.value.answers["sport"] ?: identity.sport ?: "badminton",
                level = _uiState.value.answers["level"] ?: "intermediate",
                goal = _uiState.value.answers["goal"] ?: "technique_refinement",
                playstyle = _uiState.value.answers["playstyle"] ?: "all_court",
                injuries = _uiState.value.answers["injuries"] ?: "none",
                targetArchetype = _uiState.value.answers["archetype"] ?: "Pro Benchmark",
                calibrationCompleted = true
            )

            val entity = UserProfileEntity(
                userId = identity.userId,
                sport = profile.sport,
                level = profile.level,
                goal = profile.goal,
                playstyle = profile.playstyle,
                injuries = profile.injuries,
                targetArchetype = profile.targetArchetype,
                permissionsGranted = allPermissionsGranted,
                updatedAt = System.currentTimeMillis()
            )

            identity.sport = profile.sport
            userProfileRepository.saveUserProfile(entity)
            _navigationEvents.emit(OnboardingNavigationEvent.NavigateToHome)
        }
    }
}
