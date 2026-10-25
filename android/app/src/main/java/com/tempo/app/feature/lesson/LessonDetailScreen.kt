package com.tempo.app.feature.lesson

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.Videocam
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.navigation.NavController
import com.tempo.app.network.TempoApi
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.CardBorderSubtle
import com.tempo.app.ui.theme.SurfaceCharcoal
import com.tempo.app.ui.theme.SurfaceVariantDark
import com.tempo.app.ui.theme.TextMuted
import com.tempo.app.ui.theme.TextPrimaryWhite
import com.tempo.app.ui.theme.TextSecondarySilver
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import javax.inject.Inject

/** Routes for the lesson flow: Home path node -> lesson -> capture preset for that lesson. */
object LessonRoutes {
    const val LESSON_PATTERN = "lesson/{nodeId}"
    const val CAPTURE_PATTERN = "lesson_capture?lesson_node={lesson_node}&lesson_title={lesson_title}&framing={framing}"

    fun lesson(nodeId: String) = "lesson/${Uri.encode(nodeId)}"

    fun capture(nodeId: String, title: String, framing: String) =
        "lesson_capture?lesson_node=${Uri.encode(nodeId)}&lesson_title=${Uri.encode(title)}&framing=${Uri.encode(framing)}"
}

data class LessonDrill(val title: String, val instruction: String, val targetReps: Int, val focusCue: String)

data class LessonNodeUi(
    val id: String,
    val title: String,
    val status: String,
    val youtubeUrl: String?,
    val tips: List<String>,
    val drill: LessonDrill?,
    val attempts: Int,
    val hasRemedial: Boolean,
) {
    val isActive: Boolean get() = status.equals("active", ignoreCase = true)
    val isCompleted: Boolean get() = status.equals("completed", ignoreCase = true)

    /** Phase tip ("Phases: A -> B") as ordered steps, else the drill instruction split into sentences. */
    val steps: List<String>
        get() {
            val phases = tips.firstOrNull { it.startsWith("Phases:") }
                ?.removePrefix("Phases:")?.split("->")?.map { it.trim() }?.filter { it.isNotEmpty() }
            if (!phases.isNullOrEmpty()) {
                return phases.mapIndexed { i, phase -> stepCopy(phase, i == phases.lastIndex) }
            }
            return drill?.instruction?.split(Regex("(?<=[.!?])\\s+"))?.map { it.trim() }?.filter { it.isNotEmpty() }
                ?: emptyList()
        }

    val coachingTips: List<String>
        get() = tips.filterNot { it.startsWith("Phases:") } + listOfNotNull(drill?.focusCue?.takeIf { it !in tips })

    /** What the capture screen should tell the athlete before they film this lesson. */
    val framing: String
        get() = drill?.let { "${it.instruction} Aim for ${it.targetReps} reps." }
            ?: "Film your ${title.substringBefore(":")} from the side, full body in frame, 3m back."

    private fun stepCopy(phase: String, last: Boolean): String = when {
        phase.contains("Prep", true) || phase.contains("Turn", true) -> "$phase: get side-on early with the racket up."
        phase.contains("Load", true) || phase.contains("Lag", true) || phase.contains("Drop", true) ->
            "$phase: coil the trunk and let the racket drop behind you."
        phase.contains("Impact", true) || phase.contains("Contact", true) || phase.contains("Drive", true) ->
            "$phase: reach to full extension and hit at the highest point you can."
        last -> "$phase: let the racket finish across your body and recover to base."
        else -> phase
    }
}

data class LessonUiState(
    val isLoading: Boolean = true,
    val node: LessonNodeUi? = null,
    val sport: String? = null,
    val level: String? = null,
    val errorMessage: String? = null,
)

