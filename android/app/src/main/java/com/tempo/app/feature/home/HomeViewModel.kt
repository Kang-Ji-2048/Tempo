package com.tempo.app.feature.home

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.tempo.app.BuildConfig
import com.tempo.app.data.PlayerIdentity
import com.tempo.app.data.local.SessionDao
import com.tempo.app.data.local.SessionEntity
import com.tempo.app.data.local.UserProfileDao
import com.tempo.app.data.local.UserProfileEntity
import com.tempo.app.network.TempoApi
import com.tempo.app.network.models.AiStatusDto
import com.tempo.app.network.models.NetworkResult
import com.tempo.app.repository.AuthRepository
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
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import javax.inject.Inject

data class DebugConfigState(
    val baseUrl: String = BuildConfig.BASE_URL,
    val isMockMode: Boolean = BuildConfig.USE_MOCK_API,
    val isTokenPresent: Boolean = false,
    val healthStatus: String = "Not checked yet",
    val healthLatencyMs: Long? = null,
    val aiStatus: AiStatusDto? = null,
    val isCheckingConnection: Boolean = false,
    val email: String = "",
    val userId: String = "user_1",
    val sport: String = ""
)

@HiltViewModel
class HomeViewModel @Inject constructor(
    private val userProfileRepository: UserProfileRepository,
    private val userProfileDao: UserProfileDao,
    private val sessionDao: SessionDao,
    private val authRepository: AuthRepository,
    private val tempoApi: TempoApi,
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

    val latestSession: StateFlow<SessionEntity?> = sessionDao.observeLatestSession()
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
            healthStatus = "Ready to test",
            email = identity.email.ifBlank { "Unregistered / Demo" },
            userId = identity.userId,
            sport = identity.sport ?: "Not selected"
        )
    )
    val debugState: StateFlow<DebugConfigState> = _debugState.asStateFlow()

    fun testConnection() {
        viewModelScope.launch {
            _debugState.update { it.copy(isCheckingConnection = true, healthStatus = "Testing /health...") }
            val startMs = System.currentTimeMillis()

            var healthMsg = "Failed"
            var latency: Long? = null
            withContext(Dispatchers.IO) {
                try {
                    val targetUrl = BuildConfig.BASE_URL.trimEnd('/') + "/health"
                    val request = Request.Builder().url(targetUrl).get().build()
                    val response = okHttpClient.newCall(request).execute()
                    latency = System.currentTimeMillis() - startMs
                    val body = response.body?.string().orEmpty()
                    healthMsg = if (response.isSuccessful) {
                        "HTTP ${response.code} OK (${latency}ms): $body"
                    } else {
                        "HTTP ${response.code} Err (${latency}ms): $body"
                    }
                } catch (e: Exception) {
                    healthMsg = "Connection failed (${System.currentTimeMillis() - startMs}ms): ${e.localizedMessage ?: e.message}"
                }
            }

            // Also query AI status
            var aiDto: AiStatusDto? = null
            when (val aiRes = tempoApi.getAiStatus()) {
                is NetworkResult.Success<*> -> {
                    aiDto = aiRes.data as? AiStatusDto
                }
                else -> Unit
            }

            _debugState.update {
                it.copy(
                    isCheckingConnection = false,
                    healthStatus = healthMsg,
                    healthLatencyMs = latency,
                    aiStatus = aiDto,
                    email = identity.email.ifBlank { "Unregistered / Demo" },
                    userId = identity.userId,
                    sport = identity.sport ?: "Not selected"
                )
            }
        }
    }

    fun logout(onLoggedOut: () -> Unit) {
        viewModelScope.launch {
            authRepository.logout()
            userProfileDao.clearAllProfiles()
            sessionDao.clearAll()
            prefs.edit().clear().apply()
            onLoggedOut()
        }
    }

    fun setUseMockApi(useMock: Boolean) {
        prefs.edit().putBoolean("use_mock_api", useMock).apply()
        _debugState.update { it.copy(isMockMode = useMock) }
    }
}
