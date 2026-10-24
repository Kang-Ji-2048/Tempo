package com.tempo.app.feature.correction.data

import android.content.Context
import com.tempo.app.feature.correction.model.ReferenceArchetypeData
import com.tempo.app.feature.correction.model.ReferencePhaseData
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.serialization.json.Json
import java.io.InputStreamReader
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class ReferenceArchetypeLoader @Inject constructor(
    @ApplicationContext private val context: Context,
    private val json: Json
) {
    private var cachedArchetype: ReferenceArchetypeData? = null

    fun loadReferenceArchetype(assetFileName: String = "reference_archetype_badminton.json"): ReferenceArchetypeData {
        cachedArchetype?.let { return it }

        return try {
            context.assets.open(assetFileName).use { inputStream ->
                InputStreamReader(inputStream).use { reader ->
                    val content = reader.readText()
                    val parsed = json.decodeFromString<ReferenceArchetypeData>(content)
                    cachedArchetype = parsed
                    parsed
                }
            }
        } catch (e: Exception) {
            // Fallback default reference archetype if asset loading fails
            val fallback = ReferenceArchetypeData(
                sport = "badminton",
                strokeType = "overhead_clear",
                archetypeName = "Viktor Axelsen Pro Benchmark",
                phases = emptyList()
            )
            fallback
        }
    }

    fun getPhaseReference(phaseName: String): ReferencePhaseData? {
        val archetype = loadReferenceArchetype()
        return archetype.phases.firstOrNull { it.phaseName.equals(phaseName, ignoreCase = true) }
    }
}
