package com.tempo.app.feature.ingestion

import android.content.Context
import android.net.Uri
import androidx.annotation.OptIn
import androidx.media3.common.MediaItem
import androidx.media3.common.util.UnstableApi
import androidx.media3.effect.Presentation
import androidx.media3.transformer.Composition
import androidx.media3.transformer.EditedMediaItem
import androidx.media3.transformer.EditedMediaItemSequence
import androidx.media3.transformer.Effects
import androidx.media3.transformer.ExportException
import androidx.media3.transformer.ExportResult
import androidx.media3.transformer.Transformer
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import java.io.File
import kotlin.coroutines.resume

@OptIn(UnstableApi::class)
object Media3VideoCompressor {

    /**
     * Compresses the input video file to 720p resolution using Media3 Transformer.
     * Returns the compressed File on success, or the original file if compression fails or is cancelled.
     */
    suspend fun compressTo720p(context: Context, inputFile: File, outputFile: File): File = withContext(Dispatchers.Main) {
        if (!inputFile.exists() || inputFile.length() == 0L) {
            return@withContext inputFile
        }

        try {
            suspendCancellableCoroutine { continuation ->
                val mediaItem = MediaItem.fromUri(Uri.fromFile(inputFile))
                val presentationEffect = Presentation.createForHeight(720)

                val editedMediaItem = EditedMediaItem.Builder(mediaItem)
                    .setEffects(Effects(emptyList(), listOf(presentationEffect)))
                    .build()

                val transformer = Transformer.Builder(context)
                    .addListener(object : Transformer.Listener {
                        override fun onCompleted(composition: Composition, exportResult: ExportResult) {
                            if (outputFile.exists() && outputFile.length() > 0L) {
                                continuation.resume(outputFile)
                            } else {
                                continuation.resume(inputFile)
                            }
                        }

                        override fun onError(
                            composition: Composition,
                            exportResult: ExportResult,
                            exportException: ExportException
                        ) {
                            // On error, fallback gracefully to original file
                            continuation.resume(inputFile)
                        }
                    })
                    .build()

                if (outputFile.exists()) {
                    outputFile.delete()
                }

                transformer.start(editedMediaItem, outputFile.absolutePath)

                continuation.invokeOnCancellation {
                    try {
                        transformer.cancel()
                    } catch (_: Exception) {}
                }
            }
        } catch (e: Exception) {
            // Fallback to original input file if any exception occurs during transformation setup
            inputFile
        }
    }
}
