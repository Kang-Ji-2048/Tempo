package com.tempo.app

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Modifier
import androidx.navigation.NavController
import androidx.navigation.compose.rememberNavController
import com.tempo.app.service.TempoFirebaseMessagingService
import com.tempo.app.ui.components.TempoBottomBar
import com.tempo.app.ui.navigation.Screen
import com.tempo.app.ui.navigation.TempoNavGraph
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.TempoTheme
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.flow.MutableSharedFlow
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.tempo.app.data.AuthBannerNotifier
import com.tempo.app.ui.theme.TextPrimaryWhite
import javax.inject.Inject

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    @Inject
    lateinit var authBannerNotifier: AuthBannerNotifier

    private val intentFlow = MutableSharedFlow<Intent>(extraBufferCapacity = 1)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        setContent {
            TempoTheme {
                val navController = rememberNavController()
                val showAuthBanner by authBannerNotifier.showUnauthorizedBanner.collectAsStateWithLifecycle(initialValue = false)

                LaunchedEffect(Unit) {
                    handleIntent(intent, navController)
                    intentFlow.collect { newIntent ->
                        handleIntent(newIntent, navController)
                    }
                }

                Scaffold(
                    modifier = Modifier.fillMaxSize(),
                    containerColor = BackgroundOnyx,
                    topBar = {
                        if (showAuthBanner) {
                            Surface(
                                color = Color(0xFFB00020),
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .statusBarsPadding()
                            ) {
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(horizontal = 16.dp, vertical = 10.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.SpaceBetween
                                ) {
                                    Text(
                                        text = "Backend rejected the token, check local.properties",
                                        color = TextPrimaryWhite,
                                        style = MaterialTheme.typography.bodyMedium,
                                        modifier = Modifier.weight(1f)
                                    )
                                    IconButton(onClick = { authBannerNotifier.dismiss() }) {
                                        Icon(
                                            imageVector = Icons.Default.Close,
                                            contentDescription = "Dismiss",
                                            tint = TextPrimaryWhite
                                        )
                                    }
                                }
                            }
                        }
                    },
                    bottomBar = {
                        TempoBottomBar(navController = navController)
                    }
                ) { innerPadding ->
                    TempoNavGraph(
                        navController = navController,
                        modifier = Modifier.padding(innerPadding)
                    )
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        intentFlow.tryEmit(intent)
    }

    private fun handleIntent(intent: Intent?, navController: NavController) {
        if (intent == null) return

        // 1. If explicit data URI is present, let NavController process deep link
        val data = intent.data
        if (data != null) {
            navController.handleDeepLink(intent)
            return
        }

        // 2. Otherwise inspect intent extras (from FCM or notifications)
        val target = intent.getStringExtra(TempoFirebaseMessagingService.EXTRA_SCREEN_TARGET)
        val sessionId = intent.getStringExtra(TempoFirebaseMessagingService.EXTRA_SESSION_ID)

        when {
            target.equals("analysis", ignoreCase = true) && !sessionId.isNullOrBlank() -> {
                navController.navigate(Screen.Analysis.createRoute(sessionId)) {
                    launchSingleTop = true
                }
            }
            target.equals("capture", ignoreCase = true) -> {
                navController.navigate(Screen.Capture.route) {
                    launchSingleTop = true
                }
            }
            target.equals("schedule", ignoreCase = true) -> {
                navController.navigate(Screen.Schedule.route) {
                    launchSingleTop = true
                }
            }
        }
    }
}
