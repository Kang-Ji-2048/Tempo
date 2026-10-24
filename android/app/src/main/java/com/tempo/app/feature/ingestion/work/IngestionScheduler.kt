package com.tempo.app.feature.ingestion.work

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.workDataOf
import java.util.UUID
import java.util.concurrent.TimeUnit

object IngestionScheduler {

    /**
     * Enqueues a network-constrained, exponential-backoff WorkManager request to compress and upload
     * the captured practice clip. This guarantees survival across app closure and process death.
     */
    fun scheduleUpload(
        context: Context,
        sessionId: String,
        videoPath: String,
        sport: String = "badminton",
        strokeType: String = "overhead_clear",
        targetArchetype: String? = "Axelsen",
        userIntent: String? = "Working on steep angle and early high contact reach",
        userId: String = "usr_sumanth_001"
    ): UUID {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()

        val inputData = workDataOf(
            UploadWorker.KEY_SESSION_ID to sessionId,
            UploadWorker.KEY_VIDEO_PATH to videoPath,
            UploadWorker.KEY_SPORT to sport,
            UploadWorker.KEY_STROKE_TYPE to strokeType,
            UploadWorker.KEY_TARGET_ARCHETYPE to targetArchetype,
            UploadWorker.KEY_USER_INTENT to userIntent,
            UploadWorker.KEY_USER_ID to userId
        )

        val uploadRequest = OneTimeWorkRequestBuilder<UploadWorker>()
            .setConstraints(constraints)
            .setBackoffCriteria(
                BackoffPolicy.EXPONENTIAL,
                15,
                TimeUnit.SECONDS
            )
            .setInputData(inputData)
            .addTag("session_upload_$sessionId")
            .build()

        WorkManager.getInstance(context).enqueueUniqueWork(
            "session_upload_$sessionId",
            ExistingWorkPolicy.REPLACE,
            uploadRequest
        )

        return uploadRequest.id
    }
}