@HiltViewModel
class LessonDetailViewModel @Inject constructor(
    private val tempoApi: TempoApi,
    savedStateHandle: SavedStateHandle,
) : ViewModel() {
    private val nodeId: String = savedStateHandle.get<String>("nodeId").orEmpty()
    private val _uiState = MutableStateFlow(LessonUiState())
    val uiState: StateFlow<LessonUiState> = _uiState.asStateFlow()

    init { load() }

    fun load() {
        viewModelScope.launch {
            _uiState.value = LessonUiState(isLoading = true)
            _uiState.value = try {
                val memory = tempoApi.getCoachMemory().athleteMemory
                val node = (memory?.get("curriculum_nodes") as? JsonArray)
                    ?.mapNotNull { it as? JsonObject }
                    ?.firstOrNull { it.text("id") == nodeId }
                    ?.let(::parseNode)
                LessonUiState(
                    isLoading = false, node = node, sport = memory?.text("sport"), level = memory?.text("level"),
                    errorMessage = if (node == null) "This lesson is no longer in your plan." else null,
                )
            } catch (e: Exception) {
                LessonUiState(isLoading = false, errorMessage = "Couldn't load your lesson. Check the connection and retry.")
            }
        }
    }

    private fun parseNode(obj: JsonObject): LessonNodeUi {
        val drill = (obj["drill_spec"] as? JsonObject)?.let {
            LessonDrill(it.text("title").orEmpty(), it.text("instruction").orEmpty(),
                (it["target_reps"] as? JsonPrimitive)?.intOrNull ?: 10, it.text("focus_cue").orEmpty())
        }
        return LessonNodeUi(
            id = obj.text("id").orEmpty(), title = obj.text("title").orEmpty(), status = obj.text("status") ?: "locked",
            youtubeUrl = obj.text("youtube_url"),
            tips = (obj["tips"] as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.contentOrNull }.orEmpty(),
            drill = drill, attempts = (obj["attempts"] as? JsonPrimitive)?.intOrNull ?: 0,
            hasRemedial = obj["remedial_quiz"] is JsonObject,
        )
    }

    private fun JsonObject.text(key: String): String? = (this[key] as? JsonPrimitive)?.contentOrNull
}

@Composable
fun LessonDetailScreen(
    navController: NavController,
    modifier: Modifier = Modifier,
    viewModel: LessonDetailViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val context = LocalContext.current

    LazyColumn(
        modifier = modifier.fillMaxSize().background(BackgroundOnyx).padding(horizontal = 20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item {
            Spacer(Modifier.height(24.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton(
                    onClick = { navController.popBackStack() },
                    modifier = Modifier.size(40.dp).clip(CircleShape).background(SurfaceCharcoal),
                ) {
                    Icon(Icons.AutoMirrored.Rounded.ArrowBack, contentDescription = "Back", tint = TextPrimaryWhite)
                }
                Spacer(Modifier.width(12.dp))
                Text(
                    text = listOfNotNull(state.sport, state.level).joinToString(" • ") { it.replaceFirstChar(Char::uppercase) }
                        .ifBlank { "Lesson" }.uppercase(),
                    style = MaterialTheme.typography.labelLarge.copy(letterSpacing = 1.2.sp),
                    color = AccentNeonVolt,
                )
            }
        }

        val node = state.node
        when {
            state.isLoading -> item {
                Box(Modifier.fillMaxWidth().height(240.dp), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = AccentNeonVolt)
                }
            }
            node == null -> item {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(state.errorMessage.orEmpty(), color = TextSecondarySilver)
                    Button(onClick = viewModel::load) { Text("Retry") }
                }
            }
            else -> {
                item { LessonHeader(node) }
                if (node.steps.isNotEmpty()) item { StepsCard(node.steps) }
                item {
                    ReferenceVideoCard(node) {
                        node.youtubeUrl?.let { url ->
                            context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                        }
                    }
                }
                if (node.coachingTips.isNotEmpty()) item { TipsCard(node.coachingTips) }
                item {
                    Button(
                        onClick = { navController.navigate(LessonRoutes.capture(node.id, node.title, node.framing)) },
                        enabled = node.isActive,
                        modifier = Modifier.fillMaxWidth().height(56.dp),
                        shape = RoundedCornerShape(16.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = AccentNeonVolt, contentColor = BackgroundOnyx),
                    ) {
                        Icon(Icons.Rounded.Videocam, contentDescription = null)
                        Spacer(Modifier.width(8.dp))
                        Text(
                            if (node.isCompleted) "Lesson complete" else "Record & Analyze My Swing",
                            fontWeight = FontWeight.Bold,
                        )
                    }
                    Text(
                        text = when {
                            node.isCompleted -> "You passed this lesson. Your active lesson is next on the path."
                            node.hasRemedial -> "Attempt ${node.attempts}: finish the remedial drill on Home, then record again. Score 80+ to unlock the next lesson."
                            else -> "Score 80+ on your recorded swing to complete this lesson and unlock the next one."
                        },
                        style = MaterialTheme.typography.bodySmall,
                        color = TextMuted,
                        modifier = Modifier.padding(top = 8.dp),
                    )
                    Spacer(Modifier.height(32.dp))
                }
            }
        }
    }
}

