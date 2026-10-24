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

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    private val intentFlow = MutableSharedFlow<Intent>(extraBufferCapacity = 1)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        setContent {
            TempoTheme {
                val navController = rememberNavController()

                LaunchedEffect(Unit) {
                    handleIntent(intent, navController)
                    intentFlow.collect { newIntent ->
                        handleIntent(newIntent, navController)
                    }
                }

                Scaffold(
                    modifier = Modifier.fillMaxSize(),
                    containerColor = BackgroundOnyx,
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
