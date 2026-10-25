package com.tempo.app.feature.sports

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.tempo.app.data.PlayerIdentity
import com.tempo.app.data.local.UserProfileEntity
import com.tempo.app.network.TempoApi
import com.tempo.app.network.models.ProfilePayloadDto
import com.tempo.app.network.models.SportDto
import com.tempo.app.network.models.SportSkillDto
import com.tempo.app.repository.UserProfileRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeout
import android.util.Log
import kotlinx.serialization.SerializationException
import retrofit2.HttpException
import java.io.IOException
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
            // TempoApi.getSports() returns the list directly and throws on failure; never leave the spinner up.
            val sports = try {
                withTimeout(SPORTS_TIMEOUT_MS) { tempoApi.getSports() }.takeIf { it.isNotEmpty() }
            } catch (e: CancellationException) {
                if (e !is TimeoutCancellationException) throw e
                null
            } catch (e: Exception) {
                Log.w(TAG, "GET /api/v1/sports failed; using the built-in catalog", e)
                null
            }
            _uiState.update {
                if (sports != null) {
                    it.copy(sports = sports, isLoading = false)
                } else {
                    it.copy(
                        sports = FALLBACK_SPORTS,
                        isLoading = false,
                        errorMessage = "Couldn't reach Tempo, showing the built-in sports list.",
                        errorDetail = "Check the connection (adb reverse tcp:8000 tcp:8000) and tap Retry."
                    )
                }
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

            // Save to backend (updateProfile returns the body directly and throws on HTTP/network errors)
            val saveError: String? = try {
                withTimeout(SAVE_TIMEOUT_MS) { tempoApi.updateProfile(payload) }
                null
            } catch (e: CancellationException) {
                if (e !is TimeoutCancellationException) throw e
                "Saving your sport timed out."
            } catch (e: HttpException) {
                "Couldn't save your sport (HTTP ${e.code()})."
            } catch (e: SerializationException) {
                // The server answered but the body didn't match ProfileUpdateResponseDto: not a network problem.
                Log.e(TAG, "POST /api/v1/profile response did not decode", e)
                "Tempo saved your sport but sent an unexpected reply. Update the app."
            } catch (e: IOException) {
                Log.w(TAG, "POST /api/v1/profile failed", e)
                "Couldn't reach Tempo to save your sport."
            } catch (e: Exception) {
                Log.e(TAG, "POST /api/v1/profile failed", e)
                "Couldn't save your sport (${e.javaClass.simpleName})."
            }
            when (saveError) {
                null -> {
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
                else -> {
                    _uiState.update {
                        it.copy(isSaving = false, errorMessage = saveError, errorDetail = "Check the connection and try again.")
                    }
                }
            }
        }
    }

    companion object {
        private const val TAG = "SportSelection"
        private const val SPORTS_TIMEOUT_MS = 3_000L
        private const val SAVE_TIMEOUT_MS = 10_000L

        /** Mirrors backend/sports_config.py so the picker always renders, even offline. */
        val FALLBACK_SPORTS = listOf(
            SportDto("badminton", "Badminton", "badminton_shuttle", true, listOf(
                SportSkillDto("overhead_clear", "Overhead Clear", true), SportSkillDto("jump_smash", "Jump Smash", false))),
            SportDto("tennis", "Tennis", "tennis_ball", true, listOf(
                SportSkillDto("forehand", "Modern Forehand", true), SportSkillDto("one_hand_backhand", "One-Handed Backhand", true))),
            SportDto("padel", "Padel", "padel_racket", false, listOf(
                SportSkillDto("bandeja", "Bandeja", false), SportSkillDto("vibora", "Vibora", false))),
            SportDto("pickleball", "Pickleball", "pickleball_paddle", false, listOf(
                SportSkillDto("kitchen_dink", "Kitchen Line Dink", false), SportSkillDto("third_shot_drop", "Third Shot Drop", false))),
            SportDto("squash", "Squash", "squash_ball", false, listOf(SportSkillDto("straight_drive", "Rail / Straight Drive", false))),
            SportDto("table_tennis", "Table Tennis", "table_tennis_paddle", false,
                listOf(SportSkillDto("forehand_loop", "Forehand Topspin Loop", false))),
            SportDto("golf", "Golf", "golf_tee", false, listOf(SportSkillDto("driver_swing", "Driver Full Swing", false))),
        )
    }
}