@Composable
private fun LessonHeader(node: LessonNodeUi) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Surface(
            shape = RoundedCornerShape(8.dp),
            color = AccentNeonVolt.copy(alpha = 0.15f),
            border = BorderStroke(1.dp, AccentNeonVolt.copy(alpha = 0.5f)),
        ) {
            Text(
                text = node.status.uppercase(),
                style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Bold),
                color = AccentNeonVolt,
                modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp),
            )
        }
        Text(node.title, style = MaterialTheme.typography.headlineSmall.copy(fontWeight = FontWeight.Bold), color = TextPrimaryWhite)
        node.drill?.let {
            Text("${it.targetReps} reps • Cue: ${it.focusCue}", style = MaterialTheme.typography.bodyMedium, color = TextSecondarySilver)
        }
    }
}

@Composable
private fun LessonCard(title: String, content: @Composable () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        colors = CardDefaults.cardColors(containerColor = SurfaceCharcoal),
        border = BorderStroke(1.dp, CardBorderSubtle),
    ) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(
                title,
                style = MaterialTheme.typography.labelMedium.copy(fontWeight = FontWeight.Bold, letterSpacing = 1.sp),
                color = AccentNeonVolt,
            )
            content()
        }
    }
}

@Composable
private fun StepsCard(steps: List<String>) {
    LessonCard("HOW IT WORKS") {
        steps.forEachIndexed { i, step ->
            Row(verticalAlignment = Alignment.Top) {
                Box(
                    modifier = Modifier.size(26.dp).clip(CircleShape).background(SurfaceVariantDark),
                    contentAlignment = Alignment.Center,
                ) {
                    Text("${i + 1}", style = MaterialTheme.typography.labelMedium, color = AccentNeonVolt, fontWeight = FontWeight.Bold)
                }
                Spacer(Modifier.width(12.dp))
                Text(step, style = MaterialTheme.typography.bodyMedium, color = TextPrimaryWhite, modifier = Modifier.padding(top = 3.dp))
            }
        }
    }
}

@Composable
private fun ReferenceVideoCard(node: LessonNodeUi, onOpen: () -> Unit) {
    LessonCard("REFERENCE VIDEO") {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .aspectRatio(16f / 9f)
                .clip(RoundedCornerShape(14.dp))
                .background(Brush.linearGradient(listOf(SurfaceVariantDark, Color(0xFF1B1B1B), AccentNeonVolt.copy(alpha = 0.25f))))
                .clickable(enabled = node.youtubeUrl != null, onClick = onOpen),
            contentAlignment = Alignment.Center,
        ) {
            Box(
                modifier = Modifier.size(64.dp).clip(CircleShape).background(Color(0xFFFF0033)),
                contentAlignment = Alignment.Center,
            ) {
                Icon(Icons.Rounded.PlayArrow, contentDescription = "Open tutorial", tint = Color.White, modifier = Modifier.size(36.dp))
            }
            Text(
                text = node.title,
                style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.Bold),
                color = TextPrimaryWhite,
                modifier = Modifier.align(Alignment.BottomStart).padding(12.dp),
            )
        }
        Text(
            if (node.youtubeUrl != null) "Opens YouTube tutorials for this exact skill." else "No tutorial link for this lesson yet.",
            style = MaterialTheme.typography.bodySmall,
            color = TextMuted,
        )
    }
}

@Composable
private fun TipsCard(tips: List<String>) {
    LessonCard("KEY COACHING TIPS") {
        tips.forEach { tip ->
            Row(verticalAlignment = Alignment.Top) {
                Icon(Icons.Rounded.CheckCircle, contentDescription = null, tint = AccentNeonVolt, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(10.dp))
                Text(tip, style = MaterialTheme.typography.bodyMedium, color = TextSecondarySilver)
            }
        }
    }
}
