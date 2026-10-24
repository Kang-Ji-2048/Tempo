package com.tempo.app.ui.navigation

sealed class Screen(val route: String) {
    data object Login : Screen("auth/login")
    data object Register : Screen("auth/register")
    data object SportSelection : Screen("sport_selection")
    data object Home : Screen("home")
    data object Onboarding : Screen("onboarding")
    data object Capture : Screen("capture")
    data object Analysis : Screen("analysis/{sessionId}") {
        fun createRoute(sessionId: String): String = "analysis/$sessionId"
    }
    data object Live : Screen("live")
    data object Schedule : Screen("schedule")
    data object SduiDebug : Screen("debug/sdui")
}
