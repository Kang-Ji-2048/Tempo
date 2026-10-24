package com.tempo.app.network;

import dagger.internal.DaggerGenerated;
import dagger.internal.Factory;
import dagger.internal.QualifierMetadata;
import dagger.internal.ScopeMetadata;
import javax.annotation.processing.Generated;

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
public final class MockTempoApi_Factory implements Factory<MockTempoApi> {
  @Override
  public MockTempoApi get() {
    return newInstance();
  }

  public static MockTempoApi_Factory create() {
    return InstanceHolder.INSTANCE;
  }

  public static MockTempoApi newInstance() {
    return new MockTempoApi();
  }

  private static final class InstanceHolder {
    private static final MockTempoApi_Factory INSTANCE = new MockTempoApi_Factory();
  }
}
