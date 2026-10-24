package com.tempo.app.feature.sdui.debug

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.tempo.app.feature.sdui.data.SduiRepository
import com.tempo.app.feature.sdui.di.MockSdui
import com.tempo.app.feature.sdui.model.WidgetAction
import com.tempo.app.network.models.NetworkResult
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import javax.inject.Inject

/**
 * Drives the SDUI gallery. Widget actions are posted to the (mock) backend and the
 * response replaces the entire widget list — the server is the source of truth.
 */
@HiltViewModel
class SduiDebugViewModel @Inject constructor(
    @MockSdui private val repository: SduiRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(SduiFeedUiState(isLoading = true))
    val state: StateFlow<SduiFeedUiState> = _state.asStateFlow()

    private val _events = Channel<SduiEvent>(Channel.BUFFERED)
    val events: Flow<SduiEvent> = _events.receiveAsFlow()

    /** Actions are applied strictly in order so responses can't overwrite each other. */
    private val actionMutex = Mutex()

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            _state.update { it.copy(isLoading = true, error = null) }
            when (val result = repository.getFeed(SESSION_ID)) {
                is NetworkResult.Success -> _state.update {
                    it.copy(items = result.data.toSduiItems(), isLoading = false)
                }
                is NetworkResult.Error -> _state.update {
                    it.copy(isLoading = false, error = result.message ?: "Couldn't load feed")
                }
                NetworkResult.Loading -> Unit
            }
        }
    }

    fun onAction(action: WidgetAction) {
        if (action is WidgetAction.CaptureRequested) {
            _events.trySend(SduiEvent.NavigateToCapture)
        }
        viewModelScope.launch {
            actionMutex.withLock {
                _state.update { it.copy(isPosting = true) }
                when (val result = repository.postAction(SESSION_ID, action)) {
                    is NetworkResult.Success -> {
                        _state.update { it.copy(items = result.data.toSduiItems(), isPosting = false, error = null) }
                        _events.send(SduiEvent.Message("${action.label()} · ${result.data.size} widgets"))
                    }
                    is NetworkResult.Error -> {
                        _state.update { it.copy(isPosting = false) }
                        _events.send(SduiEvent.Message("Couldn't sync: ${result.message ?: "network error"}"))
                    }
                    NetworkResult.Loading -> Unit
                }
            }
        }
    }

    private fun WidgetAction.label(): String = when (this) {
        is WidgetAction.QuizAnswered -> if (isCorrect) "Quiz: correct" else "Quiz: incorrect"
        is WidgetAction.DrillCompleted -> "Drill logged ($repsCompleted reps)"
        is WidgetAction.SlotPicked -> "Slot booked"
        is WidgetAction.ChoiceSelected -> "Answer sent"
        is WidgetAction.CaptureRequested -> "Capture requested"
        is WidgetAction.ScheduleChanged -> "Schedule updated ($targetTimeUtc UTC)"
    }

    private companion object {
        const val SESSION_ID = "debug"
    }
}
