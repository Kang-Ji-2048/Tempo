package com.tempo.app.data

import android.content.Context
import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

import com.tempo.app.BuildConfig

interface PlayerIdentity {
    var userId: String
        get() = playerId
        set(value) { playerId = value }
    var playerId: String
        get() = if (BuildConfig.DEBUG) BuildConfig.TEMPO_USER_ID.ifBlank { "user_1" } else ""
        set(value) {}
    var accessToken: String
        get() = if (BuildConfig.DEBUG) BuildConfig.TEMPO_DEBUG_TOKEN else ""
        set(value) {}
    var email: String
        get() = ""
        set(value) {}
    var displayName: String
        get() = ""
        set(value) {}
    var sport: String?
        get() = null
        set(value) {}
    var skill: String?
        get() = null
        set(value) {}
    fun clear() {}
}

@Singleton
class SharedPreferencesPlayerIdentity @Inject constructor(@ApplicationContext context: Context) : PlayerIdentity {
    private val preferences = context.getSharedPreferences("tempo_identity", Context.MODE_PRIVATE)
    private val configPreferences = context.getSharedPreferences("tempo_config", Context.MODE_PRIVATE)
    private fun key(): javax.crypto.SecretKey {
        val store = java.security.KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey("tempo_api_token", null) as? javax.crypto.SecretKey)?.let { return it }
        return javax.crypto.KeyGenerator.getInstance("AES", "AndroidKeyStore").apply {
            init(android.security.keystore.KeyGenParameterSpec.Builder("tempo_api_token",
                android.security.keystore.KeyProperties.PURPOSE_ENCRYPT or android.security.keystore.KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes("GCM").setEncryptionPaddings("NoPadding").build())
        }.generateKey()
    }
    override var accessToken: String
        get() = try {
            val encoded = preferences.getString("access_token", null)
            if (encoded != null) {
                val pieces = encoded.split(":")
                val cipher = javax.crypto.Cipher.getInstance("AES/GCM/NoPadding")
                cipher.init(javax.crypto.Cipher.DECRYPT_MODE, key(),
                    javax.crypto.spec.GCMParameterSpec(128, android.util.Base64.decode(pieces[0], android.util.Base64.NO_WRAP)))
                String(cipher.doFinal(android.util.Base64.decode(pieces[1], android.util.Base64.NO_WRAP)), Charsets.UTF_8)
            } else if (BuildConfig.DEBUG && BuildConfig.TEMPO_DEBUG_TOKEN.isNotBlank()) {
                BuildConfig.TEMPO_DEBUG_TOKEN
            } else {
                ""
            }
        } catch (_: Exception) {
            if (BuildConfig.DEBUG) BuildConfig.TEMPO_DEBUG_TOKEN else ""
        }
        set(value) {
            if (value.isBlank()) { preferences.edit().remove("access_token").apply(); return }
            val cipher = javax.crypto.Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(javax.crypto.Cipher.ENCRYPT_MODE, key())
            val iv = android.util.Base64.encodeToString(cipher.iv, android.util.Base64.NO_WRAP)
            val encrypted = android.util.Base64.encodeToString(cipher.doFinal(value.trim().toByteArray(Charsets.UTF_8)), android.util.Base64.NO_WRAP)
            preferences.edit().putString("access_token", "$iv:$encrypted").apply()
        }
    override var userId: String
        get() {
            val fallback = if (BuildConfig.DEBUG) BuildConfig.TEMPO_USER_ID.ifBlank { "user_1" } else ""
            return preferences.getString("user_id", preferences.getString("player_id", fallback) ?: fallback) ?: fallback
        }
        set(value) {
            val clean = value.trim()
            preferences.edit()
                .putString("user_id", clean)
                .putString("player_id", clean)
                .apply()
        }
    override var playerId: String
        get() = userId
        set(value) { userId = value }

    override var email: String
        get() = preferences.getString("email", "") ?: ""
        set(value) { preferences.edit().putString("email", value.trim()).apply() }

    override var displayName: String
        get() = preferences.getString("display_name", "") ?: ""
        set(value) { preferences.edit().putString("display_name", value.trim()).apply() }

    override var sport: String?
        get() = preferences.getString("sport", null)
        set(value) {
            if (value == null) preferences.edit().remove("sport").apply()
            else preferences.edit().putString("sport", value).apply()
        }

    override var skill: String?
        get() = preferences.getString("skill", null)
        set(value) {
            if (value == null) preferences.edit().remove("skill").apply()
            else preferences.edit().putString("skill", value).apply()
        }

    override fun clear() {
        preferences.edit().clear().commit()
        configPreferences.edit().clear().commit()
        try {
            java.security.KeyStore.getInstance("AndroidKeyStore").apply { load(null) }.deleteEntry("tempo_api_token")
        } catch (_: Exception) {}
    }
}

@Module
@InstallIn(SingletonComponent::class)
abstract class PlayerIdentityModule {
    @Binds abstract fun bindIdentity(impl: SharedPreferencesPlayerIdentity): PlayerIdentity
}
