package com.tempo.app.feature.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.tempo.app.BuildConfig
import com.tempo.app.network.models.NetworkResult
import com.tempo.app.repository.AuthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class AuthUiState(
    val email: String = "",
    val password: String = "",
    val displayName: String = "",
    val isPasswordVisible: Boolean = false,
    val isLoading: Boolean = false,
    val errorMessage: String? = null,
    val errorDetail: String? = null,
    val isRegistered: Boolean = false
)

@HiltViewModel
class AuthViewModel @Inject constructor(
    private val authRepository: AuthRepository
) : ViewModel() {

    private val _uiState = MutableStateFlow(AuthUiState())
    val uiState: StateFlow<AuthUiState> = _uiState.asStateFlow()

    fun updateEmail(email: String) {
        _uiState.update { it.copy(email = email, errorMessage = null) }
    }

    fun updatePassword(password: String) {
        _uiState.update { it.copy(password = password, errorMessage = null) }
    }

    fun updateDisplayName(name: String) {
        _uiState.update { it.copy(displayName = name, errorMessage = null) }
    }

    fun togglePasswordVisibility() {
        _uiState.update { it.copy(isPasswordVisible = !it.isPasswordVisible) }
    }

    fun resetLocalState(onReset: () -> Unit) {
        viewModelScope.launch {
            authRepository.clearLocalState()
            _uiState.value = AuthUiState()
            onReset()
        }
    }

    fun fillDemoAccount() {
        if (BuildConfig.DEBUG) {
            _uiState.update {
                it.copy(
                    email = "demo@tempo.app",
                    password = "TempoDemo2026!",
                    displayName = "Tempo Demo Athlete",
                    errorMessage = null
                )
            }
        }
    }

    fun login(onSuccess: (hasSport: Boolean) -> Unit) {
        val email = _uiState.value.email.trim()
        val password = _uiState.value.password
        if (email.isBlank() || password.isBlank()) {
            _uiState.update { it.copy(errorMessage = "Please enter both email and password") }
            return
        }

        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, errorMessage = null, errorDetail = null) }
            when (val res = authRepository.login(email, password)) {
                is NetworkResult.Success<*> -> {
                    // Check profile to see if sport is selected
                    val profileRes = authRepository.getMe()
                    val hasSport = (profileRes as? NetworkResult.Success<*>)?.data is com.tempo.app.network.models.UserProfileDto &&
                            (profileRes.data as com.tempo.app.network.models.UserProfileDto).sport.isNotBlank()
                    _uiState.update { it.copy(isLoading = false) }
                    onSuccess(hasSport)
                }
                is NetworkResult.Error -> {
                    _uiState.update {
                        it.copy(
                            isLoading = false,
                            errorMessage = res.message ?: "Sign in failed.",
                            errorDetail = res.fullDetail
                        )
                    }
                }
                is NetworkResult.Loading -> Unit
            }
        }
    }

    fun register(onSuccess: () -> Unit) {
        val email = _uiState.value.email.trim()
        val password = _uiState.value.password
        val name = _uiState.value.displayName.trim()

        if (name.isBlank()) {
            _uiState.update { it.copy(errorMessage = "Please enter your name") }
            return
        }
        if (email.isBlank()) {
            _uiState.update { it.copy(errorMessage = "Please enter your email") }
            return
        }
        if (password.length < 8) {
            _uiState.update { it.copy(errorMessage = "Password must be at least 8 characters") }
            return
        }

        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, errorMessage = null, errorDetail = null) }
            when (val res = authRepository.register(email, password, name)) {
                is NetworkResult.Success<*> -> {
                    _uiState.update { it.copy(isLoading = false, isRegistered = true) }
                    onSuccess()
                }
                is NetworkResult.Error -> {
                    _uiState.update {
                        it.copy(
                            isLoading = false,
                            errorMessage = res.message ?: "Registration failed.",
                            errorDetail = res.fullDetail
                        )
                    }
                }
                is NetworkResult.Loading -> Unit
            }
        }
    }
}
