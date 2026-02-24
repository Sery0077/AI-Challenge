package ru.sery0077.aichallenge.feature.chat.domain.usecase

import ru.sery0077.aichallenge.feature.chat.domain.repository.ChatHistoryRepository

class CreateSessionUseCase(
    private val repository: ChatHistoryRepository,
) {
    suspend operator fun invoke(title: String, model: String, timestamp: Long): Long {
        return repository.createSession(title, model, timestamp)
    }
}
