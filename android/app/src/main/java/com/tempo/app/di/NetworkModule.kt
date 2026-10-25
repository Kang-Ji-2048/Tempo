package com.tempo.app.di

import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import com.tempo.app.BuildConfig
import com.tempo.app.network.TempoApi
import com.tempo.app.repository.SessionRepository
import com.tempo.app.repository.SessionRepositoryImpl
import dagger.Binds
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import java.util.concurrent.TimeUnit
import javax.inject.Named
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {

    @Provides
    @Singleton
    fun provideJson(): Json = Json {
        ignoreUnknownKeys = true
        isLenient = true
        encodeDefaults = true
        // A JSON null for a non-null Kotlin field falls back to its default instead of failing a 200.
        coerceInputValues = true
        prettyPrint = false
    }

    @Provides
    @Singleton
    fun provideOkHttpClient(
        identity: com.tempo.app.data.PlayerIdentity,
        authBannerNotifier: com.tempo.app.data.AuthBannerNotifier
    ): OkHttpClient {
        val logging = HttpLoggingInterceptor().apply {
            level = if (BuildConfig.DEBUG) {
                HttpLoggingInterceptor.Level.BASIC
            } else {
                HttpLoggingInterceptor.Level.NONE
            }
        }
        logging.redactHeader("Authorization")
        return OkHttpClient.Builder()
            .addInterceptor { chain ->
                val identityToken = identity.accessToken
                val token = if (identityToken.isNotBlank()) identityToken else BuildConfig.TEMPO_DEBUG_TOKEN
                val request = chain.request().newBuilder().apply {
                    if (token.isNotBlank()) header("Authorization", "Bearer $token")
                }.build()
                val response = chain.proceed(request)
                if (response.code == 401) {
                    authBannerNotifier.notifyUnauthorized()
                }
                response
            }
            .addInterceptor(logging)
            .connectTimeout(15, TimeUnit.SECONDS)
            // Gemini tool-calling turns and plan generation routinely take 15-30 s.
            .readTimeout(90, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .build()
    }

    @Provides
    @Singleton
    fun provideRetrofit(okHttpClient: OkHttpClient, json: Json): Retrofit {
        val contentType = "application/json".toMediaType()
        return Retrofit.Builder()
            .baseUrl(BuildConfig.BASE_URL)
            .client(okHttpClient)
            .addConverterFactory(json.asConverterFactory(contentType))
            .build()
    }

    @Provides
    @Singleton
    fun provideTempoApi(retrofit: Retrofit): TempoApi = retrofit.create(TempoApi::class.java)
}

@Module
@InstallIn(SingletonComponent::class)
abstract class RepositoryModule {

    @Binds
    @Singleton
    abstract fun bindSessionRepository(
        impl: SessionRepositoryImpl
    ): SessionRepository

    @Binds
    @Singleton
    abstract fun bindOnboardingRepository(
        impl: com.tempo.app.repository.OnboardingRepositoryImpl
    ): com.tempo.app.repository.OnboardingRepository

    @Binds
    @Singleton
    abstract fun bindUserProfileRepository(
        impl: com.tempo.app.repository.UserProfileRepositoryImpl
    ): com.tempo.app.repository.UserProfileRepository

    @Binds
    @Singleton
    abstract fun bindAuthRepository(
        impl: com.tempo.app.repository.AuthRepositoryImpl
    ): com.tempo.app.repository.AuthRepository
}
