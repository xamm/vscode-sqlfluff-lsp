import * as vscode from 'vscode';

function diagnosticsForError(diagnostics: readonly vscode.Diagnostic[]): unknown[] {
    return diagnostics.map((diagnostic) => ({
        code: diagnostic.code,
        source: diagnostic.source,
        range: diagnostic.range,
    }));
}

export async function openSqlDocument(uri: vscode.Uri): Promise<vscode.TextDocument> {
    const document = await vscode.workspace.openTextDocument(uri);
    await vscode.window.showTextDocument(document);
    return document;
}

export async function waitForDiagnostics(
    uri: vscode.Uri,
    timeoutMs: number,
    predicate: (diagnostics: readonly vscode.Diagnostic[]) => boolean = (diagnostics) => diagnostics.length > 0,
): Promise<vscode.Diagnostic[]> {
    const deadline = Date.now() + timeoutMs;
    let diagnostics: readonly vscode.Diagnostic[] = [];

    do {
        diagnostics = vscode.languages.getDiagnostics(uri);
        if (predicate(diagnostics)) {
            return [...diagnostics];
        }

        const remainingMs = deadline - Date.now();
        if (remainingMs <= 0) {
            break;
        }
        await new Promise<void>((resolve) => setTimeout(resolve, Math.min(250, remainingMs)));
    } while (Date.now() < deadline);

    throw new Error(
        `Timed out after ${timeoutMs} ms waiting for diagnostics: ${JSON.stringify(diagnosticsForError(diagnostics))}`,
    );
}

export function restartAndAwaitRepublish(uri: vscode.Uri, timeoutMs: number): Promise<void> {
    return new Promise<void>((resolve, reject) => {
        let sawEmpty = false;
        let settled = false;
        const subscription = vscode.languages.onDidChangeDiagnostics((event) => {
            if (settled || !event.uris.some((eventUri) => eventUri.toString() === uri.toString())) {
                return;
            }

            const diagnostics = vscode.languages.getDiagnostics(uri);
            if (diagnostics.length === 0) {
                sawEmpty = true;
                return;
            }

            settled = true;
            subscription.dispose();
            clearTimeout(timer);
            if (sawEmpty || diagnostics.length > 0) {
                resolve();
            }
        });
        const timer = setTimeout(() => {
            if (settled) {
                return;
            }
            settled = true;
            subscription.dispose();
            reject(new Error(`Timed out after ${timeoutMs} ms waiting for diagnostics republish`));
        }, timeoutMs);
    });
}
