package com.tempo.app.feature.saint

import androidx.lifecycle.ViewModel
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.viewModelScope
import com.tempo.app.data.PlayerIdentity
import com.tempo.app.network.models.NetworkResult
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

data class SaintUiState(
    val text: String = "", val preferences: SaintPreferences = SaintPreferences(),
    val busy: Boolean = false, val editingPreferences: Boolean = false,
    val question: String? = null, val proposal: SaintProposal? = null,
    val record: SaintActionRecord? = null, val message: String? = null,
    val decisionSubmitted: Boolean = false,
    val resultDescription: String? = null,
    val connectionOpen: Boolean = false, val playerInput: String = "", val tokenInput: String = ""
)

@HiltViewModel class SaintViewModel @Inject constructor(
    private val repository: SaintRepository, private val identity: PlayerIdentity,
    private val savedState: SavedStateHandle
): ViewModel() {
    private val restored=runCatching { savedState.get<String>("saint_proposal")?.let { Json.decodeFromString<SaintProposal>(it) } }.getOrNull()
    private val _state=MutableStateFlow(SaintUiState(proposal=restored,
        decisionSubmitted=restored != null && savedState.get<Boolean>("saint_decided")==true,
        playerInput=identity.playerId, connectionOpen=identity.accessToken.isBlank()))
    val state=_state.asStateFlow()
    private val user get()=identity.playerId
    init { if(identity.accessToken.isNotBlank()) loadPreferences() }
    fun connection() { if(!_state.value.busy) _state.update { it.copy(connectionOpen=!it.connectionOpen) } }
    fun playerInput(value: String) { _state.update { it.copy(playerInput=value.take(128)) } }
    fun tokenInput(value: String) { _state.update { it.copy(tokenInput=value.take(512)) } }
    fun connect() {
        if(_state.value.busy) return
        val player=_state.value.playerInput.trim()
        val token=_state.value.tokenInput.trim()
        if(!Regex("[a-z0-9][a-z0-9_-]{0,127}").matches(player) || token.length !in 32..512) {
            _state.update { it.copy(message="Enter a valid player ID and Tempo access token.") }; return
        }
        if(_state.value.decisionSubmitted && _state.value.record?.status !in listOf("executed_mock","declined")) {
            _state.update { it.copy(message="Resolve the pending action before changing player credentials.") }; return
        }
        identity.playerId=player
        identity.accessToken=token
        savedState.remove<String>("saint_proposal");savedState["saint_decided"]=false
        _state.value=SaintUiState(playerInput=player,message="Credential saved securely. Checking your connection…")
        loadPreferences()
    }
    fun text(value: String) { _state.update { it.copy(text=value.take(1000)) } }
    fun editPreferences() { if (!_state.value.busy) _state.update { it.copy(editingPreferences=!it.editingPreferences) } }
    fun preferences(value: SaintPreferences) { if (!_state.value.busy) _state.update { it.copy(preferences=value) } }
    private fun error(result: NetworkResult.Error) { _state.update { it.copy(busy=false,message=result.message ?: "Could not reach Saint's backend.") } }
    private fun loadPreferences() {
        _state.update { it.copy(busy=true) }
        viewModelScope.launch { when(val result=repository.preferences(user)) {
            is NetworkResult.Success -> _state.update { it.copy(busy=false,preferences=result.data.preferences) }
            is NetworkResult.Error -> error(result)
            NetworkResult.Loading -> Unit
        }
        if(_state.value.decisionSubmitted && !_state.value.busy) refreshStatus()
        }
    }
    fun savePreferences() {
        val prefs=_state.value.preferences
        if (_state.value.busy) return
        if (prefs.homeArea.isBlank() || !Regex("^(?:[01]\\d|2[0-3]):[0-5]\\d$").matches(prefs.preferredTime)) {
            _state.update { it.copy(message="Enter a home area and a 24-hour time, for example 09:00.") }; return
        }
        _state.update { it.copy(busy=true,message=null) }
        viewModelScope.launch { when(val result=repository.savePreferences(user,prefs)) {
            is NetworkResult.Success -> _state.update { it.copy(busy=false,editingPreferences=false,
                message=if(result.data.storageMode=="in_memory_demo") "Preferences saved for this server session only." else "Preferences saved.") }
            is NetworkResult.Error -> error(result)
            NetworkResult.Loading -> Unit
        } }
    }
    fun propose() {
        val text=_state.value.text.trim()
        if (_state.value.busy || text.isBlank()) return
        // Never discard an approval whose outcome is uncertain.
        if (_state.value.decisionSubmitted && _state.value.record?.status !in listOf("executed_mock","declined")) return
        savedState.remove<String>("saint_proposal");savedState["saint_decided"]=false
        _state.update { it.copy(busy=true,message=null,question=null,proposal=null,record=null,decisionSubmitted=false,resultDescription=null) }
        viewModelScope.launch { when(val result=repository.command(user,text)) {
            is NetworkResult.Success -> {
                result.data.proposal?.let { savedState["saint_proposal"]=Json.encodeToString(it) }
                _state.update { it.copy(busy=false,question=result.data.question,proposal=result.data.proposal) }
            }
            is NetworkResult.Error -> error(result)
            NetworkResult.Loading -> Unit
        } }
    }
    fun decide(approved: Boolean) {
        val proposal=_state.value.proposal ?: return
        if (_state.value.busy || _state.value.decisionSubmitted || !proposal.action.requiresApproval) return
        savedState["saint_decided"]=true; savedState["saint_approved"]=approved
        _state.update { it.copy(busy=true,message=null,decisionSubmitted=true) }
        viewModelScope.launch { when(val result=repository.decide(proposal,approved)) {
            is NetworkResult.Success -> showRecord(result.data)
            is NetworkResult.Error -> {
                if(result.code in listOf(400,410,422)) {
                    savedState.remove<String>("saint_proposal");savedState["saint_decided"]=false
                    _state.update { it.copy(busy=false,proposal=null,decisionSubmitted=false,message=result.message) }
                } else _state.update { it.copy(busy=false,message="${result.message} Use Check action status; do not submit a second booking.") }
            }
            NetworkResult.Loading -> Unit
        } }
    }
    fun refreshStatus() {
        val key=_state.value.proposal?.action?.idempotencyKey ?: return
        if (_state.value.busy) return
        _state.update { it.copy(busy=true,message=null) }
        viewModelScope.launch { when(val result=repository.action(key)) {
            is NetworkResult.Success -> showRecord(result.data)
            is NetworkResult.Error -> {
                _state.update { it.copy(busy=false,
                message=if(result.code==404) "No action is recorded yet. Retry the same decision; do not prepare another booking." else result.message) }
            }
            NetworkResult.Loading -> Unit
        } }
    }
    fun retryDecision() {
        if(_state.value.busy || !_state.value.decisionSubmitted || _state.value.record != null) return
        val approved=savedState.get<Boolean>("saint_approved") ?: return
        // Same signed proposal and idempotency key; never creates a second action.
        _state.update { it.copy(decisionSubmitted=false) }
        decide(approved)
    }
    private fun showRecord(record: SaintActionRecord) {
        val reference=(record.result?.get("booking_reference") as? JsonPrimitive)?.contentOrNull
        val description=when {
            reference!=null -> "Demo reference: $reference"
            record.status=="executed_mock" && record.action.type=="search_venues" -> "Demo venue found in your saved area. Availability and pricing are not verified."
            else -> null
        }
        _state.update { it.copy(busy=false,record=record,resultDescription=description) }
    }
}
