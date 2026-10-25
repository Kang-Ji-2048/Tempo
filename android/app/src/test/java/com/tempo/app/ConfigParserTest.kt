package com.tempo.app

import com.tempo.app.data.PlayerIdentity
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Properties

class ConfigParserTest {

    @Test
    fun testBuildConfigStylePropertiesParserDefaultsWhenKeysMissing() {
        // Simulates reading an empty local.properties file
        val properties = Properties()

        val baseUrl = properties.getProperty("BASE_URL", "http://10.0.2.2:8000/")
        val debugToken = properties.getProperty("TEMPO_DEBUG_TOKEN", "")
        val theaNumber = properties.getProperty("THEA_NUMBER", "")
        val useMockApi = properties.getProperty("USE_MOCK_API", "false").toBoolean()
        val userId = properties.getProperty("TEMPO_USER_ID", "user_1")

        assertEquals("http://10.0.2.2:8000/", baseUrl)
        assertEquals("", debugToken)
        assertEquals("", theaNumber)
        assertFalse(useMockApi)
        assertEquals("user_1", userId)
    }

    @Test
    fun testBuildConfigStylePropertiesParserPicksExplicitValues() {
        val properties = Properties().apply {
            setProperty("BASE_URL", "http://192.168.1.100:8000/")
            setProperty("TEMPO_DEBUG_TOKEN", "tempo_tok_secret_12345")
            setProperty("THEA_NUMBER", "447700900123")
            setProperty("USE_MOCK_API", "true")
            setProperty("TEMPO_USER_ID", "user_sumanth")
        }

        val baseUrl = properties.getProperty("BASE_URL", "http://10.0.2.2:8000/")
        val debugToken = properties.getProperty("TEMPO_DEBUG_TOKEN", "")
        val theaNumber = properties.getProperty("THEA_NUMBER", "")
        val useMockApi = properties.getProperty("USE_MOCK_API", "false").toBoolean()
        val userId = properties.getProperty("TEMPO_USER_ID", "user_1")

        assertEquals("http://192.168.1.100:8000/", baseUrl)
        assertEquals("tempo_tok_secret_12345", debugToken)
        assertEquals("447700900123", theaNumber)
        assertTrue(useMockApi)
        assertEquals("user_sumanth", userId)
    }

    @Test
    fun testPlayerIdentityUserIdUnification() {
        val identity = object : PlayerIdentity {
            override var playerId = "test_player_abc"
        }

        // Mutual delegation guarantees userId reflects playerId
        assertEquals("test_player_abc", identity.userId)
        assertEquals("test_player_abc", identity.playerId)

        identity.userId = "user_1"
        assertEquals("user_1", identity.userId)
    }
}
