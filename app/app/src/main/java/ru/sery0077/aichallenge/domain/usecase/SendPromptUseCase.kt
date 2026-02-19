package ru.sery0077.aichallenge.domain.usecase

import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import ru.sery0077.aichallenge.domain.model.RequestSettings
import ru.sery0077.aichallenge.domain.repository.RouterAIRepository

class SendPromptUseCase(
    private val repository: RouterAIRepository,
) {
    operator fun invoke(prompt: String, settings: RequestSettings): Flow<String> {
        if (prompt.isBlank()) {
            return flow { throw IllegalArgumentException("Prompt is blank.") }
        }
        return repository.streamPrompt(
            prompt = prompt,
            settings = settings,
        )
    }
}
