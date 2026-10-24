package com.tempo.app.feature.sports

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.tempo.app.data.PlayerIdentity
import com.tempo.app.data.local.UserProfileEntity
import com.tempo.app.network.TempoApi
import com.tempo.app.network.models.NetworkResult
import com.tempo.app.network.models.ProfilePayloadDto
import com.tempo.app.network.models.SportDto
import com.tempo.app.network.models.SportSkillDto
import com.tempo.app.repository.UserProfileRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class SportSelectionUiState(
    val sports: List<SportDto> = emptyMap<String, Any>().let { emptyList() },
    val selectedSport: SportDto? = null,
    val selectedSkill: SportSkillDto? = null,
    val showSkillPicker: Boolean = false,
    val isLoading: Boolean = false,
    val isSaving: Boolean = false,
    val errorMessage: String? = null,
    val errorDetail: String? = null
)

@HiltViewModel
class SportSelectionViewModel @Inject constructor(
    private val tempoApi: TempoApi,
    private val userProfileRepository: UserProfileRepository,
    private val identity: PlayerIdentity
) : ViewModel() {

    private val _uiState = MutableStateFlow(SportSelectionUiState())
    val uiState: StateFlow<SportSelectionUiState> = _uiState.asStateFlow()

    init {
        loadSports()
    }

    fun loadSports() {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, errorMessage = null, errorDetail = null) }
            when (val res = tempoApi.getSports()) {
                is NetworkResult.Success<List<SportDto>> -> {
                    _uiState.update {
                        it.copy(
                            sports = res.data,
                            isLoading = false
                        )
                    }
                }
                is NetworkResult.Error -> {
                    _uiState.update {
                        it.copy(
                            isLoading = false,
                            errorMessage = res.message ?: "Failed to load sports list.",
                            errorDetail = res.fullDetail
                        )
                    }
                }
                is NetworkResult.Loading -> Unit
            }
        }
    }

    fun onSportClicked(sport: SportDto) {
        if (!sport.analysis_ready) return
        val defaultSkill = sport.skills.firstOrNull { it.analysis_ready } ?: sport.skills.firstOrNull()
        _uiState.update {
            it.copy(
                selectedSport = sport,
                selectedSkill = defaultSkill,
                showSkillPicker = sport.skills.size > 1
            )
        }
    }

    fun onSkillSelected(skill: SportSkillDto) {
        if (!skill.analysis_ready) return
        _uiState.update { it.copy(selectedSkill = skill) }
    }

    fun dismissSkillPicker() {
        _uiState.update { it.copy(showSkillPicker = false) }
    }

    fun confirmSportAndSkill(onConfirmed: () -> Unit) {
        val sport = _uiState.value.selectedSport ?: return
        val skill = _uiState.value.selectedSkill

        viewModelScope.launch {
            _uiState.update { it.copy(isSaving = true, errorMessage = null, errorDetail = null) }

            val payload = ProfilePayloadDto(
                sport = sport.id,
                skill = skill?.id,
                level = "intermediate",
                goal = "technique_refinement",
                playstyle = "all_court",
                injuries = emptyList(),
                referencePlayer = null
            )

            // Save to backend
            when (val res = tempoApi.updateProfile(payload)) {
                is NetworkResult.Success<*> -> {
                    // Update local identity and room
                    identity.sport = sport.id
                    identity.skill = skill?.id

                    val currentProfile = userProfileRepository.getUserProfileOnce()
                    val updatedEntity = currentProfile?.copy(
                        sport = sport.id,
                        updatedAt = System.currentTimeMillis()
                    ) ?: UserProfileEntity(
                        userId = identity.userId,
                        sport = sport.id,
                        level = "intermediate",
                        goal = "technique_refinement",
                        playstyle = "all_court",
                        injuries = "none",
                        targetArchetype = "Standard Reference",
                        permissionsGranted = true,
                        updatedAt = System.currentTimeMillis()
                    )
                    userProfileRepository.saveUserProfile(updatedEntity)

                    _uiState.update { it.copy(isSaving = false, showSkillPicker = false) }
                    onConfirmed()
                }
                is NetworkResult.Error -> {
                    _uiState.update {
                        it.copy(
                            isSaving = false,
                            errorMessage = res.message ?: "Failed to save selected sport.",
                            errorDetail = res.fullDetail
                        )
                    }
                }
                is NetworkResult.Loading -> Unit
            }
        }
    }
}
