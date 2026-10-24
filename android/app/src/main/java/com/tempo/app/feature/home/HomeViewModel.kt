package com.tempo.app.feature.home

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.tempo.app.BuildConfig
import com.tempo.app.data.PlayerIdentity
import com.tempo.app.data.local.UserProfileEntity
import com.tempo.app.repository.UserProfileRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import javax.inject.Inject

data class DebugConfigState(
    val baseUrl: String = BuildConfig.BASE_URL,
    val isMockMode: Boolean = BuildConfig.USE_MOCK_API,
    val isTokenPresent: Boolean = false,
    val healthStatus: String = "Not checked yet",
    val userId: String = "user_1"
)

@HiltViewModel
class HomeViewModel @Inject constructor(
    private val userProfileRepository: UserProfileRepository,
    private val identity: PlayerIdentity,
    private val okHttpClient: OkHttpClient,
    @ApplicationContext private val context: Context
) : ViewModel() {

    private val prefs = context.getSharedPreferences("tempo_config", Context.MODE_PRIVATE)

    val userProfile: StateFlow<UserProfileEntity?> = userProfileRepository.getUserProfile()
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5000),
            initialValue = null
        )

    private val _debugState = MutableStateFlow(
        DebugConfigState(
            baseUrl = BuildConfig.BASE_URL,
            isMockMode = prefs.getBoolean("use_mock_api", BuildConfig.USE_MOCK_API),
            isTokenPresent = identity.accessToken.isNotBlank() || BuildConfig.TEMPO_DEBUG_TOKEN.isNotBlank(),
            healthStatus = "Ready to query",
            userId = identity.userId
        )
    )
    val debugState: StateFlow<DebugConfigState> = _debugState.asStateFlow()

    fun checkHealth() {
        viewModelScope.launch(Dispatchers.IO) {
            _debugState.update { it.copy(healthStatus = "Querying GET /health...") }
            try {
                val targetUrl = BuildConfig.BASE_URL.trimEnd('/') + "/health"
                val request = Request.Builder()
                    .url(targetUrl)
                    .get()
                    .build()
                val response = okHttpClient.newCall(request).execute()
                val body = response.body?.string() ?: ""
                val text = if (response.isSuccessful) {
                    "HTTP ${response.code} OK: $body"
                } else {
                    "HTTP ${response.code} Err: $body"
                }
                _debugState.update { it.copy(healthStatus = text) }
            } catch (e: Exception) {
                _debugState.update { it.copy(healthStatus = "Connection failed: ${e.localizedMessage ?: e.message}") }
            }
        }
    }

    fun setUseMockApi(useMock: Boolean) {
        prefs.edit().putBoolean("use_mock_api", useMock).apply()
        _debugState.update { it.copy(isMockMode = useMock) }
    }
}
