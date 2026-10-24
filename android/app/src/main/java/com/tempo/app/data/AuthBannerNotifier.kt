package com.tempo.app.data

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Notifier observed by the root UI to present an explicit banner when
 * the backend rejects an access token (HTTP 401), preventing silent failures.
 */
@Singleton
class AuthBannerNotifier @Inject constructor() {

    private val _showUnauthorizedBanner = MutableStateFlow(false)
    val showUnauthorizedBanner: StateFlow<Boolean> = _showUnauthorizedBanner.asStateFlow()

    fun notifyUnauthorized() {
        _showUnauthorizedBanner.value = true
    }

    fun dismiss() {
        _showUnauthorizedBanner.value = false
    }
}
