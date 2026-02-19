package ru.sery0077.aichallenge

import android.app.Application
import org.koin.android.ext.koin.androidContext
import org.koin.core.context.startKoin
import ru.sery0077.aichallenge.di.appModule

class App : Application() {
    override fun onCreate() {
        super.onCreate()
        startKoin {
            androidContext(this@App)
            modules(appModule)
        }
    }
}
