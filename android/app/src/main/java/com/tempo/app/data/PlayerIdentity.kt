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
        get() = "user_1"
        set(value) {}
    var accessToken: String
        get() = ""
        set(value) {}
}

@Singleton
class SharedPreferencesPlayerIdentity @Inject constructor(@ApplicationContext context: Context) : PlayerIdentity {
    private val preferences = context.getSharedPreferences("tempo_identity", Context.MODE_PRIVATE)
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
            if (encoded == null) "" else {
                val pieces = encoded.split(":")
                val cipher = javax.crypto.Cipher.getInstance("AES/GCM/NoPadding")
                cipher.init(javax.crypto.Cipher.DECRYPT_MODE, key(),
                    javax.crypto.spec.GCMParameterSpec(128, android.util.Base64.decode(pieces[0], android.util.Base64.NO_WRAP)))
                String(cipher.doFinal(android.util.Base64.decode(pieces[1], android.util.Base64.NO_WRAP)), Charsets.UTF_8)
            }
        } catch (_: Exception) { "" }
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
            val defaultId = BuildConfig.TEMPO_USER_ID.ifBlank { "user_1" }
            return preferences.getString("user_id", preferences.getString("player_id", defaultId) ?: defaultId) ?: defaultId
        }
        set(value) {
            val clean = value.trim().ifBlank { BuildConfig.TEMPO_USER_ID.ifBlank { "user_1" } }
            preferences.edit()
                .putString("user_id", clean)
                .putString("player_id", clean)
                .apply()
        }
    override var playerId: String
        get() = userId
        set(value) { userId = value }
}

@Module
@InstallIn(SingletonComponent::class)
abstract class PlayerIdentityModule {
    @Binds abstract fun bindIdentity(impl: SharedPreferencesPlayerIdentity): PlayerIdentity
}
