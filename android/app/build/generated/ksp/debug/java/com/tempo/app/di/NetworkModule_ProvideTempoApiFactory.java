package com.tempo.app.di;

import com.tempo.app.network.MockTempoApi;
import com.tempo.app.network.TempoApi;
import dagger.internal.DaggerGenerated;
import dagger.internal.Factory;
import dagger.internal.Preconditions;
import dagger.internal.QualifierMetadata;
import dagger.internal.ScopeMetadata;
import javax.annotation.processing.Generated;
import javax.inject.Provider;
import retrofit2.Retrofit;

@ScopeMetadata("javax.inject.Singleton")
@QualifierMetadata
@DaggerGenerated
@Generated(
    value = "dagger.internal.codegen.ComponentProcessor",
    comments = "https://dagger.dev"
)
@SuppressWarnings({
    "unchecked",
    "rawtypes",
    "KotlinInternal",
    "KotlinInternalInJava",
    "cast"
})
public final class NetworkModule_ProvideTempoApiFactory implements Factory<TempoApi> {
  private final Provider<Retrofit> retrofitProvider;

  private final Provider<MockTempoApi> mockApiProvider;

  public NetworkModule_ProvideTempoApiFactory(Provider<Retrofit> retrofitProvider,
      Provider<MockTempoApi> mockApiProvider) {
    this.retrofitProvider = retrofitProvider;
    this.mockApiProvider = mockApiProvider;
  }

  @Override
  public TempoApi get() {
    return provideTempoApi(retrofitProvider.get(), mockApiProvider.get());
  }

  public static NetworkModule_ProvideTempoApiFactory create(Provider<Retrofit> retrofitProvider,
      Provider<MockTempoApi> mockApiProvider) {
    return new NetworkModule_ProvideTempoApiFactory(retrofitProvider, mockApiProvider);
  }

  public static TempoApi provideTempoApi(Retrofit retrofit, MockTempoApi mockApi) {
    return Preconditions.checkNotNullFromProvides(NetworkModule.INSTANCE.provideTempoApi(retrofit, mockApi));
  }
}
