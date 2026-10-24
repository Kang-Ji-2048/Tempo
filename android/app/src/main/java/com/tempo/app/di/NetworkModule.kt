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
    fun provideOkHttpClient(identity: com.tempo.app.data.PlayerIdentity): OkHttpClient {
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
                val token = identity.accessToken
                val request = chain.request().newBuilder().apply {
                    if (token.isNotBlank()) header("Authorization", "Bearer $token")
                }.build()
                chain.proceed(request)
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
        mockApi: MockTempoApi
    ): TempoApi {
        // Toggle real vs mock api via BuildConfig.USE_MOCK_API debug flag
        return if (BuildConfig.USE_MOCK_API) {
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
}
