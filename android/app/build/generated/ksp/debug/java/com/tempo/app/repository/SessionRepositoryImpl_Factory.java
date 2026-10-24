package com.tempo.app.repository;

import com.tempo.app.network.TempoApi;
import dagger.internal.DaggerGenerated;
import dagger.internal.Factory;
import dagger.internal.QualifierMetadata;
import dagger.internal.ScopeMetadata;
import javax.annotation.processing.Generated;
import javax.inject.Provider;

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
public final class SessionRepositoryImpl_Factory implements Factory<SessionRepositoryImpl> {
  private final Provider<TempoApi> apiProvider;

  public SessionRepositoryImpl_Factory(Provider<TempoApi> apiProvider) {
    this.apiProvider = apiProvider;
  }

  @Override
  public SessionRepositoryImpl get() {
    return newInstance(apiProvider.get());
  }

  public static SessionRepositoryImpl_Factory create(Provider<TempoApi> apiProvider) {
    return new SessionRepositoryImpl_Factory(apiProvider);
  }

  public static SessionRepositoryImpl newInstance(TempoApi api) {
    return new SessionRepositoryImpl(api);
  }
}
