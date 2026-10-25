package com.tempo.app.feature.home

import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.tempo.app.BuildConfig
import com.tempo.app.data.PlayerIdentity
import com.tempo.app.data.local.SessionDao
import com.tempo.app.data.local.SessionEntity
import com.tempo.app.data.local.UserProfileDao
import com.tempo.app.data.local.UserProfileEntity
import com.tempo.app.feature.sdui.data.SduiRepository
import com.tempo.app.feature.sdui.data.WidgetParser
import com.tempo.app.feature.sdui.model.PathProgressWidget
import com.tempo.app.feature.sdui.model.Widget
import com.tempo.app.feature.sdui.model.WidgetAction
import com.tempo.app.network.TempoApi
import com.tempo.app.network.models.AiStatusDto
import com.tempo.app.network.models.CoachConverseRequestDto
import com.tempo.app.network.models.CoachMemoryHeaderDto
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
import java.util.UUID
import javax.inject.Inject

data class TheaMessage(
    val id: String = UUID.randomUUID().toString(),
    val sender: TheaSender,
    val text: String,
    val audioCueText: String? = null,
    val timestamp: Long = System.currentTimeMillis()
)

enum class TheaSender { THEA, ATHLETE }

data class CoachConversationState(
    val isThinking: Boolean = false,
    val messages: List<TheaMessage> = emptyList(),
    val activeWidgets: List<Widget> = emptyList(),
    val statusMessage: String? = null
)

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
    private val sduiRepository: SduiRepository,
    private val widgetParser: WidgetParser,
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

    private val _conversationState = MutableStateFlow(
        CoachConversationState(
            messages = listOf(
                TheaMessage(
                    sender = TheaSender.THEA,
                    text = "Welcome to your training studio! I'm Thea, your autonomous biomechanics coach powered by Gemini 4 Argon. I track your kinetic reach, joint extension, and fatigue index. What stroke or drill would you like to review today?",
                    audioCueText = "Maintain high contact apex."
                )
            ),
            activeWidgets = emptyList()
        )
    )
    val conversationState: StateFlow<CoachConversationState> = _conversationState.asStateFlow()

    private val _homeHeader = MutableStateFlow<CoachMemoryHeaderDto?>(null)
    val homeHeader: StateFlow<CoachMemoryHeaderDto?> = _homeHeader.asStateFlow()

    init {
        refreshFromMemory()
    }

    /**
     * Renders home from the shared athlete_memory (plan path, active drills, quiz) via
     * `GET /api/v1/coach/memory`; falls back to the latest session feed before onboarding.
     */
    fun refreshFromMemory(extraWidgets: List<Widget> = emptyList()) {
        viewModelScope.launch {
            val memory = try {
                tempoApi.getCoachMemory()
            } catch (_: Exception) {
                null
            }
            if (memory != null) _homeHeader.value = memory.header
            val memoryWidgets = memory?.widgets?.let(widgetParser::parse).orEmpty()
            if (memoryWidgets.isEmpty() && extraWidgets.isEmpty()) {
                loadLatestSessionWidgets()
                return@launch
            }
            val memoryKeys = memoryWidgets.map { it.key }.toSet()
            val extras = extraWidgets.filter { it !is PathProgressWidget && it.key !in memoryKeys }
            _conversationState.update { it.copy(activeWidgets = memoryWidgets + extras) }
        }
    }

    private fun loadLatestSessionWidgets() {
        viewModelScope.launch {
            val session = sessionDao.getLatestSession()
            if (session != null && session.sessionId.isNotBlank()) {
                when (val feed = sduiRepository.getFeed(session.sessionId)) {
                    is NetworkResult.Success -> {
                        if (feed.data.isNotEmpty()) {
                            _conversationState.update { current ->
                                current.copy(activeWidgets = feed.data)
                            }
                        }
                    }
                    else -> Unit
                }
            }
        }
    }

    fun sendMessage(text: String) {
        val trimmed = text.trim()
        if (trimmed.isBlank()) return

        val userMsg = TheaMessage(sender = TheaSender.ATHLETE, text = trimmed)
        _conversationState.update { current ->
            current.copy(
                messages = current.messages + userMsg,
                isThinking = true
            )
        }

        viewModelScope.launch {
            try {
                val activeSessionId = sessionDao.getLatestSession()?.sessionId
                val request = CoachConverseRequestDto(
                    userId = identity.userId.ifBlank { "user_1" },
                    message = trimmed,
                    sessionId = activeSessionId
                )
                val response = tempoApi.converseWithCoach(request)

                val theaMsg = TheaMessage(
                    sender = TheaSender.THEA,
                    text = response.replyText,
                    audioCueText = response.audioCueText
                )

                val newWidgets = if (response.dynamicWidgets.isNotEmpty()) {
                    widgetParser.parse(response.dynamicWidgets)
                } else null

                _conversationState.update { current ->
                    current.copy(
                        isThinking = false,
                        messages = current.messages + theaMsg
                    )
                }
                // Thea's tools mutate athlete_memory, so re-render home from it.
                refreshFromMemory(newWidgets.orEmpty())
            } catch (e: Exception) {
                val fallbackMsg = TheaMessage(
                    sender = TheaSender.THEA,
                    text = "I'm analyzing your technique. Keep your reach tall and maintain forearm pronation through contact."
                )
                _conversationState.update { current ->
                    current.copy(
                        isThinking = false,
                        messages = current.messages + fallbackMsg
                    )
                }
            }
        }
    }

    fun onWidgetAction(action: WidgetAction) {
        viewModelScope.launch {
            _conversationState.update { it.copy(statusMessage = "Syncing action with Thea...") }
            val activeSessionId = sessionDao.getLatestSession()?.sessionId.orEmpty().ifBlank { "home_session" }

            when (val res = sduiRepository.postAction(activeSessionId, action)) {
                is NetworkResult.Success -> {
                    _conversationState.update { current ->
                        current.copy(
                            activeWidgets = res.data,
                            statusMessage = null
                        )
                    }
                }
                is NetworkResult.Error -> {
                    _conversationState.update { it.copy(statusMessage = null) }
                }
                is NetworkResult.Loading -> Unit
            }
        }
    }

    /**
     * Saves [phoneNumber] on athlete_memory (so inbound WhatsApp messages resolve to this athlete),
     * then opens a chat with Thea. [onResult] gets null on success or a message to show.
     */
    fun linkAndOpenWhatsApp(context: Context, phoneNumber: String, onResult: (String?) -> Unit) {
        viewModelScope.launch {
            try {
                val linked = tempoApi.linkWhatsApp(com.tempo.app.network.models.WhatsAppLinkRequestDto(phoneNumber.trim()))
                onResult(null)
                openWhatsAppCadence(context, linked.prefillText)
            } catch (e: retrofit2.HttpException) {
                onResult(when (e.code()) {
                    409 -> "That number is already linked to another Tempo account."
                    422 -> "Use international format, e.g. +44 7700 900123."
                    else -> "Couldn't link WhatsApp (HTTP ${e.code()})."
                })
            } catch (e: Exception) {
                onResult("Couldn't reach Tempo. Check the connection and try again.")
            }
        }
    }

    fun openWhatsAppCadence(context: Context, customBrief: String? = null) {
        val theaNumber = BuildConfig.THEA_NUMBER.ifBlank { "4477985791437" }
        val brief = customBrief ?: "Hey Coach Thea! I'm reviewing my practice session debrief and setting my upcoming training cadence."
        val url = "https://wa.me/$theaNumber?text=" + Uri.encode(brief)
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url)).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK
        }
        try {
            context.startActivity(intent)
        } catch (_: Exception) {
            // WhatsApp client not installed, open in browser
            val webIntent = Intent(Intent.ACTION_VIEW, Uri.parse(url)).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK
            }
            context.startActivity(webIntent)
        }
    }

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
