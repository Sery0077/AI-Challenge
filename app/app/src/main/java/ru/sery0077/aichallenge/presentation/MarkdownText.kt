package ru.sery0077.aichallenge.presentation

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.tooling.preview.Preview
import ru.sery0077.aichallenge.ui.theme.AIChallengeTheme

@Composable
fun MarkdownText(
    text: AnnotatedString,
    modifier: Modifier = Modifier,
) {
    Text(text = text, modifier = modifier)
}

@Preview(showBackground = true)
@Composable
private fun MarkdownTextPreview() {
    AIChallengeTheme {
        MarkdownText(
            text = AnnotatedString("Пример MarkdownText"),
        )
    }
}
