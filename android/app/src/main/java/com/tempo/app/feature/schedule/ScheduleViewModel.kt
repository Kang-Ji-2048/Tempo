package com.tempo.app.feature.schedule

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.tempo.app.data.PlayerIdentity
import com.tempo.app.network.models.NetworkResult
import com.tempo.app.network.models.UserScheduleDto
import com.tempo.app.repository.SessionRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class ScheduleUiState(
    val userId: String = "athlete",
    val sport: String = "badminton",
    val strokeType: String = "overhead_clear",
    val daysOfWeek: List<String> = listOf("Monday", "Wednesday", "Friday"),
    val targetTimeUtc: String = "18:00",
    val primingLeadMinutes: Int = 30,
    val preferredChannel: String = "whatsapp",
    val isActive: Boolean = true,
    val durationMinutes: Int = 45,
    val recentBrief: String? = null,
    val isLoading: Boolean = false,
    val isSaving: Boolean = false,
    val saveSuccess: Boolean = false,
    val errorMessage: String? = null
)

@HiltViewModel
class ScheduleViewModel @Inject constructor(
    private val sessionRepository: SessionRepository,
    private val identity: PlayerIdentity
) : ViewModel() {

    private val _uiState = MutableStateFlow(
        ScheduleUiState(userId = identity.userId.ifBlank { "user_1" })
    )
    val uiState: StateFlow<ScheduleUiState> = _uiState.asStateFlow()

    fun loadSchedule(scope: kotlinx.coroutines.CoroutineScope = viewModelScope): kotlinx.coroutines.Job {
        val user = identity.userId.ifBlank { "user_1" }
        _uiState.update { it.copy(isLoading = true, errorMessage = null, userId = user) }

        return scope.launch {
            when (val result = sessionRepository.getSchedule(user)) {
                is NetworkResult.Success -> {
                    val dto = result.data
                    _uiState.update {
                        it.copy(
                            userId = dto.userId,
                            sport = dto.sport,
                            strokeType = dto.strokeType,
                            daysOfWeek = dto.daysOfWeek,
                            targetTimeUtc = dto.targetTimeUtc,
                            primingLeadMinutes = dto.primingLeadMinutes,
                            preferredChannel = dto.preferredChannel,
                            isActive = dto.isActive,
                            recentBrief = dto.recentBrief,
                            isLoading = false
                        )
                    }
                }
                is NetworkResult.Error -> {
                    _uiState.update {
                        it.copy(
                            isLoading = false,
                            errorMessage = result.message ?: "Failed to load cadence schedule"
                        )
                    }
                }
                NetworkResult.Loading -> Unit
            }
        }
    }

    fun toggleDay(day: String) {
        _uiState.update { current ->
            val list = current.daysOfWeek.toMutableList()
            if (list.contains(day)) {
                if (list.size > 1) list.remove(day)
            } else {
                list.add(day)
            }
            current.copy(daysOfWeek = list, saveSuccess = false)
        }
    }

    fun setTime(time: String) {
        _uiState.update { it.copy(targetTimeUtc = time, saveSuccess = false) }
    }

    fun setDuration(minutes: Int) {
        _uiState.update { it.copy(durationMinutes = minutes, saveSuccess = false) }
    }

    fun setPrimingLeadMinutes(minutes: Int) {
        _uiState.update { it.copy(primingLeadMinutes = minutes, saveSuccess = false) }
    }

    fun setChannel(channel: String) {
        _uiState.update { it.copy(preferredChannel = channel, saveSuccess = false) }
    }

    fun toggleActive(active: Boolean) {
        _uiState.update { it.copy(isActive = active, saveSuccess = false) }
    }

    fun saveSchedule(scope: kotlinx.coroutines.CoroutineScope = viewModelScope): kotlinx.coroutines.Job {
        val current = _uiState.value
        _uiState.update { it.copy(isSaving = true, errorMessage = null, saveSuccess = false) }

        val scheduleDto = UserScheduleDto(
            userId = current.userId,
            sport = current.sport,
            strokeType = current.strokeType,
            daysOfWeek = current.daysOfWeek,
            targetTimeUtc = current.targetTimeUtc,
            primingLeadMinutes = current.primingLeadMinutes,
            preferredChannel = current.preferredChannel,
            isActive = current.isActive
        )

        return scope.launch {
            when (val result = sessionRepository.updateSchedule(scheduleDto)) {
                is NetworkResult.Success -> {
                    val updated = result.data
                    _uiState.update {
                        it.copy(
                            userId = updated.userId,
                            sport = updated.sport,
                            strokeType = updated.strokeType,
                            daysOfWeek = updated.daysOfWeek,
                            targetTimeUtc = updated.targetTimeUtc,
                            primingLeadMinutes = updated.primingLeadMinutes,
                            preferredChannel = updated.preferredChannel,
                            isActive = updated.isActive,
                            isSaving = false,
                            saveSuccess = true
                        )
                    }
                }
                is NetworkResult.Error -> {
                    _uiState.update {
                        it.copy(
                            isSaving = false,
                            errorMessage = result.message ?: "Failed to save schedule"
                        )
                    }
                }
                NetworkResult.Loading -> Unit
            }
        }
    }
}
