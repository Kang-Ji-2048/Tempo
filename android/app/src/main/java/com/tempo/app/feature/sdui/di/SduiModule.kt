package com.tempo.app.feature.sdui.di

import com.tempo.app.feature.sdui.data.MockSduiApi
import com.tempo.app.feature.sdui.data.SduiApi
import com.tempo.app.feature.sdui.data.SduiRepository
import com.tempo.app.feature.sdui.data.SduiRepositoryImpl
import com.tempo.app.feature.sdui.data.WidgetParser
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import retrofit2.Retrofit
import javax.inject.Qualifier
import javax.inject.Singleton

/** Repository that is always backed by [MockSduiApi], regardless of USE_MOCK_API. */
@Qualifier
@Retention(AnnotationRetention.BINARY)
annotation class MockSdui

@Module
@InstallIn(SingletonComponent::class)
object SduiModule {

    @Provides
    @Singleton
    fun provideSduiApi(retrofit: Retrofit): SduiApi = retrofit.create(SduiApi::class.java)

    @Provides
    @Singleton
    fun provideSduiRepository(api: SduiApi, parser: WidgetParser): SduiRepository =
        SduiRepositoryImpl(api, parser)

    @Provides
    @Singleton
    @MockSdui
    fun provideMockSduiRepository(mock: MockSduiApi, parser: WidgetParser): SduiRepository =
        SduiRepositoryImpl(mock, parser)
}
