package com.tempo.app.feature.thea

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.util.Log
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.ChatBubbleOutline
import androidx.compose.material.icons.rounded.Place
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import com.tempo.app.BuildConfig
import com.tempo.app.network.TempoApi
import com.tempo.app.network.models.CourtsResponseDto
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.CardBorderSubtle
import com.tempo.app.ui.theme.SurfaceCharcoal
import com.tempo.app.ui.theme.TextMuted
import com.tempo.app.ui.theme.TextPrimaryWhite
import com.tempo.app.ui.theme.TextSecondarySilver
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

private val WhatsAppGreen = Color(0xFF25D366)

@HiltViewModel
class TheaHandoffViewModel @Inject constructor(private val tempoApi: TempoApi) : ViewModel() {
    private val _busy = MutableStateFlow(false)
    val busy: StateFlow<Boolean> = _busy.asStateFlow()

    private val _courts = MutableStateFlow<CourtsResponseDto?>(null)
    val courts: StateFlow<CourtsResponseDto?> = _courts.asStateFlow()
    private val _courtsError = MutableStateFlow<String?>(null)
    val courtsError: StateFlow<String?> = _courtsError.asStateFlow()

    /** Open WhatsApp to Thea with the live Tempo context brief pre-filled (falls back to a plain hello). */
    fun continueOnWhatsApp(context: Context, question: String? = null) {
        viewModelScope.launch {
            _busy.value = true
            val number = BuildConfig.THEA_NUMBER.filter(Char::isDigit).ifBlank { "447985791437" }
            val text = try {
                tempoApi.getCoachBrief().briefText
            } catch (e: Exception) {
                Log.w("TheaHandoff", "Brief unavailable", e)
                "Hi Thea!"
            } + (question?.let { " $it" } ?: "")
            _busy.value = false
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse("https://wa.me/$number?text=" + Uri.encode(text)))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            runCatching { context.startActivity(intent) }
        }
    }

    fun loadCourts(lat: Double = CENTRAL_LONDON.first, lng: Double = CENTRAL_LONDON.second) {
        viewModelScope.launch {
            _courtsError.value = null
            _courts.value = try {
                tempoApi.getNearbyCourts(lat, lng)
            } catch (e: Exception) {
                _courtsError.value = "Couldn't load courts right now. Pull to refresh or ask Thea."
                null
            }
        }
    }

    companion object {
        val CENTRAL_LONDON = 51.5248 to -0.1328
    }
}

/** "Continue with Thea on WhatsApp": hands off with the athlete's live Tempo context brief. */
@Composable
fun ContinueWithTheaButton(
    modifier: Modifier = Modifier,
    question: String? = null,
    viewModel: TheaHandoffViewModel = hiltViewModel(),
) {
    val context = LocalContext.current
    val busy by viewModel.busy.collectAsStateWithLifecycle()
    OutlinedButton(
        onClick = { viewModel.continueOnWhatsApp(context, question) },
        enabled = !busy,
        modifier = modifier.fillMaxWidth().height(48.dp),
        shape = RoundedCornerShape(14.dp),
        border = BorderStroke(1.dp, WhatsAppGreen),
    ) {
        if (busy) {
            CircularProgressIndicator(Modifier.size(18.dp), color = WhatsAppGreen, strokeWidth = 2.dp)
        } else {
            Icon(Icons.Rounded.ChatBubbleOutline, contentDescription = null, tint = WhatsAppGreen)
            Spacer(Modifier.width(8.dp))
            Text("Continue with Thea on WhatsApp", color = TextPrimaryWhite, fontWeight = FontWeight.Bold)
        }
    }
}

/** Schedule tab: courts near you ($nearSphere) with Thea's play / move indoors / postpone call. */
@Composable
fun CourtFinderCard(modifier: Modifier = Modifier, viewModel: TheaHandoffViewModel = hiltViewModel()) {
    val courts by viewModel.courts.collectAsStateWithLifecycle()
    val error by viewModel.courtsError.collectAsStateWithLifecycle()
    val context = LocalContext.current
    LaunchedEffect(Unit) { viewModel.loadCourts() }
    Card(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
        border = BorderStroke(1.dp, CardBorderSubtle),
    ) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("COURTS NEAR YOU", style = MaterialTheme.typography.labelMedium.copy(fontWeight = FontWeight.Bold),
                color = AccentNeonVolt)
            courts?.playCall?.let { call ->
                Text(
                    when (call.decision) {
                        "play_outdoor" -> "Good to play outside"
                        "play_indoor" -> "Play indoors" + (call.venue?.let { " at $it" } ?: "")
                        "postpone" -> "Postpone the outdoor session"
                        else -> "Check the forecast"
                    },
                    style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.Bold), color = TextPrimaryWhite
                )
                Text(call.reason, style = MaterialTheme.typography.bodySmall, color = TextSecondarySilver)
            }
            when {
                error != null -> Text(error.orEmpty(), style = MaterialTheme.typography.bodySmall, color = TextMuted)
                courts == null -> CircularProgressIndicator(Modifier.size(22.dp), color = AccentNeonVolt, strokeWidth = 2.dp)
                courts!!.courts.isEmpty() -> Text("No courts found near central London.", color = TextMuted)
                else -> courts!!.courts.forEach { court ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Rounded.Place, contentDescription = null, tint = AccentNeonVolt, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(8.dp))
                        Column(Modifier.weight(1f)) {
                            Text(court.name, style = MaterialTheme.typography.bodyMedium, color = TextPrimaryWhite)
                            Text(
                                listOfNotNull(
                                    court.sports.joinToString(", ").ifBlank { null },
                                    when {
                                        court.indoor == true && court.outdoor == true -> "indoor + outdoor"
                                        court.indoor == true -> "indoor"
                                        court.outdoor == true -> "outdoor"
                                        else -> null
                                    },
                                    court.postcode,
                                ).joinToString(" · "),
                                style = MaterialTheme.typography.bodySmall, color = TextMuted
                            )
                        }
                        Text("%.1f km".format(court.distanceKm), style = MaterialTheme.typography.labelMedium, color = TextSecondarySilver)
                    }
                }
            }
            courts?.bookingNote?.let { Text(it, style = MaterialTheme.typography.labelSmall, color = TextMuted) }
            ContinueWithTheaButton(question = "Can you help me book a court for my next session?",
                modifier = Modifier.padding(top = 4.dp), viewModel = viewModel)
        }
    }
}
