package com.tempo.app.ui.components

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Sensors
import androidx.compose.material.icons.filled.Videocam
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.currentBackStackEntryAsState
import com.tempo.app.ui.navigation.Screen
import com.tempo.app.ui.theme.AccentNeonVolt
import com.tempo.app.ui.theme.BackgroundOnyx
import com.tempo.app.ui.theme.SurfaceCharcoal
import com.tempo.app.ui.theme.TextMuted
import com.tempo.app.ui.theme.TextPrimaryWhite

data class BottomNavItem(
    val title: String,
    val route: String,
    val icon: ImageVector
)

val BottomNavItems = listOf(
    BottomNavItem(title = "Home", route = Screen.Home.route, icon = Icons.Default.Home),
    BottomNavItem(title = "Live", route = Screen.Live.route, icon = Icons.Default.Sensors),
    BottomNavItem(title = "Capture", route = Screen.Capture.route, icon = Icons.Default.Videocam),
    BottomNavItem(title = "Schedule", route = Screen.Schedule.route, icon = Icons.Default.CalendarMonth)
)

@Composable
fun TempoBottomBar(
    navController: NavController,
    modifier: Modifier = Modifier
) {
    val navBackStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = navBackStackEntry?.destination?.route

    // Only display bottom bar on top-level routes
    val isTopLevelDestination = BottomNavItems.any { it.route == currentRoute }
    if (!isTopLevelDestination) return

    Surface(
        modifier = modifier.fillMaxWidth(),
        color = SurfaceCharcoal,
        shape = RoundedCornerShape(topStart = 24.dp, topEnd = 24.dp),
        shadowElevation = 8.dp
    ) {
        NavigationBar(
            containerColor = SurfaceCharcoal,
            modifier = Modifier.height(72.dp)
        ) {
            BottomNavItems.forEach { item ->
                val selected = currentRoute == item.route
                NavigationBarItem(
                    selected = selected,
                    onClick = {
                        if (currentRoute != item.route) {
                            navController.navigate(item.route) {
                                popUpTo(navController.graph.findStartDestination().id) {
                                    saveState = true
                                }
                                launchSingleTop = true
                                restoreState = true
                            }
                        }
                    },
                    icon = {
                        Icon(
                            imageVector = item.icon,
                            contentDescription = item.title
                        )
                    },
                    label = {
                        Text(text = item.title)
                    },
                    colors = NavigationBarItemDefaults.colors(
                        selectedIconColor = BackgroundOnyx,
                        selectedTextColor = AccentNeonVolt,
                        indicatorColor = AccentNeonVolt,
                        unselectedIconColor = TextMuted,
                        unselectedTextColor = TextMuted
                    )
                )
            }
        }
    }
}
