package com.tempo.app.network

import com.tempo.app.network.models.SessionIngestResponseDto
import com.tempo.app.network.models.SessionRecordDto
import com.tempo.app.network.models.UserScheduleDto
import kotlinx.coroutines.delay
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import okhttp3.MultipartBody
import okhttp3.RequestBody
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton

/**
 * High-fidelity Mock implementation of TempoApi for offline development and testing.
 * Conforms to project rule: "provide a MockApi so every screen works offline".
 */
@Singleton
class MockTempoApi @Inject constructor(
    private val identity: com.tempo.app.data.PlayerIdentity
) : TempoApi {

    constructor() : this(object : com.tempo.app.data.PlayerIdentity {})

    private val currentUserId: String get() = identity.userId.ifBlank { "user_1" }

    private val pollCounts = java.util.concurrent.ConcurrentHashMap<String, Int>()
    private val savedSchedules = java.util.concurrent.ConcurrentHashMap<String, UserScheduleDto>()

    override suspend fun getHealth(): Map<String, String> {
        return mapOf("status" to "ready", "service" to "tempo-mock")
    }

    override suspend fun ingestSession(
        metadata: RequestBody,
        video: MultipartBody.Part?
    ): SessionIngestResponseDto {
        delay(400) // Simulate fast network turnaround
        return SessionIngestResponseDto(
            sessionId = okio.Buffer().also { metadata.writeTo(it) }.readUtf8().let {
                kotlinx.serialization.json.Json.parseToJsonElement(it)
                    .let { element -> (element as? kotlinx.serialization.json.JsonObject)?.get("session_id") }
                    ?.let { element -> (element as? kotlinx.serialization.json.JsonPrimitive)?.content }
            } ?: UUID.randomUUID().toString(),
            status = "PENDING",
            estimatedAnalysisTimeSec = 8,
            message = "Offline mock session ingestion accepted."
        )
    }

    fun resetSessionPollCount(sessionId: String) {
        pollCounts.remove(sessionId)
    }

    override suspend fun getSession(sessionId: String): SessionRecordDto {
        delay(300)
        val count = pollCounts.compute(sessionId) { _, current -> (current ?: 0) + 1 } ?: 1

        val currentStatus = when {
            sessionId.contains("fail", ignoreCase = true) -> "FAILED"
            count <= 1 -> "PENDING"
            count == 2 -> "ANALYZING"
            else -> "COMPLETED"
        }

        if (currentStatus == "FAILED") {
            return SessionRecordDto(
                sessionId = sessionId,
                userId = currentUserId,
                sport = "badminton",
                strokeType = "overhead_clear",
                targetArchetype = "Viktor Axelsen",
                status = "FAILED",
                errorMessage = "Biomechanical analysis failed: athlete body lost from frame at impact point."
            )
        }

        if (currentStatus == "PENDING" || currentStatus == "ANALYZING") {
            return SessionRecordDto(
                sessionId = sessionId,
                userId = currentUserId,
                sport = "badminton",
                strokeType = "overhead_clear",
                targetArchetype = "Viktor Axelsen",
                status = currentStatus,
                telemetryCount = 3
            )
        }

        // COMPLETED state with rich SDUI widgets
        val mockFeedback = buildJsonObject {
            put("overall_score", 85)
            put("matched_archetype", "Viktor Axelsen")
            put("primary_flaw", "Elbow dropped to 158.4° at contact")
            put("concise_audio_cue", "Accelerate forearm pronation at peak reach.")
            put("coach_voice_note_script", "Great session today! Your contact reach was explosive, but your elbow dropped to 158 degrees before full pronation. Focus on driving your elbow to 175 degrees at impact for maximum steepness.")
            put("voice_note_url", "https://actions.google.com/sounds/v1/sports/badminton_rally.ogg")
            put("kinetic_phases", kotlinx.serialization.json.buildJsonArray {
                add(buildJsonObject {
                    put("phase_name", "Preparation")
                    put("timestamp_ms", 300)
                    put("form_accuracy_score", 92)
                    put("observation", "Stable base with strong non-racket arm elevation for tracking shuttle height.")
                })
                add(buildJsonObject {
                    put("phase_name", "Loading")
                    put("timestamp_ms", 850)
                    put("form_accuracy_score", 80)
                    put("observation", "Slightly restricted thoracic arch during loading phase under fatigue.")
                })
                add(buildJsonObject {
                    put("phase_name", "Impact")
                    put("timestamp_ms", 1320)
                    put("form_accuracy_score", 74)
                    put("observation", "Elbow flexion at contact (158.4°) lacked full extension compared to Axelsen profile (175°).")
                })
                add(buildJsonObject {
                    put("phase_name", "Follow-Through")
                    put("timestamp_ms", 1750)
                    put("form_accuracy_score", 88)
                    put("observation", "Smooth kinetic dissipation across the torso with quick split-step recovery.")
                })
            })
        }

        val mockWidget1 = buildJsonObject {
            put("widget_type", "PathProgressWidget")
            put("title", "Forearm Mechanics Path")
            put("current_streak", 5)
            put("active_node_id", "node_pronation_03")
            put("nodes", kotlinx.serialization.json.buildJsonArray {
                add(buildJsonObject {
                    put("node_id", "node_pronation_01")
                    put("title", "High Elbow Setup")
                    put("status", "DONE")
                    put("xp_reward", 50)
                })
                add(buildJsonObject {
                    put("node_id", "node_pronation_02")
                    put("title", "Shoulder Rotation")
                    put("status", "DONE")
                    put("xp_reward", 50)
                })
                add(buildJsonObject {
                    put("node_id", "node_pronation_03")
                    put("title", "Peak Pronation Speed")
                    put("status", "ACTIVE")
                    put("xp_reward", 75)
                })
                add(buildJsonObject {
                    put("node_id", "node_pronation_04")
                    put("title", "Wrist Snap Recovery")
                    put("status", "LOCKED")
                    put("xp_reward", 100)
                })
            })
        }

        val mockWidget2 = buildJsonObject {
            put("widget_type", "DrillCardWidget")
            put("id", "drill_pronation_wall_30s")
            put("title", "30s Rapid Pronation Drill")
            put("instruction", "Rapidly rotate forearm against wall target maintaining high elbow position.")
            put("target_reps", 15)
            put("focus_cue", "Full elbow extension at contact.")
        }

        val mockWidget3 = buildJsonObject {
            put("widget_type", "ConceptQuizWidget")
            put("id", "quiz_impact_angle")
            put("question", "What is the primary power generation mechanism in an overhead clear?")
            put("options", kotlinx.serialization.json.buildJsonArray {
                add(kotlinx.serialization.json.JsonPrimitive("Bicep flexion"))
                add(kotlinx.serialization.json.JsonPrimitive("Forearm pronation & kinetic chain"))
                add(kotlinx.serialization.json.JsonPrimitive("Wrist flick only"))
            })
            put("correct_index", 1)
            put("explanation", "Forearm pronation combined with kinetic chain sequencing transfers maximum energy into the shuttlecock.")
        }

        return SessionRecordDto(
            sessionId = sessionId,
            userId = currentUserId,
            sport = "badminton",
            strokeType = "overhead_clear",
            targetArchetype = "Viktor Axelsen",
            status = "COMPLETED",
            telemetryCount = 3,
            geminiFeedback = mockFeedback,
            activeWidgets = listOf(mockWidget1, mockWidget2, mockWidget3),
            kinematicVector = listOf(0.97f, 0.93f, 0.95f, 0.91f, 0.80f, 0.94f)
        )
    }

    override suspend fun getSchedule(userId: String): UserScheduleDto {
        delay(200)
        return savedSchedules[userId] ?: UserScheduleDto(
            userId = userId,
            sport = "badminton",
            strokeType = "overhead_clear",
            daysOfWeek = listOf("Monday", "Wednesday", "Friday"),
            targetTimeUtc = "18:00",
            primingLeadMinutes = 30,
            preferredChannel = "whatsapp",
            isActive = true
        )
    }

    override suspend fun updateSchedule(schedule: UserScheduleDto): UserScheduleDto {
        delay(200)
        savedSchedules[schedule.userId] = schedule
        return schedule
    }

    override suspend fun getCoachMemory(): com.tempo.app.network.models.CoachMemoryResponseDto {
        delay(150)
        return com.tempo.app.network.models.CoachMemoryResponseDto()
    }

    override suspend fun nextOnboardingStep(
        request: com.tempo.app.network.models.OnboardingStepRequestDto
    ): com.tempo.app.network.models.OnboardingStepResponseDto {
        delay(250) // High responsiveness
        val answers = request.answers.toMutableMap()
        if (request.stepId.isNotBlank() && request.answer.isNotBlank()) {
            answers[request.stepId] = request.answer
        }

        val currentStep = request.stepId.ifBlank { "init" }

        // Step 0 -> Sport
        if (currentStep == "init" || currentStep.isEmpty()) {
            val widget = buildJsonObject {
                put("widget_type", "ChoiceWidget")
                put("id", "sport")
                put("title", "Select Your Sport")
                put("subtitle", "Your kinematic models and Olympic benchmarks adapt to this sport.")
                put("multi_select", false)
                put("options", kotlinx.serialization.json.buildJsonArray {
                    add(buildJsonObject {
                        put("id", "badminton")
                        put("label", "Badminton")
                        put("description", "High-velocity overhead clears, jump smashes, and lateral split-steps")
                        put("emoji", "🏸")
                    })
                    add(buildJsonObject {
                        put("id", "tennis")
                        put("label", "Tennis")
                        put("description", "Heavy topspin groundstrokes, kinetic serve chain, and court transitions")
                        put("emoji", "🎾")
                    })
                    add(buildJsonObject {
                        put("id", "pickleball")
                        put("label", "Pickleball")
                        put("description", "Kitchen dinks, rapid hand speed, reset mechanics, and rotational drives")
                        put("emoji", "🏓")
                    })
                    add(buildJsonObject {
                        put("id", "squash")
                        put("label", "Squash")
                        put("description", "High cardiovascular tempo, low lunges, and tight wall angles")
                        put("emoji", "💥")
                    })
                })
            }
            return com.tempo.app.network.models.OnboardingStepResponseDto(
                stepId = "sport",
                progress = 0.125f,
                coachMessage = "Hey! I'm your Tempo AI coach. Let's calibrate your biomechanics and dial in your movement baseline. What's your primary sport?",
                widget = widget
            )
        }

        // Step 1 -> Level
        if (currentStep == "sport") {
            val sportTitle = answers["sport"]?.replaceFirstChar { it.uppercase() } ?: "Badminton"
            val widget = buildJsonObject {
                put("widget_type", "ChoiceWidget")
                put("id", "level")
                put("title", "Current Skill Tier")
                put("subtitle", "Determines pose analysis tolerance and real-time audio cue frequency.")
                put("multi_select", false)
                put("options", kotlinx.serialization.json.buildJsonArray {
                    add(buildJsonObject {
                        put("id", "beginner")
                        put("label", "Beginner / Recreational")
                        put("description", "Building fundamental stroke paths, balance, and basic timing")
                        put("emoji", "🌱")
                    })
                    add(buildJsonObject {
                        put("id", "intermediate")
                        put("label", "Club / Intermediate")
                        put("description", "Consistent rally player tuning power, depth, and technique")
                        put("emoji", "⚡")
                    })
                    add(buildJsonObject {
                        put("id", "advanced")
                        put("label", "Advanced / Competitive")
                        put("description", "Tournament athlete optimizing milliseconds of kinetic lag")
                        put("emoji", "🏆")
                    })
                })
            }
            return com.tempo.app.network.models.OnboardingStepResponseDto(
                stepId = "level",
                progress = 0.25f,
                coachMessage = "$sportTitle! Fantastic sport for kinetic chain mastery. What level are you currently competing at?",
                widget = widget
            )
        }

        // Step 2 -> Goal
        if (currentStep == "level") {
            val widget = buildJsonObject {
                put("widget_type", "ChoiceWidget")
                put("id", "goal")
                put("title", "Primary Focus Area")
                put("subtitle", "Our Gemini Argon pipeline prioritizes drills targeting this flaw.")
                put("multi_select", false)
                put("options", kotlinx.serialization.json.buildJsonArray {
                    add(buildJsonObject {
                        put("id", "overhead_power")
                        put("label", "Overhead Power & Steepness")
                        put("description", "Maximize forearm pronation and steep downward attack trajectory")
                        put("emoji", "⚡")
                    })
                    add(buildJsonObject {
                        put("id", "footwork_speed")
                        put("label", "Footwork Speed & Recovery")
                        put("description", "Quicker recovery to center court and explosive change of direction")
                        put("emoji", "👟")
                    })
                    add(buildJsonObject {
                        put("id", "consistency_depth")
                        put("label", "Stroke Consistency & Length")
                        put("description", "Eliminate unforced frame errors and hit back line consistently")
                        put("emoji", "🎯")
                    })
                })
            }
            return com.tempo.app.network.models.OnboardingStepResponseDto(
                stepId = "goal",
                progress = 0.375f,
                coachMessage = "Got it. Every athlete has a primary lever. What is the single biggest breakthrough you want from our sessions?",
                widget = widget
            )
        }

        // Step 3 -> Playstyle
        if (currentStep == "goal") {
            val widget = buildJsonObject {
                put("widget_type", "ChoiceWidget")
                put("id", "playstyle")
                put("title", "Court Playstyle")
                put("subtitle", "Aligns tactical SDUI recommendations with your personality.")
                put("multi_select", false)
                put("options", kotlinx.serialization.json.buildJsonArray {
                    add(buildJsonObject {
                        put("id", "defensive")
                        put("label", "Defensive Retriever")
                        put("description", "Patient, high clears, tireless court coverage, waiting for opponent errors")
                        put("emoji", "🛡️")
                    })
                    add(buildJsonObject {
                        put("id", "aggressive")
                        put("label", "Aggressive Attacker")
                        put("description", "Heavy pace, steep jump smashes, intercepts early at the net")
                        put("emoji", "🔥")
                    })
                    add(buildJsonObject {
                        put("id", "all_court")
                        put("label", "All-Court Tactician")
                        put("description", "Deceptive drops, shifts tempo unpredictably, controls geometry")
                        put("emoji", "🧠")
                    })
                })
            }
            return com.tempo.app.network.models.OnboardingStepResponseDto(
                stepId = "playstyle",
                progress = 0.50f,
                coachMessage = "Love that focus. Now, how do you express yourself on court? What's your natural playstyle?",
                widget = widget
            )
        }

        // Step 4 -> Injuries
        if (currentStep == "playstyle") {
            val widget = buildJsonObject {
                put("widget_type", "ChoiceWidget")
                put("id", "injuries")
                put("title", "Injury Prevention Guardrails")
                put("subtitle", "Tempo flags excessive joint stress during high-strain phases.")
                put("multi_select", false)
                put("options", kotlinx.serialization.json.buildJsonArray {
                    add(buildJsonObject {
                        put("id", "none")
                        put("label", "100% Healthy / No Issues")
                        put("description", "Ready for maximum range of motion and load")
                        put("emoji", "✨")
                    })
                    add(buildJsonObject {
                        put("id", "shoulder")
                        put("label", "Rotator Cuff / Shoulder")
                        put("description", "Guard against hyperextension during high loading phase")
                        put("emoji", "⚠️")
                    })
                    add(buildJsonObject {
                        put("id", "elbow")
                        put("label", "Forearm Tendon / Tennis Elbow")
                        put("description", "Monitor impact shock and grip deceleration")
                        put("emoji", "🩹")
                    })
                    add(buildJsonObject {
                        put("id", "knee")
                        put("label", "Knee / Patellar Tendon")
                        put("description", "Monitor jump landing angles and deep lunge shock")
                        put("emoji", "🦵")
                    })
                })
            }
            return com.tempo.app.network.models.OnboardingStepResponseDto(
                stepId = "injuries",
                progress = 0.625f,
                coachMessage = "Crucial biomechanical check: protect the kinetic chain. Any past or recurring limitations I should guard against?",
                widget = widget
            )
        }

        // Step 5 -> "Who do you want to move like?"
        if (currentStep == "injuries") {
            val isTennis = answers["sport"].equals("tennis", ignoreCase = true)
            val widget = buildJsonObject {
                put("widget_type", "ChoiceWidget")
                put("id", "archetype")
                put("title", "Kinematic Benchmark Archetype")
                put("subtitle", "Your 33-landmark skeleton will be compared directly against their gold standard.")
                put("multi_select", false)
                put("options", kotlinx.serialization.json.buildJsonArray {
                    if (isTennis) {
                        add(buildJsonObject {
                            put("id", "Roger Federer")
                            put("label", "Roger Federer")
                            put("description", "Effortless kinetic fluidity, precision balance, and early ball-strike")
                            put("emoji", "🇨🇭")
                        })
                        add(buildJsonObject {
                            put("id", "Rafael Nadal")
                            put("label", "Rafael Nadal")
                            put("description", "Heavy topspin torque, explosive open stance, and maximum angular momentum")
                            put("emoji", "🇪🇸")
                        })
                        add(buildJsonObject {
                            put("id", "Carlos Alcaraz")
                            put("label", "Carlos Alcaraz")
                            put("description", "Dynamic front-foot acceleration, steep drop deception, and lightning recovery")
                            put("emoji", "⚡")
                        })
                    } else {
                        add(buildJsonObject {
                            put("id", "Viktor Axelsen")
                            put("label", "Viktor Axelsen")
                            put("description", "Full 175° reach, steep downward angles, suffocating court length")
                            put("emoji", "🇩🇰")
                        })
                        add(buildJsonObject {
                            put("id", "Kento Momota")
                            put("label", "Kento Momota")
                            put("description", "Flawless footwork economy, surgical precision, deceptive defensive turns")
                            put("emoji", "🇯🇵")
                        })
                        add(buildJsonObject {
                            put("id", "Lee Chong Wei")
                            put("label", "Lee Chong Wei")
                            put("description", "Lightning racket acceleration, explosive jump smashes, feline agility")
                            put("emoji", "🇲🇾")
                        })
                    }
                })
            }
            return com.tempo.app.network.models.OnboardingStepResponseDto(
                stepId = "archetype",
                progress = 0.75f,
                coachMessage = "This is my favorite part. Biomechanics work best with a mental model. Who do you want to move like?",
                widget = widget
            )
        }

        // Step 6 -> 5-Second Capture Prompt
        if (currentStep == "archetype") {
            val targetArchetype = answers["archetype"] ?: "Viktor Axelsen"
            val widget = buildJsonObject {
                put("widget_type", "CapturePromptWidget")
                put("id", "baseline_calibration")
                put("title", "Baseline Stroke Calibration")
                put("instruction", "Record 1 full-effort practice swing. Stand 3-4 meters away so your entire body and racket are visible in frame.")
                put("camera_hint", "Film from behind-left • Full body in frame • 60fps")
                put("duration_s", 5)
            }
            return com.tempo.app.network.models.OnboardingStepResponseDto(
                stepId = "capture_prompt",
                progress = 0.875f,
                coachMessage = "Calibrating your baseline against $targetArchetype! Let's record a 5-second calibration swing so the AI maps your initial posture.",
                widget = widget
            )
        }

        // Step 7 -> Summary & Permissions
        val selectedSport = answers["sport"] ?: "badminton"
        val selectedLevel = answers["level"] ?: "intermediate"
        val selectedGoal = answers["goal"] ?: "overhead_power"
        val selectedPlaystyle = answers["playstyle"] ?: "aggressive"
        val selectedInjuries = answers["injuries"] ?: "none"
        val selectedArchetype = answers["archetype"] ?: "Viktor Axelsen"

        val userProfile = com.tempo.app.network.models.UserProfileDto(
            userId = currentUserId,
            sport = selectedSport,
            level = selectedLevel,
            goal = selectedGoal,
            playstyle = selectedPlaystyle,
            injuries = selectedInjuries,
            targetArchetype = selectedArchetype,
            calibrationCompleted = true
        )

        return com.tempo.app.network.models.OnboardingStepResponseDto(
            stepId = "summary_permissions",
            progress = 1.0f,
            coachMessage = "You're all set! We've configured your profile benchmarked to $selectedArchetype. Grant the permissions below so Tempo can deliver live kinematic coaching.",
            widget = null,
            isCompleted = true,
            userProfile = userProfile
        )
    }

    override suspend fun register(request: com.tempo.app.network.models.RegisterRequestDto): com.tempo.app.network.models.AuthResponseDto {
        delay(200)
        val uid = "user_" + UUID.randomUUID().toString().take(8)
        identity.userId = uid
        identity.email = request.email
        identity.displayName = request.displayName
        val token = "mock_token_" + UUID.randomUUID().toString()
        identity.accessToken = token
        return com.tempo.app.network.models.AuthResponseDto(
            userId = uid,
            accessToken = token,
            displayName = request.displayName
        )
    }

    override suspend fun login(request: com.tempo.app.network.models.LoginRequestDto): com.tempo.app.network.models.AuthResponseDto {
        delay(200)
        val uid = identity.userId.ifBlank { "user_1" }
        identity.email = request.email
        val token = "mock_token_" + UUID.randomUUID().toString()
        identity.accessToken = token
        return com.tempo.app.network.models.AuthResponseDto(
            userId = uid,
            accessToken = token,
            displayName = identity.displayName.ifBlank { "Athlete" }
        )
    }

    override suspend fun getMe(): com.tempo.app.network.models.UserProfileDto {
        delay(100)
        return com.tempo.app.network.models.UserProfileDto(
            userId = currentUserId,
            sport = identity.sport ?: "badminton",
            level = "intermediate",
            goal = "overhead_power",
            playstyle = "aggressive",
            injuries = "none",
            targetArchetype = "Viktor Axelsen",
            calibrationCompleted = true
        )
    }

    override suspend fun logout(): Map<String, String> {
        delay(100)
        identity.clear()
        return mapOf("status" to "logged_out")
    }

    override suspend fun getSports(): List<com.tempo.app.network.models.SportDto> {
        delay(150)
        return listOf(
            com.tempo.app.network.models.SportDto(
                id = "badminton",
                displayName = "Badminton",
                iconKey = "badminton_shuttle",
                analysisReady = true,
                skills = listOf(
                    com.tempo.app.network.models.SportSkillDto("overhead_clear", "Overhead Clear", analysisReady = true),
                    com.tempo.app.network.models.SportSkillDto("jump_smash", "Jump Smash", analysisReady = false)
                )
            ),
            com.tempo.app.network.models.SportDto(
                id = "tennis",
                displayName = "Tennis",
                iconKey = "tennis_ball",
                analysisReady = true,
                skills = listOf(
                    com.tempo.app.network.models.SportSkillDto("forehand", "Modern Forehand", analysisReady = true),
                    com.tempo.app.network.models.SportSkillDto("one_hand_backhand", "One-Handed Backhand", analysisReady = true)
                )
            ),
            com.tempo.app.network.models.SportDto(
                id = "padel",
                displayName = "Padel",
                iconKey = "padel_racket",
                analysisReady = false
            ),
            com.tempo.app.network.models.SportDto(
                id = "pickleball",
                displayName = "Pickleball",
                iconKey = "pickleball_paddle",
                analysisReady = false
            ),
            com.tempo.app.network.models.SportDto(
                id = "squash",
                displayName = "Squash",
                iconKey = "squash_ball",
                analysisReady = false
            ),
            com.tempo.app.network.models.SportDto(
                id = "table_tennis",
                displayName = "Table Tennis",
                iconKey = "table_tennis_paddle",
                analysisReady = false
            ),
            com.tempo.app.network.models.SportDto(
                id = "golf",
                displayName = "Golf",
                iconKey = "golf_tee",
                analysisReady = false
            )
        )
    }

    override suspend fun updateProfile(profile: com.tempo.app.network.models.ProfilePayloadDto): Map<String, String> {
        delay(150)
        identity.sport = profile.sport
        identity.skill = profile.skill
        return mapOf("status" to "profile_updated", "user_id" to currentUserId)
    }

    override suspend fun getProfile(): com.tempo.app.network.models.UserProfileDto {
        return getMe()
    }

    override suspend fun getAiStatus(): com.tempo.app.network.models.AiStatusDto {
        delay(100)
        return com.tempo.app.network.models.AiStatusDto(
            configured = true,
            model = "gemini-4-argon",
            keyMasked = "AQ.A...ciCg",
            lastCallOk = true,
            lastLatencyMs = 420,
            lastCheckedAt = java.time.Instant.now().toString()
        )
    }

    override suspend fun converseWithCoach(
        request: com.tempo.app.network.models.CoachConverseRequestDto
    ): com.tempo.app.network.models.CoachConverseResponseDto {
        delay(250)
        return com.tempo.app.network.models.CoachConverseResponseDto(
            replyText = "Welcome to your training studio. I'm Thea, your biomechanics coach. Based on your recent overhead practice, we're locking in high contact apex and forearm pronation. What would you like to work on today?",
            audioCueText = "Reach high at contact apex.",
            dynamicWidgets = emptyList(),
            latencyMs = 250
        )
    }
}
