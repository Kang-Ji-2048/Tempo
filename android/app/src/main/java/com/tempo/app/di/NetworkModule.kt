package com.tempo.app.di

import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import com.tempo.app.BuildConfig
import com.tempo.app.network.MockTempoApi
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
            .readTimeout(30, TimeUnit.SECONDS)
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
    fun provideTempoApi(
        retrofit: Retrofit,
        mockApi: MockTempoApi,
        @dagger.hilt.android.qualifiers.ApplicationContext context: android.content.Context
    ): TempoApi {
        val prefs = context.getSharedPreferences("tempo_config", android.content.Context.MODE_PRIVATE)
        val useMock = prefs.getBoolean("use_mock_api", BuildConfig.USE_MOCK_API)
        return if (useMock) {
            mockApi
        } else {
            retrofit.create(TempoApi::class.java)
        }
    }
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
}
