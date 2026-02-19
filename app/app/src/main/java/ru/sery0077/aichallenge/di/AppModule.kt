package ru.sery0077.aichallenge.di

import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import org.koin.core.module.dsl.viewModel
import org.koin.dsl.module
import ru.sery0077.aichallenge.data.repository.RouterAIConfigRepositoryImpl
import ru.sery0077.aichallenge.data.repository.RouterAIRepositoryImpl
import ru.sery0077.aichallenge.domain.repository.RouterAIConfigRepository
import ru.sery0077.aichallenge.domain.repository.RouterAIRepository
import ru.sery0077.aichallenge.domain.usecase.SendPromptUseCase
import ru.sery0077.aichallenge.presentation.MainViewModel
import java.util.concurrent.TimeUnit

val appModule = module {
    single { provideJson() }
    single { provideOkHttpClient() }
    single<RouterAIConfigRepository> { RouterAIConfigRepositoryImpl() }
    single<RouterAIRepository> { RouterAIRepositoryImpl(get(), get(), get()) }
    single { SendPromptUseCase(get()) }
    viewModel { MainViewModel(get(), get()) }
}

private fun provideJson(): Json = Json {
    ignoreUnknownKeys = true
    isLenient = true
}

private fun provideOkHttpClient(): OkHttpClient {
    return OkHttpClient.Builder()
        .connectTimeout(60, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .writeTimeout(120, TimeUnit.SECONDS)
        .callTimeout(180, TimeUnit.SECONDS)
        .build()
}

// Retrofit setup can be added here later if needed.
