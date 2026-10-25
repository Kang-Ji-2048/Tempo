package com.tempo.app.feature.saint

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import com.tempo.app.ui.theme.*

@Composable fun SaintScreen(navController: NavController, viewModel: SaintViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    Column(Modifier.fillMaxSize().background(BackgroundOnyx).verticalScroll(rememberScrollState()).imePadding().padding(24.dp),
        verticalArrangement=Arrangement.spacedBy(16.dp)) {
        TextButton(onClick={navController.popBackStack()}) { Text("← Back",color=TextSecondarySilver) }
        Text("PLAN WITH SAINT",color=AccentNeonVolt,style=MaterialTheme.typography.labelSmall)
        Text("Plan your next session",style=MaterialTheme.typography.displayLarge)
        Text("Plan your next practice, then review each action before it runs. Court bookings are simulated in this demo.",color=TextSecondarySilver)
        OutlinedButton(onClick=viewModel::connection,enabled=!state.busy,modifier=Modifier.fillMaxWidth()) {
            Text("Connect to Tempo",color=AccentNeonVolt)
        }
        if(state.connectionOpen) {
            Text("Use your Tempo player ID and backend access token. This is separate from your Watch receiver key.",color=TextSecondarySilver)
            OutlinedTextField(value=state.playerInput,onValueChange=viewModel::playerInput,
                label={Text("Player ID")},singleLine=true,enabled=!state.busy,modifier=Modifier.fillMaxWidth())
            OutlinedTextField(value=state.tokenInput,onValueChange=viewModel::tokenInput,
                label={Text("Tempo access token")},singleLine=true,enabled=!state.busy,
                visualTransformation=androidx.compose.ui.text.input.PasswordVisualTransformation(),
                keyboardOptions=androidx.compose.foundation.text.KeyboardOptions(
                    keyboardType=androidx.compose.ui.text.input.KeyboardType.Password),modifier=Modifier.fillMaxWidth())
            Button(onClick=viewModel::connect,enabled=!state.busy,modifier=Modifier.fillMaxWidth()) { Text("Save & connect") }
        }
        OutlinedButton(onClick=viewModel::editPreferences,enabled=!state.busy,modifier=Modifier.fillMaxWidth()) {
            Text(if(state.editingPreferences) "Close preferences" else "Practice preferences",color=AccentNeonVolt)
        }
        if(state.editingPreferences) {
            OutlinedTextField(value=state.preferences.homeArea,onValueChange={viewModel.preferences(state.preferences.copy(homeArea=it.take(120)))},label={Text("Home area")},enabled=!state.busy,modifier=Modifier.fillMaxWidth())
            OutlinedTextField(value=state.preferences.preferredTime,onValueChange={viewModel.preferences(state.preferences.copy(preferredTime=it.take(5)))},label={Text("Preferred time · Europe/London · HH:mm")},enabled=!state.busy,modifier=Modifier.fillMaxWidth())
            Text("Sport",color=TextSecondarySilver)
            Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                listOf("badminton","tennis").forEach { value -> FilterChip(selected=state.preferences.sport==value,onClick={viewModel.preferences(state.preferences.copy(sport=value))},label={Text(value)},enabled=!state.busy) }
            }
            Text("Level",color=TextSecondarySilver)
            Column {
                listOf("beginner","intermediate","advanced").forEach { value -> FilterChip(selected=state.preferences.level==value,onClick={viewModel.preferences(state.preferences.copy(level=value))},label={Text(value)},enabled=!state.busy) }
            }
            Button(onClick=viewModel::savePreferences,enabled=!state.busy) { Text("Save preferences") }
        }
        OutlinedTextField(value=state.text,onValueChange=viewModel::text,label={Text("Ask Saint")},
            placeholder={Text("Book me an indoor court Saturday morning",color=TextSecondarySilver)},
            textStyle=MaterialTheme.typography.bodyLarge.copy(color=TextPrimaryWhite),
            colors=OutlinedTextFieldDefaults.colors(focusedTextColor=TextPrimaryWhite,
                unfocusedTextColor=TextPrimaryWhite,cursorColor=AccentNeonVolt),
            minLines=3,modifier=Modifier.fillMaxWidth())
        Button(onClick=viewModel::propose,enabled=!state.busy && state.text.isNotBlank() && (!state.decisionSubmitted || state.record?.status in listOf("executed_mock","declined")),
            modifier=Modifier.fillMaxWidth(),colors=ButtonDefaults.buttonColors(containerColor=AccentNeonVolt,contentColor=BackgroundOnyx)) { Text("Prepare proposal") }
        if(state.busy) Text("Working through your request…",color=TextSecondarySilver)
        state.question?.let { Text(it,color=TextPrimaryWhite) }
        state.proposal?.let { proposal ->
            Card(colors=CardDefaults.cardColors(containerColor=SurfaceCharcoal),border=BorderStroke(1.dp,CardBorderSubtle)) {
                Column(Modifier.padding(20.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
                    Text("REVIEW PROPOSED ACTION",color=AccentNeonVolt,style=MaterialTheme.typography.labelSmall)
                    Text(proposal.action.summary,color=TextPrimaryWhite)
                    Text("Nothing is executed until you approve. This proposal expires after 15 minutes.",color=TextSecondarySilver)
                    if(!state.decisionSubmitted) {
                        Button(onClick={viewModel.decide(true)},enabled=!state.busy && proposal.action.requiresApproval) { Text("Approve mock action") }
                        OutlinedButton(onClick={viewModel.decide(false)},enabled=!state.busy) { Text("Decline") }
                    } else {
                        OutlinedButton(onClick=viewModel::refreshStatus,enabled=!state.busy) { Text("Check action status") }
                        if(state.record==null) OutlinedButton(onClick=viewModel::retryDecision,enabled=!state.busy) { Text("Retry same decision") }
                    }
                }
            }
        }
        state.record?.let { record ->
            Text(when(record.status) {
                "executed_mock" -> "Mock action completed. No real reservation or payment was made."
                "declined" -> "Declined. No venue action was executed."
                "processing" -> "Action is processing. Check its status before doing anything else."
                else -> "Outcome needs review. This action will not be retried automatically."
            },color=AccentNeonVolt)
            state.resultDescription?.let { Text(it,color=TextSecondarySilver,style=MaterialTheme.typography.bodySmall) }
            if(record.storageMode=="in_memory_demo") Text("Action log is temporary: database is offline.",color=WarningAmber)
        }
        state.message?.let { Text(it,color=TextSecondarySilver) }
        Spacer(Modifier.height(24.dp))
    }
}
