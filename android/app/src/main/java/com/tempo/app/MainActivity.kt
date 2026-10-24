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
import androidx.compose.foundation.layout.Column
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.tempo.app.data.AuthBannerNotifier
import com.tempo.app.ui.theme.TextPrimaryWhite
import javax.inject.Inject

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    @Inject
    lateinit var authBannerNotifier: AuthBannerNotifier

    @Inject
    lateinit var authRepository: com.tempo.app.repository.AuthRepository

    @Inject
    lateinit var playerIdentity: com.tempo.app.data.PlayerIdentity

    private val intentFlow = MutableSharedFlow<Intent>(extraBufferCapacity = 1)

    private fun isEmulator(): Boolean {
        val fp = android.os.Build.FINGERPRINT.lowercase()
        val model = android.os.Build.MODEL.lowercase()
        val hw = android.os.Build.HARDWARE.lowercase()
        val mfg = android.os.Build.MANUFACTURER.lowercase()
        val product = android.os.Build.PRODUCT.lowercase()
        return fp.startsWith("generic") || fp.startsWith("unknown") ||
                model.contains("google_sdk") || model.contains("emulator") || model.contains("android sdk built for x86") ||
                mfg.contains("genymotion") || hw.contains("goldfish") || hw.contains("ranchu") ||
                product.contains("sdk") || product.contains("emulator") || product.contains("simulator")
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        val isPhysicalPhone = !isEmulator()
        val isBaseUrlEmulator = BuildConfig.BASE_URL.contains("10.0.2.2")
        val showConnectivityWarning = isPhysicalPhone && isBaseUrlEmulator

        setContent {
            TempoTheme {
                val navController = rememberNavController()
                val showUnauthorized by authBannerNotifier.showUnauthorizedBanner.collectAsStateWithLifecycle(initialValue = false)
                var sessionExpiredMessage by androidx.compose.runtime.remember { androidx.compose.runtime.mutableStateOf<String?>(null) }

                LaunchedEffect(Unit) {
                    handleIntent(intent, navController)
                    intentFlow.collect { newIntent ->
                        handleIntent(newIntent, navController)
                    }
                }

                LaunchedEffect(showUnauthorized) {
                    if (showUnauthorized) {
                        authBannerNotifier.dismiss()
                        playerIdentity.clear()
                        sessionExpiredMessage = "Session expired. Please sign in again."
                        navController.navigate(Screen.Login.route) {
                            popUpTo(0) { inclusive = true }
                        }
                    }
                }

                val startDestination = if (authRepository.isLoggedIn()) Screen.Home.route else Screen.Login.route

                Scaffold(
                    modifier = Modifier.fillMaxSize(),
                    containerColor = BackgroundOnyx,
                    topBar = {
                        Column(modifier = Modifier.fillMaxWidth().statusBarsPadding()) {
                            if (showConnectivityWarning) {
                                Surface(
                                    color = Color(0xFFE65100),
                                    modifier = Modifier.fillMaxWidth()
                                ) {
                                    Row(
                                        modifier = Modifier
                                            .fillMaxWidth()
                                            .padding(horizontal = 14.dp, vertical = 8.dp),
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Text(
                                            text = "BASE_URL points at the emulator alias (10.0.2.2). On a real phone set BASE_URL in android/local.properties to your laptop's LAN IP (http://<ip>:8000/) or run `adb reverse tcp:8000 tcp:8000` and use http://localhost:8000/, then rebuild.",
                                            color = TextPrimaryWhite,
                                            style = MaterialTheme.typography.bodySmall,
                                            fontWeight = FontWeight.Medium
                                        )
                                    }
                                }
                            }
                            if (sessionExpiredMessage != null) {
                                Surface(
                                    color = Color(0xFFC62828),
                                    modifier = Modifier.fillMaxWidth()
                                ) {
                                    Row(
                                        modifier = Modifier
                                            .fillMaxWidth()
                                            .padding(horizontal = 16.dp, vertical = 8.dp),
                                        verticalAlignment = Alignment.CenterVertically,
                                        horizontalArrangement = Arrangement.SpaceBetween
                                    ) {
                                        Text(
                                            text = sessionExpiredMessage ?: "",
                                            color = TextPrimaryWhite,
                                            style = MaterialTheme.typography.bodyMedium
                                        )
                                        IconButton(onClick = { sessionExpiredMessage = null }) {
                                            Icon(
                                                imageVector = Icons.Default.Close,
                                                contentDescription = "Dismiss",
                                                tint = TextPrimaryWhite
                                            )
                                        }
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
                        startDestination = startDestination,
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
