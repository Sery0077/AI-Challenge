package ru.sery0077.aichallenge.domain.repository

import kotlinx.coroutines.flow.Flow
import ru.sery0077.aichallenge.domain.model.RequestSettings

interface RouterAIRepository {
    fun streamPrompt(prompt: String, settings: RequestSettings): Flow<String>
}
