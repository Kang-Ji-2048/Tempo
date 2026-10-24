package com.tempo.app.service

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import androidx.core.app.NotificationCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.tempo.app.MainActivity
import java.util.concurrent.atomic.AtomicInteger

class TempoFirebaseMessagingService : FirebaseMessagingService() {

    override fun onNewToken(token: String) {
        super.onNewToken(token)
        // Store or transmit FCM token for push dispatches
    }

    override fun onMessageReceived(remoteMessage: RemoteMessage) {
        super.onMessageReceived(remoteMessage)

        val data = remoteMessage.data
        val sessionId = data["session_id"]
        val screenTarget = data["screen_target"] ?: data["screen"]

        val title = remoteMessage.notification?.title
            ?: data["title"]
            ?: "Tempo Coach Update"
        val body = remoteMessage.notification?.body
            ?: data["body"]
            ?: "Your session analysis or practice reminder is ready."

        showNotification(
            title = title,
            body = body,
            sessionId = sessionId,
            screenTarget = screenTarget
        )
    }

    private fun showNotification(
        title: String,
        body: String,
        sessionId: String?,
        screenTarget: String?
    ) {
        val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        createChannel(notificationManager)

        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
            if (!sessionId.isNullOrBlank()) {
                data = Uri.parse("tempo://app/analysis/$sessionId")
                putExtra(EXTRA_SCREEN_TARGET, "analysis")
                putExtra(EXTRA_SESSION_ID, sessionId)
            } else if (screenTarget.equals("capture", ignoreCase = true)) {
                data = Uri.parse("tempo://app/capture")
                putExtra(EXTRA_SCREEN_TARGET, "capture")
            } else if (screenTarget.equals("schedule", ignoreCase = true)) {
                data = Uri.parse("tempo://app/schedule")
                putExtra(EXTRA_SCREEN_TARGET, "schedule")
            } else {
                data = Uri.parse("tempo://app/home")
                putExtra(EXTRA_SCREEN_TARGET, "home")
            }
        }

        val requestCode = notificationIdCounter.incrementAndGet()
        val pendingIntent = PendingIntent.getActivity(
            this,
            requestCode,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)
            .build()

        notificationManager.notify(requestCode, notification)
    }

    private fun createChannel(manager: NotificationManager) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Tempo Practice Alerts",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Cadence schedule reminders and practice session analysis notifications"
                enableLights(true)
                enableVibration(true)
            }
            manager.createNotificationChannel(channel)
        }
    }

    companion object {
        const val CHANNEL_ID = "tempo_coach_alerts"
        const val EXTRA_SCREEN_TARGET = "screen_target"
        const val EXTRA_SESSION_ID = "session_id"
        private val notificationIdCounter = AtomicInteger(1000)
    }
}
